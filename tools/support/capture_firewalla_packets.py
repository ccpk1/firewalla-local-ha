"""Windows helper to capture Firewalla packets and build a safe report.

This support tool is intentionally narrow:

- prompt for router IP address or hostname and SSH password
- SSH to the Firewalla box as user ``pi`` on port ``22``
- start a remote tcpdump capture in the background
- wait for the user to reproduce the behavior they want to capture
- stop the capture, download the pcap, and clean up remote files
- build a local safe report from cleartext HTTP metadata only

It does not perform any payload decryption and does not include the raw pcap in
the safe report archive.
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

try:
    import paramiko
except ImportError:  # pragma: no cover - environment-specific dependency
    paramiko = None

try:
    from scp import SCPClient, SCPException
except ImportError:  # pragma: no cover - environment-specific dependency
    SCPClient = None
    SCPException = None

try:
    from scapy.layers.inet import IP, TCP
    from scapy.utils import rdpcap
except ImportError:  # pragma: no cover - environment-specific dependency
    IP = None
    TCP = None
    rdpcap = None

if TYPE_CHECKING:
    from paramiko import SSHClient


SSH_PORT: Final = 22
SSH_USER: Final = "pi"
REMOTE_PCAP_PATH: Final = "/tmp/firewalla_capture.pcap"
REMOTE_PID_PATH: Final = "/tmp/firewalla_capture.pid"
DEFAULT_CONNECT_TIMEOUT: Final = 10.0
DEFAULT_CAPTURE_FILTER: Final = "tcp port 8833"
SERVER_PORT: Final = 8833
MESSAGE_PATH_RE = re.compile(r"(/v1/encipher/message/)[^\s?]+")


@dataclass(slots=True)
class Segment:
    """One TCP payload segment captured from the local Firewalla transport."""

    seq: int
    data: bytes
    ts: float


@dataclass(slots=True)
class HttpMessage:
    """One parsed HTTP message from a reassembled port 8833 TCP stream."""

    ts: float | None
    first_line: str
    headers: dict[str, str]
    content_length: int


@dataclass(slots=True)
class SafeReportEvent:
    """One safe report event derived from cleartext packet metadata."""

    timestamp_utc: str
    direction: str
    kind: str
    message_class: str
    first_line: str
    content_length: int | None = None
    user_agent: str | None = None
    content_type: str | None = None
    latency_seconds: float | None = None
    status_code: str | None = None


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Start a remote Firewalla packet capture, wait for the target "
            "behavior to occur, download the pcap, and clean up"
        )
    )
    parser.add_argument(
        "--host",
        help="Router IP address or hostname. If omitted, you will be prompted.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Local directory where the downloaded pcap should be saved",
    )
    parser.add_argument(
        "--label",
        help=(
            "Optional short label to distinguish one capture, such as "
            "phone-success or home-assistant-attempt"
        ),
    )
    parser.add_argument(
        "--client-ip",
        help=(
            "Optional client IP address to restrict the remote capture to one "
            "client, such as the pairing phone or Home Assistant host"
        ),
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=DEFAULT_CONNECT_TIMEOUT,
        help="SSH connection timeout in seconds",
    )
    return parser


def require_dependencies() -> None:
    """Raise a friendly error if required libraries are not installed."""
    missing: list[str] = []
    if paramiko is None:
        missing.append("paramiko")
    if SCPClient is None:
        missing.append("scp")
    if missing:
        package_list = ", ".join(missing)
        raise RuntimeError(
            "Missing required Python packages: "
            f"{package_list}. Install them with: pip install {package_list}"
        )


def prompt_host(provided_host: str | None) -> str:
    """Return the provided or prompted router IP address."""
    if provided_host and provided_host.strip():
        return provided_host.strip()

    while True:
        host = input("Router IP address or hostname: ").strip()
        if host:
            return host
        print("A router IP address or hostname is required.")


def normalize_label(label: str | None) -> str | None:
    """Return a filesystem-safe label fragment or None."""
    if label is None:
        return None

    normalized = "".join(
        char.lower() if char.isalnum() else "-" for char in label.strip()
    ).strip("-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized or None


def build_local_capture_path(output_dir: Path, label: str | None) -> Path:
    """Return one timestamped local output path for the downloaded pcap."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"_{label}" if label else ""
    return output_dir / f"firewalla_capture_{timestamp}{suffix}.pcap"


