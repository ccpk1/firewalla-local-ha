"""Decode Firewalla local port 8833 packet captures.

This helper is for reverse-engineering work when a fresh runtime pull is not
enough and the exact encrypted request or response sequence matters.

It reads a `.pcap` capture containing local Firewalla traffic on port `8833`,
reassembles TCP segments into HTTP messages, loads the active
`firewalla_local` symmetric key from the Home Assistant development config, and
prints decrypted request and response previews.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scapy.layers.inet import IP, TCP
from scapy.utils import rdpcap

sys.path.insert(0, "/workspaces/firewalla-local-ha")


DEFAULT_PCAP_PATH = Path(
    "/workspaces/firewalla-local-ha/.tmp/firewalla_mutation_capture.pcap"
)
CONFIG_PATH = Path("/workspaces/core/config/.storage/core.config_entries")
SERVER_PORT = 8833


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
    body: bytes


def load_symmetric_key() -> str:
    """Return the active Firewalla symmetric key from Home Assistant storage."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for entry in config["data"]["entries"]:
        if entry.get("domain") != "firewalla_local":
            continue
        data = entry.get("data")
        if isinstance(data, dict) and isinstance(data.get("symmetric_key"), str):
            return data["symmetric_key"]
    raise RuntimeError("No firewalla_local symmetric key found")


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
    """Split a byte stream into HTTP messages with timestamps and bodies."""
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
                body=body,
            )
        )
        index = body_end

    return parsed


def classify_request(message: HttpMessage, decoded: dict[str, object] | None) -> str:
    """Classify one request into a stable pairing-analysis bucket."""
    if message.first_line.startswith("GET "):
        return "live_stream_get"

    if not decoded:
        return "post_unknown"

    obj = decoded.get("message", {}).get("obj", {})
    if not isinstance(obj, dict):
        return "post_unknown"

    match obj.get("mtype"):
        case "init":
            return "pairing_init"
        case "cmd":
            return "command_post"
        case _:
            return "post_unknown"


def classify_response(message: HttpMessage, decoded: dict[str, object] | None) -> str:
    """Classify one response into a stable pairing-analysis bucket."""
    content_type = message.headers.get("content-type", "")
    if content_type.startswith("text/event-stream"):
        return "live_stream_response"
    if content_type.startswith("application/json") and decoded is not None:
        return "json_response"
    if content_type.startswith("application/json"):
        return "json_response_undecoded"
    return "response_unknown"


def header_summary(message: HttpMessage, *, request: bool) -> str:
    """Return a compact header summary for pairing comparisons."""
    if request:
        parts: list[str] = []
        if user_agent := message.headers.get("user-agent"):
            parts.append(f"user_agent={user_agent}")
        if content_length := message.headers.get("content-length"):
            parts.append(f"content_length={content_length}")
        if content_type := message.headers.get("content-type"):
            parts.append(f"content_type={content_type}")
        return " ".join(parts)

    parts = []
    if content_type := message.headers.get("content-type"):
        parts.append(f"content_type={content_type}")
    if content_length := message.headers.get("content-length"):
        parts.append(f"content_length={content_length}")
    return " ".join(parts)


def format_elapsed(base_ts: float | None, ts: float | None) -> str:
    """Render elapsed time from the first visible message."""
    if base_ts is None or ts is None:
        return "elapsed=unknown"
    return f"elapsed=+{ts - base_ts:.3f}s"


def flow_peer_key(flow: tuple[str, int, str, int], *, request: bool) -> tuple[str, int]:
    """Return a stable client endpoint key for one parsed flow."""
    if request:
        return (flow[0], flow[1])
    return (flow[2], flow[3])


def decode_body(body: bytes, key: str) -> dict[str, object] | None:
    """Decrypt one Firewalla HTTP message body using the active symmetric key."""
    try:
        payload = json.loads(body.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    message = payload.get("message")
    if isinstance(message, dict):
        return payload
    if not isinstance(message, str):
        return None
    crypto_module = importlib.import_module(
        "custom_components.firewalla_local.api.crypto"
    )
    plaintext = crypto_module.aes256_cbc_decrypt_from_base64(message, key)
    decoded = json.loads(plaintext)
    if not isinstance(decoded, dict):
        return None
    return decoded


def format_ts(ts: float | None) -> str:
    """Render one packet timestamp in a stable UTC format."""
    if ts is None:
        return "unknown"
    return datetime.fromtimestamp(ts, UTC).isoformat()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Decode a Firewalla local port 8833 packet capture using the active "
            "Home Assistant symmetric key"
        )
    )
    parser.add_argument(
        "capture_path",
        nargs="?",
        type=Path,
        default=DEFAULT_PCAP_PATH,
        help="Path to the .pcap file to decode",
    )
    parser.add_argument(
        "--client-ip",
        help=(
            "Only decode flows for one specific client IP talking to the "
            "Firewalla box on port 8833"
        ),
    )
    parser.add_argument(
        "--pairing-only",
        action="store_true",
        help=(
            "Suppress live-stream GET and text/event-stream traffic so the "
            "output stays focused on pairing POST traffic"
        ),
    )
    return parser


