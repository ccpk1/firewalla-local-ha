"""Capture a narrow Firewalla pairing trace and build a shareable bundle.

This helper is intended to make pairing capture collection simple for users
while keeping the raw packet capture local by default. It arms a short remote
`tcpdump` capture on the Firewalla box, downloads the resulting `.pcap`, and
creates a redacted support bundle containing only HTTP metadata and TCP
disconnect events for local port `8833`.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from scapy.layers.inet import IP, TCP
from scapy.utils import rdpcap

DEFAULT_CAPTURE_DURATION_SECONDS: Final = 150
DEFAULT_CAPTURE_FILTER: Final = "tcp port 8833"
DEFAULT_INTERFACE: Final = "any"
DEFAULT_OUTPUT_ROOT = Path(".artifacts/pairing-support")
SERVER_PORT: Final = 8833

try:
    UTC = datetime.UTC
except AttributeError:
    UTC = timezone.utc  # noqa: UP017


@dataclass(slots=True)
class Segment:
    """One TCP payload segment captured from the local Firewalla transport."""

    seq: int
    data: bytes
    ts: float


@dataclass(slots=True)
class TranscriptEvent:
    """One redacted HTTP or TCP lifecycle event for the support bundle."""

    timestamp_utc: str
    direction: str
    kind: str
    summary: str
    content_length: int | None = None


@dataclass(slots=True)
class HttpMessage:
    """One parsed HTTP message from a reassembled port 8833 TCP stream."""

    ts: float | None
    first_line: str
    headers: dict[str, str]
    content_length: int


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Capture Firewalla pairing traffic on port 8833 and create a "
            "redacted support bundle while keeping the raw pcap local"
        )
    )
    parser.add_argument(
        "--host",
        help="SSH hostname or IP for the Firewalla box",
    )
    parser.add_argument(
        "--ssh-user",
        help="SSH username for the Firewalla box",
    )
    parser.add_argument(
        "--ssh-port",
        type=int,
        default=22,
        help="SSH port for the Firewalla box",
    )
    parser.add_argument(
        "--interface",
        default=DEFAULT_INTERFACE,
        help="Remote interface name for tcpdump",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_CAPTURE_DURATION_SECONDS,
        help="Capture duration in seconds",
    )
    parser.add_argument(
        "--filter",
        default=DEFAULT_CAPTURE_FILTER,
        help="tcpdump filter expression",
    )
    parser.add_argument(
        "--client-ip",
        help=(
            "Only include transcript events for one client IP talking to the "
            "Firewalla box on port 8833"
        ),
    )
    parser.add_argument(
        "--pairing-only",
        action="store_true",
        help=(
            "Only include pairing POST and JSON response metadata in the "
            "redacted transcript"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Artifact root for the capture outputs",
    )
    parser.add_argument(
        "--sudo",
        action="store_true",
        help="Prefix remote tcpdump commands with sudo",
    )
    parser.add_argument(
        "--keep-remote",
        action="store_true",
        help="Leave the remote pcap in /tmp after download",
    )
    return parser


def prompt(value: str | None, label: str, *, default: str | None = None) -> str:
    """Return one provided or interactively prompted value."""
    if value:
        return value

    suffix = f" [{default}]" if default is not None else ""
    raw = input(f"{label}{suffix}: ").strip()
    if raw:
        return raw
    if default is not None:
        return default
    raise RuntimeError(f"{label} is required")


def build_output_dir(root: Path) -> Path:
    """Create and return one timestamped artifact directory."""
    run_dir = root / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def format_ts(ts: float) -> str:
    """Render one timestamp in a stable UTC format."""
    return datetime.fromtimestamp(ts, UTC).isoformat()


def run_command(command: list[str]) -> None:
    """Run one subprocess command and raise on failure."""
    subprocess.run(command, check=True)


def build_ssh_target(user: str, host: str) -> str:
    """Build the SSH target string."""
    return f"{user}@{host}"


def build_remote_capture_command(
    *,
    remote_pcap: str,
    interface: str,
    duration: int,
    capture_filter: str,
    use_sudo: bool,
) -> str:
    """Build the remote shell command that captures one bounded pcap."""
    prefix = "sudo " if use_sudo else ""
    quoted_pcap = shlex.quote(remote_pcap)
    quoted_interface = shlex.quote(interface)
    quoted_filter = shlex.quote(capture_filter)
    return "sh -lc " + shlex.quote(
        "command -v tcpdump >/dev/null 2>&1 || exit 127; "
        f"rm -f {quoted_pcap}; "
        f"{prefix}tcpdump -U -i {quoted_interface} -n -s 0 "
        f"-w {quoted_pcap} {quoted_filter} >/dev/null 2>&1 & "
        "capture_pid=$!; "
        f"sleep {duration}; "
        "kill $capture_pid >/dev/null 2>&1 || true; "
        "wait $capture_pid >/dev/null 2>&1 || true"
    )


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
    """Split a byte stream into HTTP messages with timestamps and body sizes."""
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
        content_length = 0
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


def classify_transcript_message(message: HttpMessage, *, request: bool) -> str:
    """Return one compact transcript class label."""
    if request:
        if message.first_line.startswith("GET "):
            return "live_stream_get"
        if message.first_line.startswith("POST "):
            return "pairing_post"
        return "request_unknown"

    if message.headers.get("content-type", "").startswith("text/event-stream"):
        return "live_stream_response"
    if message.headers.get("content-type", "").startswith("application/json"):
        return "pairing_response"
    return "response_unknown"


def flow_direction_label(is_request: bool, peer_index: int) -> str:
    """Return a stable redacted direction label."""
    peer = f"CLIENT_{peer_index}"
    if is_request:
        return f"{peer} -> BOX"
    return f"BOX -> {peer}"


def build_transcript(
    capture_path: Path,
    *,
    client_ip: str | None = None,
    pairing_only: bool = False,
) -> list[TranscriptEvent]:
    """Build a redacted transcript from one port 8833 pcap."""
    flows: dict[tuple[str, int, str, int], list[Segment]] = defaultdict(list)
    events: list[TranscriptEvent] = []
    peer_indices: dict[str, int] = {}

    packets = rdpcap(str(capture_path))
    for packet in packets:
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
                TranscriptEvent(
                    timestamp_utc=format_ts(float(packet.time)),
                    direction=direction,
                    kind="tcp_event",
                    summary="TCP RST observed",
                )
            )
        elif flags & 0x01:
            events.append(
                TranscriptEvent(
                    timestamp_utc=format_ts(float(packet.time)),
                    direction=direction,
                    kind="tcp_event",
                    summary="TCP FIN observed",
                )
            )

        payload = bytes(tcp.payload)
        if not payload:
            continue
        flows[(ip.src, tcp.sport, ip.dst, tcp.dport)].append(
            Segment(seq=int(tcp.seq), data=payload, ts=float(packet.time))
        )

    for flow, segments in sorted(flows.items()):
        is_request = flow[3] == SERVER_PORT
        peer_ip = flow[0] if is_request else flow[2]
        peer_index = peer_indices[peer_ip]
        direction = flow_direction_label(is_request, peer_index)
        blob, offsets = reassemble(segments)
        for message in parse_http_messages(
            blob,
            offsets,
            request=is_request,
        ):
            if message.ts is None:
                continue
            message_class = classify_transcript_message(message, request=is_request)
            if pairing_only and message_class in {
                "live_stream_get",
                "live_stream_response",
            }:
                continue
            events.append(
                TranscriptEvent(
                    timestamp_utc=format_ts(message.ts),
                    direction=direction,
                    kind="http_request" if is_request else "http_response",
                    summary=f"{message.first_line} [{message_class}]",
                    content_length=message.content_length,
                )
            )

    return sorted(events, key=lambda item: item.timestamp_utc)


def build_summary(
    events: list[TranscriptEvent],
    *,
    duration_seconds: int,
    capture_filter: str,
    client_ip: str | None,
    pairing_only: bool,
) -> dict[str, object]:
    """Build a compact summary for the shareable bundle."""
    http_responses = [
        event.summary.split()[1]
        for event in events
        if event.kind == "http_response" and len(event.summary.split()) >= 2
    ]
    tcp_events = Counter(event.summary for event in events if event.kind == "tcp_event")
    return {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "capture_duration_seconds": duration_seconds,
        "capture_filter": capture_filter,
        "client_ip_filter": client_ip,
        "pairing_only": pairing_only,
        "http_request_count": sum(event.kind == "http_request" for event in events),
        "http_response_count": sum(event.kind == "http_response" for event in events),
        "http_response_status_counts": dict(Counter(http_responses)),
        "http_summary_counts": dict(
            Counter(event.summary for event in events if event.kind.startswith("http_"))
        ),
        "tcp_event_counts": dict(tcp_events),
        "notes": [
            "This redacted bundle excludes the raw pcap by default.",
            "The raw pcap may contain sensitive device and network metadata.",
            "Share only this redacted bundle unless you have agreed to send raw "
            "data privately.",
        ],
    }


def write_redacted_bundle(
    run_dir: Path,
    *,
    events: list[TranscriptEvent],
    summary: dict[str, object],
) -> Path:
    """Write the redacted files and return the bundle zip path."""
    redacted_dir = run_dir / "redacted"
    redacted_dir.mkdir(parents=True, exist_ok=False)

    (redacted_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (redacted_dir / "transcript.json").write_text(
        json.dumps([asdict(event) for event in events], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (redacted_dir / "README.txt").write_text(
        "This bundle contains only redacted HTTP metadata and TCP lifecycle "
        "events for Firewalla local port 8833.\n\n"
        "It is intended to be shareable for support. The raw pcap is stored "
        "locally in the same run directory and is not included in this zip.\n",
        encoding="utf-8",
    )

    bundle_path = run_dir / "firewalla_pairing_bundle_redacted.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(redacted_dir.iterdir()):
            bundle.write(path, arcname=path.name)
    return bundle_path


def main() -> int:
    """Capture one pairing trace and build one redacted support bundle."""
    args = build_parser().parse_args()

    if shutil.which("ssh") is None or shutil.which("scp") is None:
        raise RuntimeError("Both ssh and scp must be available on PATH")

    host = prompt(args.host, "Firewalla SSH host")
    ssh_user = prompt(args.ssh_user, "Firewalla SSH username", default="pi")

    run_dir = build_output_dir(args.output_dir)
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=False)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    remote_pcap = f"/tmp/firewalla_pairing_capture_{timestamp}.pcap"
    local_pcap = raw_dir / "firewalla_pairing_capture.pcap"
    ssh_target = build_ssh_target(ssh_user, host)

    remote_command = build_remote_capture_command(
        remote_pcap=remote_pcap,
        interface=args.interface,
        duration=args.duration,
        capture_filter=args.filter,
        use_sudo=args.sudo,
    )

    print("Capture armed. Start the pairing attempt now and do not cancel it early.")
    print(f"The capture will stop automatically after about {args.duration} seconds.")

    run_command(
        [
            "ssh",
            "-p",
            str(args.ssh_port),
            ssh_target,
            remote_command,
        ]
    )

    run_command(
        [
            "scp",
            "-P",
            str(args.ssh_port),
            f"{ssh_target}:{remote_pcap}",
            str(local_pcap),
        ]
    )

    if not args.keep_remote:
        run_command(
            [
                "ssh",
                "-p",
                str(args.ssh_port),
                ssh_target,
                f"rm -f {shlex.quote(remote_pcap)}",
            ]
        )

    events = build_transcript(
        local_pcap,
        client_ip=args.client_ip,
        pairing_only=args.pairing_only,
    )
    summary = build_summary(
        events,
        duration_seconds=args.duration,
        capture_filter=args.filter,
        client_ip=args.client_ip,
        pairing_only=args.pairing_only,
    )
    bundle_path = write_redacted_bundle(run_dir, events=events, summary=summary)

    (raw_dir / "DO_NOT_SHARE_RAW_PCAP.txt").write_text(
        "This directory contains the raw packet capture. Treat it as sensitive "
        "and do not upload it publicly. Share only the redacted zip unless you "
        "have agreed to send raw data privately.\n",
        encoding="utf-8",
    )

    print()
    print(f"Redacted support bundle: {bundle_path}")
    print(f"Raw local pcap (keep private): {local_pcap}")
    print("Share only the redacted bundle unless raw data was requested privately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