def build_capture_filter(client_ip: str | None) -> str:
    """Return the tcpdump filter for the requested capture scope."""
    if not client_ip:
        return DEFAULT_CAPTURE_FILTER

    validated_ip = ipaddress.ip_address(client_ip)
    return f"{DEFAULT_CAPTURE_FILTER} and host {validated_ip}"


def format_ts(ts: float) -> str:
    """Render one timestamp in a stable UTC format."""
    return datetime.utcfromtimestamp(ts).isoformat() + "Z"


def reassemble(segments: list[Segment]) -> tuple[bytes, list[tuple[int, float]]]:
    """Reassemble ordered TCP payload segments into one byte stream."""
    ordered = sorted(segments, key=lambda item: (item.seq, item.ts, len(item.data)))
    output = bytearray()
    offsets: list[tuple[int, float]] = []
    next_seq: int | None = None
    for segment in ordered:
        if next_seq is None:
            offsets.append((0, segment.ts))
            output.extend(segment.data)
            next_seq = segment.seq + len(segment.data)
            continue

        if segment.seq >= next_seq:
            gap = segment.seq - next_seq
            if gap:
                output.extend(b" " * gap)
            offsets.append((len(output), segment.ts))
            output.extend(segment.data)
            next_seq = segment.seq + len(segment.data)
            continue

        overlap = next_seq - segment.seq
        if overlap < len(segment.data):
            offsets.append((len(output), segment.ts))
            output.extend(segment.data[overlap:])
            next_seq += len(segment.data) - overlap

    return bytes(output), offsets


def ts_for_offset(offsets: list[tuple[int, float]], position: int) -> float | None:
    """Return the last packet timestamp known at one stream offset."""
    current: float | None = None
    for offset, ts in offsets:
        if offset > position:
            break
        current = ts
    return current


def parse_http_messages(
    blob: bytes,
    offsets: list[tuple[int, float]],
    *,
    request: bool,
) -> list[HttpMessage]:
    """Split a byte stream into HTTP messages with timestamps and headers."""
    request_markers = (b"POST ", b"GET ")
    response_marker = b"HTTP/1.1 "
    index = 0
    parsed: list[HttpMessage] = []
    while True:
        if request:
            starts = [blob.find(marker, index) for marker in request_markers]
            starts = [start for start in starts if start >= 0]
            start = min(starts) if starts else -1
        else:
            start = blob.find(response_marker, index)
        if start < 0:
            break

        header_end = blob.find(b"\r\n\r\n", start)
        if header_end < 0:
            break

        header = blob[start:header_end].decode("latin1", errors="ignore")
        first_line, *rest = header.split("\r\n")
        headers: dict[str, str] = {}
        content_length: int | None = None
        for line in rest:
            name, _, value = line.partition(":")
            header_name = name.lower()
            header_value = value.strip()
            headers[header_name] = header_value
            if header_name == "content-length":
                try:
                    content_length = int(header_value)
                except ValueError:
                    content_length = 0

        if content_length is None:
            if request:
                content_length = 0
            else:
                transfer_encoding = headers.get("transfer-encoding", "")
                content_type = headers.get("content-type", "")
                if transfer_encoding.lower() == "chunked" or content_type.startswith(
                    "text/event-stream"
                ):
                    next_start = blob.find(response_marker, header_end + 4)
                    if next_start < 0:
                        content_length = len(blob) - (header_end + 4)
                    else:
                        content_length = next_start - (header_end + 4)
                else:
                    content_length = 0

        body_start = header_end + 4
        body_end = body_start + content_length
        body = blob[body_start:body_end]
        if len(body) < content_length:
            break

        parsed.append(
            HttpMessage(
                ts=ts_for_offset(offsets, start),
                first_line=first_line,
                headers=headers,
                content_length=len(body),
            )
        )
        index = body_end

    return parsed