def main() -> None:
    """Decode and print packet-capture message previews for local analysis."""
    args = build_parser().parse_args()
    capture_path = args.capture_path.resolve()
    key = load_symmetric_key()
    flows: dict[tuple[str, int, str, int], list[Segment]] = defaultdict(list)
    matched_payload_packets = 0
    for packet in rdpcap(str(capture_path)):
        if IP not in packet or TCP not in packet:
            continue
        ip = packet[IP]
        tcp = packet[TCP]
        if tcp.sport != SERVER_PORT and tcp.dport != SERVER_PORT:
            continue
        peer_ip = ip.src if tcp.dport == SERVER_PORT else ip.dst
        if args.client_ip and peer_ip != args.client_ip:
            continue
        payload = bytes(tcp.payload)
        if not payload:
            continue
        matched_payload_packets += 1
        flows[(ip.src, tcp.sport, ip.dst, tcp.dport)].append(
            Segment(seq=int(tcp.seq), data=payload, ts=float(packet.time))
        )

    if args.client_ip:
        print(f"FILTER client_ip={args.client_ip}")
    if args.pairing_only:
        print("FILTER pairing_only=true")

    if matched_payload_packets == 0:
        if args.client_ip:
            print(
                "No matching payload-bearing port 8833 flows were found for "
                f"client {args.client_ip}"
            )
            return
        print("No payload-bearing port 8833 flows were found")
        return

    parsed_flows: list[tuple[tuple[str, int, str, int], bool, list[HttpMessage]]] = []
    base_ts: float | None = None
    request_started_at: dict[tuple[str, int], float] = {}

    for flow, segments in sorted(flows.items()):
        blob, offsets = reassemble(segments)
        is_request = flow[3] == SERVER_PORT
        messages = parse_http_messages(blob, offsets, request=is_request)
        if not messages:
            continue
        parsed_flows.append((flow, is_request, messages))
        for message in messages:
            if message.ts is None:
                continue
            if base_ts is None or message.ts < base_ts:
                base_ts = message.ts
            if is_request:
                peer_key = flow_peer_key(flow, request=True)
                request_started_at.setdefault(peer_key, message.ts)

    printed_any = False
    for flow, is_request, messages in parsed_flows:
        direction = "request" if is_request else "response"
        peer_key = flow_peer_key(flow, request=is_request)
        flow_header_printed = False
        for message in messages[:40]:
            try:
                decoded = decode_body(message.body, key)
            except ValueError as err:
                request_class = classify_request(message, None) if is_request else ""
                response_class = (
                    classify_response(message, None) if not is_request else ""
                )
                if args.pairing_only and (
                    request_class == "live_stream_get"
                    or response_class == "live_stream_response"
                ):
                    continue
                if not flow_header_printed:
                    print(
                        f"FLOW {direction} {flow[0]}:{flow[1]} -> "
                        f"{flow[2]}:{flow[3]} count={len(messages)}"
                    )
                    flow_header_printed = True
                printed_any = True
                print(
                    f"  {format_ts(message.ts)} {message.first_line} "
                    f"{format_elapsed(base_ts, message.ts)} "
                    f"decode_error={type(err).__name__}: {err}"
                )
                continue

            if is_request:
                request_class = classify_request(message, decoded)
                if args.pairing_only and request_class == "live_stream_get":
                    continue
                if not flow_header_printed:
                    print(
                        f"FLOW {direction} {flow[0]}:{flow[1]} -> "
                        f"{flow[2]}:{flow[3]} count={len(messages)}"
                    )
                    flow_header_printed = True
                printed_any = True
                if request_class == "live_stream_get":
                    print(
                        f"  {format_ts(message.ts)} {message.first_line} "
                        f"{format_elapsed(base_ts, message.ts)} class={request_class}"
                    )
                    continue

                obj = decoded.get("message", {}).get("obj", {}) if decoded else {}
                if not isinstance(obj, dict):
                    print(
                        f"  {format_ts(message.ts)} {message.first_line} "
                        f"{format_elapsed(base_ts, message.ts)} class={request_class} "
                        "request_missing_obj"
                    )
                    continue
                print(
                    f"  {format_ts(message.ts)} {message.first_line} "
                    f"{format_elapsed(base_ts, message.ts)} class={request_class} "
                    f"mtype={obj.get('mtype')} target={obj.get('target')}"
                )
                if summary := header_summary(message, request=True):
                    print(f"     headers={summary}")
                print(f"     data={json.dumps(obj.get('data'), sort_keys=True)[:800]}")
                continue

            response_class = classify_response(message, decoded)
            if args.pairing_only and response_class == "live_stream_response":
                continue
            if not flow_header_printed:
                print(
                    f"FLOW {direction} {flow[0]}:{flow[1]} -> "
                    f"{flow[2]}:{flow[3]} count={len(messages)}"
                )
                flow_header_printed = True
            printed_any = True

            latency_note = ""
            if message.ts is not None and (
                request_ts := request_started_at.get(peer_key)
            ):
                latency_note = f" latency={message.ts - request_ts:.3f}s"
            if response_class == "live_stream_response":
                print(
                    f"  {format_ts(message.ts)} {message.first_line} "
                    f"{format_elapsed(base_ts, message.ts)} class={response_class}"
                    f"{latency_note}"
                )
                if summary := header_summary(message, request=False):
                    print(f"     headers={summary}")
                continue

            if decoded is None:
                print(
                    f"  {format_ts(message.ts)} {message.first_line} "
                    f"{format_elapsed(base_ts, message.ts)} class={response_class}"
                    f"{latency_note} undecodable"
                )
                if summary := header_summary(message, request=False):
                    print(f"     headers={summary}")
                continue

            data = decoded.get("data")
            preview = data
            if isinstance(data, dict):
                preview = {key: data[key] for key in list(data)[:8]}
            print(
                f"  {format_ts(message.ts)} {message.first_line} "
                f"{format_elapsed(base_ts, message.ts)} class={response_class}"
                f"{latency_note} code={decoded.get('code')}"
            )
            if summary := header_summary(message, request=False):
                print(f"     headers={summary}")
            print(f"     data={json.dumps(preview, sort_keys=True)[:800]}")

    if args.pairing_only and not printed_any:
        print("No pairing-focused HTTP messages were found for the selected filters")


if __name__ == "__main__":
    main()