def classify_message(message: HttpMessage, *, request: bool) -> str:
    """Return one stable safe-report class label."""
    if request:
        if message.first_line.startswith("POST "):
            return "post_request"
        if message.first_line.startswith("GET "):
            return "get_request"
        return "request_unknown"

    content_type = message.headers.get("content-type", "")
    if content_type.startswith("text/event-stream"):
        return "event_stream_response"
    if content_type.startswith("application/json"):
        return "json_response"
    return "response_unknown"


def redact_request_line(first_line: str) -> str:
    """Redact the Firewalla message path identifier from one request line."""
    return MESSAGE_PATH_RE.sub(r"\1{gid}", first_line)


def extract_status_code(first_line: str) -> str | None:
    """Return the HTTP status code from one response line when present."""
    parts = first_line.split()
    if len(parts) >= 2 and parts[0].startswith("HTTP/"):
        return parts[1]
    return None


def determine_connection_pattern(
    *,
    distinct_request_connections: int,
    request_count: int,
) -> str:
    """Return a compact description of client connection reuse."""
    if request_count == 0:
        return "no_http_requests"
    if distinct_request_connections == 1:
        return "persistent_request_connection"
    if distinct_request_connections >= request_count:
        return "separate_request_connections"
    return "mixed_request_connections"


def flow_peer_key(flow: tuple[str, int, str, int], *, request: bool) -> tuple[str, int]:
    """Return a stable client endpoint key for one parsed flow."""
    if request:
        return (flow[0], flow[1])
    return (flow[2], flow[3])


def flow_direction_label(is_request: bool, peer_index: int) -> str:
    """Return a stable redacted direction label."""
    peer = f"CLIENT_{peer_index}"
    if is_request:
        return f"{peer} -> BOX"
    return f"BOX -> {peer}"


def build_safe_report(
    capture_path: Path,
    *,
    capture_label: str | None,
    client_ip: str | None,
    capture_filter: str,
) -> tuple[dict[str, object], list[SafeReportEvent]] | None:
    """Build one shareable safe report from a local pcap."""
    if IP is None or TCP is None or rdpcap is None:
        return None

    flows: dict[tuple[str, int, str, int], list[Segment]] = defaultdict(list)
    events: list[SafeReportEvent] = []
    peer_indices: dict[str, int] = {}
    request_times: dict[tuple[str, int], list[float]] = defaultdict(list)
    response_index_by_peer: dict[tuple[str, int], int] = defaultdict(int)
    distinct_request_connections: set[tuple[str, int]] = set()

    for packet in rdpcap(str(capture_path)):
        if IP not in packet or TCP not in packet:
            continue
        ip = packet[IP]
        tcp = packet[TCP]
        if tcp.sport != SERVER_PORT and tcp.dport != SERVER_PORT:
            continue

        peer_ip = ip.src if tcp.sport != SERVER_PORT else ip.dst
        if client_ip and peer_ip != client_ip:
            continue
        peer_index = peer_indices.setdefault(peer_ip, len(peer_indices) + 1)
        direction = flow_direction_label(tcp.dport == SERVER_PORT, peer_index)

        flags = int(tcp.flags)
        if flags & 0x04:
            events.append(
                SafeReportEvent(
                    timestamp_utc=format_ts(float(packet.time)),
                    direction=direction,
                    kind="tcp_event",
                    message_class="tcp_reset",
                    first_line="TCP RST observed",
                )
            )
        elif flags & 0x01:
            events.append(
                SafeReportEvent(
                    timestamp_utc=format_ts(float(packet.time)),
                    direction=direction,
                    kind="tcp_event",
                    message_class="tcp_finish",
                    first_line="TCP FIN observed",
                )
            )

        payload = bytes(tcp.payload)
        if not payload:
            continue
        flows[(ip.src, tcp.sport, ip.dst, tcp.dport)].append(
            Segment(seq=int(tcp.seq), data=payload, ts=float(packet.time))
        )

    parsed_flows: list[tuple[tuple[str, int, str, int], bool, list[HttpMessage]]] = []
    for flow, segments in sorted(flows.items()):
        is_request = flow[3] == SERVER_PORT
        blob, offsets = reassemble(segments)
        messages = parse_http_messages(blob, offsets, request=is_request)
        if not messages:
            continue
        parsed_flows.append((flow, is_request, messages))
        if is_request:
            distinct_request_connections.add((flow[0], flow[1]))
            peer_key = flow_peer_key(flow, request=True)
            for message in messages:
                if message.ts is not None:
                    request_times[peer_key].append(message.ts)

    for flow, is_request, messages in parsed_flows:
        peer_ip = flow[0] if is_request else flow[2]
        direction = flow_direction_label(is_request, peer_indices[peer_ip])
        peer_key = flow_peer_key(flow, request=is_request)
        for message in messages:
            if message.ts is None:
                continue

            latency_seconds: float | None = None
            if not is_request:
                request_index = response_index_by_peer[peer_key]
                if request_index < len(request_times[peer_key]):
                    latency_seconds = round(
                        message.ts - request_times[peer_key][request_index],
                        3,
                    )
                    response_index_by_peer[peer_key] += 1

            events.append(
                SafeReportEvent(
                    timestamp_utc=format_ts(message.ts),
                    direction=direction,
                    kind="http_request" if is_request else "http_response",
                    message_class=classify_message(message, request=is_request),
                    first_line=(
                        redact_request_line(message.first_line)
                        if is_request
                        else message.first_line
                    ),
                    content_length=message.content_length,
                    user_agent=message.headers.get("user-agent"),
                    content_type=message.headers.get("content-type"),
                    latency_seconds=latency_seconds,
                    status_code=(
                        None if is_request else extract_status_code(message.first_line)
                    ),
                )
            )

    sorted_events = sorted(events, key=lambda item: item.timestamp_utc)
    http_events = [event for event in sorted_events if event.kind.startswith("http_")]
    http_responses = [
        event.status_code
        for event in http_events
        if event.kind == "http_response" and event.status_code is not None
    ]
    http_request_events = [
        event for event in http_events if event.kind == "http_request"
    ]
    http_response_events = [
        event for event in http_events if event.kind == "http_response"
    ]

    summary: dict[str, object] = {
        "report_version": 1,
        "created_at_utc": datetime.utcnow().isoformat() + "Z",
        "capture_file_name": capture_path.name,
        "capture_label": capture_label,
        "capture_filter": capture_filter,
        "client_ip_filter_applied": client_ip is not None,
        "distinct_client_connection_count": len(distinct_request_connections),
        "connection_pattern": determine_connection_pattern(
            distinct_request_connections=len(distinct_request_connections),
            request_count=len(http_request_events),
        ),
        "http_request_count": len(http_request_events),
        "http_response_count": len(http_response_events),
        "http_request_method_sequence": [
            event.first_line.split()[0]
            for event in http_request_events
            if event.first_line.split()
        ],
        "http_response_status_sequence": http_responses,
        "http_request_class_counts": dict(
            Counter(event.message_class for event in http_request_events)
        ),
        "http_response_class_counts": dict(
            Counter(event.message_class for event in http_response_events)
        ),
        "http_response_status_counts": dict(Counter(http_responses)),
        "http_412_count": sum(status == "412" for status in http_responses),
        "live_stream_observed": any(
            event.message_class in {"get_request", "event_stream_response"}
            for event in http_events
        ),
        "tcp_event_counts": dict(
            Counter(
                event.first_line for event in sorted_events if event.kind == "tcp_event"
            )
        ),
        "observed_user_agents": sorted(
            {
                event.user_agent
                for event in http_request_events
                if event.user_agent is not None
            }
        ),
        "notes": [
            (
                "This safe report contains only cleartext HTTP metadata and "
                "TCP lifecycle events."
            ),
            "It does not decrypt payloads and does not include the raw pcap.",
            (
                "Repeated HTTP 412 responses and TCP disconnect patterns are "
                "preserved so pairing acceptance failures can be compared with "
                "Home Assistant logs."
            ),
            (
                "Cleartext headers such as User-Agent may still identify the "
                "app family or version used during pairing."
            ),
        ],
    }
    return summary, sorted_events


def write_safe_report(
    capture_path: Path,
    *,
    summary: dict[str, object],
    events: list[SafeReportEvent],
) -> Path:
    """Write one local safe report zip and return its path."""
    report_dir = capture_path.parent / f"{capture_path.stem}_safe_report"
    report_dir.mkdir(parents=True, exist_ok=False)

    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (report_dir / "events.json").write_text(
        json.dumps([asdict(event) for event in events], indent=2, sort_keys=True),
        encoding="utf-8",
    )

    transcript_lines = [
        "Windows Firewalla packet capture safe report",
        "",
        f"Capture file: {capture_path.name}",
    ]
    if summary.get("capture_label"):
        transcript_lines.append(f"Capture label: {summary['capture_label']}")
    connection_count = summary["distinct_client_connection_count"]
    connection_pattern = summary["connection_pattern"]
    request_count = summary["http_request_count"]
    response_count = summary["http_response_count"]
    status_counts = summary["http_response_status_counts"]
    status_sequence = summary["http_response_status_sequence"]
    request_sequence = summary["http_request_method_sequence"]
    http_412_count = summary["http_412_count"]
    live_stream_observed = summary["live_stream_observed"]
    transcript_lines.extend(
        [
            f"Distinct client connections: {connection_count}",
            f"Connection pattern: {connection_pattern}",
            f"HTTP requests: {request_count}",
            f"HTTP responses: {response_count}",
            f"HTTP response status counts: {status_counts}",
            f"HTTP response status sequence: {status_sequence}",
            f"HTTP request method sequence: {request_sequence}",
            f"HTTP 412 responses: {http_412_count}",
            f"Live stream observed: {live_stream_observed}",
            "",
            "Observed user agents:",
        ]
    )
    user_agents = summary.get("observed_user_agents", [])
    if isinstance(user_agents, list) and user_agents:
        transcript_lines.extend(f"- {user_agent}" for user_agent in user_agents)
    else:
        transcript_lines.append("- none")
    transcript_lines.extend(["", "HTTP and TCP events:"])
    for event in events:
        parts = [
            event.timestamp_utc,
            event.direction,
            event.kind,
            event.message_class,
            event.first_line,
        ]
        if event.content_length is not None:
            parts.append(f"content_length={event.content_length}")
        if event.user_agent:
            parts.append(f"user_agent={event.user_agent}")
        if event.content_type:
            parts.append(f"content_type={event.content_type}")
        if event.latency_seconds is not None:
            parts.append(f"latency_seconds={event.latency_seconds}")
        transcript_lines.append(" | ".join(parts))

    (report_dir / "transcript.txt").write_text(
        "\n".join(transcript_lines) + "\n",
        encoding="utf-8",
    )
    (report_dir / "README.txt").write_text(
        "This safe report archive contains only cleartext packet metadata, such as "
        "HTTP request lines, response status lines, selected headers, content "
        "lengths, and TCP disconnect events. The raw pcap stays local and is not "
        "included in this zip.\n",
        encoding="utf-8",
    )

    bundle_path = capture_path.parent / f"{capture_path.stem}_safe_report.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(report_dir.iterdir()):
            bundle.write(path, arcname=path.name)
    return bundle_path


def connect_ssh(host: str, password: str, timeout: float) -> SSHClient:
    """Open and return one SSH connection to the remote router."""
    assert paramiko is not None
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=SSH_PORT,
        username=SSH_USER,
        password=password,
        timeout=timeout,
        auth_timeout=timeout,
        banner_timeout=timeout,
    )
    return client


def run_remote_command(client: SSHClient, command: str) -> tuple[int, str, str]:
    """Run one remote shell command and return status, stdout, and stderr."""
    stdin, stdout, stderr = client.exec_command(command)
    stdin.close()
    exit_status = stdout.channel.recv_exit_status()
    return (
        exit_status,
        stdout.read().decode("utf-8", errors="ignore"),
        stderr.read().decode("utf-8", errors="ignore"),
    )


def start_remote_capture(client: SSHClient, capture_filter: str) -> None:
    """Start tcpdump on the remote router and persist its PID."""
    command = (
        "sudo sh -lc "
        f"'rm -f {REMOTE_PCAP_PATH} {REMOTE_PID_PATH}; "
        f"tcpdump -U -n -s 0 -i any -w {REMOTE_PCAP_PATH} {capture_filter} "
        ">/dev/null 2>&1 & "
        f"echo $! > {REMOTE_PID_PATH}'"
    )
    exit_status, _stdout, stderr = run_remote_command(client, command)
    if exit_status != 0:
        raise RuntimeError(
            "Failed to start remote packet capture"
            + (f": {stderr.strip()}" if stderr.strip() else "")
        )

    time.sleep(1.0)
    verify_status, stdout, stderr = run_remote_command(
        client,
        f"sh -lc 'test -s {REMOTE_PID_PATH} && cat {REMOTE_PID_PATH}'",
    )
    if verify_status != 0 or not stdout.strip():
        detail = stderr.strip() or stdout.strip()
        raise RuntimeError(
            "Remote packet capture did not report a running PID"
            + (f": {detail}" if detail else "")
        )


def stop_remote_capture(client: SSHClient) -> None:
    """Stop tcpdump on the remote router if it is still running."""
    command = (
        "sudo sh -lc "
        f"'if [ -f {REMOTE_PID_PATH} ]; then "
        f"kill $(cat {REMOTE_PID_PATH}) >/dev/null 2>&1 || true; "
        f"wait $(cat {REMOTE_PID_PATH}) >/dev/null 2>&1 || true; "
        f"rm -f {REMOTE_PID_PATH}; "
        f'else pkill -f "tcpdump -i any -w {REMOTE_PCAP_PATH}" '
        ">/dev/null 2>&1 || true; "
        "fi'"
    )
    run_remote_command(client, command)


def cleanup_remote_capture(client: SSHClient) -> None:
    """Delete temporary remote capture files."""
    run_remote_command(
        client,
        f"sudo rm -f {REMOTE_PCAP_PATH} {REMOTE_PID_PATH}",
    )


def download_capture(client: SSHClient, local_path: Path) -> None:
    """Download the remote pcap to the requested local path."""
    assert SCPClient is not None
    transport = client.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport is no longer available for SCP download")

    with SCPClient(transport) as scp:
        scp.get(REMOTE_PCAP_PATH, str(local_path))


def main() -> int:
    """Run the Windows Firewalla packet capture workflow."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        require_dependencies()
    except RuntimeError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    assert paramiko is not None
    assert SCPException is not None

    host = prompt_host(args.host)
    password = getpass.getpass(f"SSH password for {SSH_USER}@{host}: ")
    label = normalize_label(args.label)
    local_capture_path = build_local_capture_path(args.output_dir, label)

    try:
        capture_filter = build_capture_filter(args.client_ip)
    except ValueError as err:
        print(f"Invalid --client-ip value: {err}", file=sys.stderr)
        return 1

    client: SSHClient | None = None
    capture_started = False

    try:
        client = connect_ssh(host, password, args.connect_timeout)
        start_remote_capture(client, capture_filter)
        capture_started = True

        print()
        print(f"Remote capture filter: {capture_filter}")
        print(
            "Capture started. Reproduce the behavior you want to capture now. "
            "Press [ENTER] when you are finished or if the issue occurs."
        )
        input()

        stop_remote_capture(client)
        download_capture(client, local_capture_path)
        cleanup_remote_capture(client)

        report_path: Path | None = None
        safe_report = build_safe_report(
            local_capture_path,
            capture_label=label,
            client_ip=args.client_ip,
            capture_filter=capture_filter,
        )
        if safe_report is not None:
            summary, events = safe_report
            report_path = write_safe_report(
                local_capture_path,
                summary=summary,
                events=events,
            )

        print()
        print(f"Success. Capture saved to: {local_capture_path}")
        if report_path is not None:
            print(f"Safe report saved to: {report_path}")
            print("Share the safe report first and keep the raw pcap private.")
        else:
            print(
                "Safe report generation was skipped because Scapy is not available. "
                "Keep the raw pcap private unless asked to share it privately."
            )
        return 0
    except KeyboardInterrupt:
        print()
        print("Interrupted. Attempting remote cleanup before exiting.", file=sys.stderr)
        return 130
    except paramiko.AuthenticationException as err:
        print(f"Authentication failed: {err}", file=sys.stderr)
        return 1
    except (paramiko.SSHException, OSError, TimeoutError) as err:
        print(f"Connection or SSH error: {err}", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, SCPException) as err:
        print(f"Capture failed: {err}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            if capture_started:
                with suppress(Exception):
                    stop_remote_capture(client)
                with suppress(Exception):
                    cleanup_remote_capture(client)
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
