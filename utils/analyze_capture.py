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
) -> list[tuple[float | None, str, bytes]]:
    """Split a byte stream into HTTP messages with timestamps and bodies."""
    marker = b"POST " if request else b"HTTP/1.1 "
    index = 0
    parsed: list[tuple[float | None, str, bytes]] = []
    while True:
        start = blob.find(marker, index)
        if start < 0:
            break
        header_end = blob.find(b"\r\n\r\n", start)
        if header_end < 0:
            break

        header = blob[start:header_end].decode("latin1", errors="ignore")
        first_line, *rest = header.split("\r\n")
        content_length = 0
        for line in rest:
            name, _, value = line.partition(":")
            if name.lower() != "content-length":
                continue
            try:
                content_length = int(value.strip())
            except ValueError:
                content_length = 0
            break

        body_start = header_end + 4
        body_end = body_start + content_length
        body = blob[body_start:body_end]
        if len(body) < content_length:
            break

        parsed.append((ts_for_offset(offsets, start), first_line, body))
        index = body_end

    return parsed


def decode_body(body: bytes, key: str) -> dict[str, object] | None:
    """Decrypt one Firewalla HTTP message body using the active symmetric key."""
    try:
        payload = json.loads(body.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    message = payload.get("message")
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
    return parser


def main() -> None:
    """Decode and print packet-capture message previews for local analysis."""
    args = build_parser().parse_args()
    capture_path = args.capture_path.resolve()
    key = load_symmetric_key()
    flows: dict[tuple[str, int, str, int], list[Segment]] = defaultdict(list)
    for packet in rdpcap(str(capture_path)):
        if IP not in packet or TCP not in packet:
            continue
        ip = packet[IP]
        tcp = packet[TCP]
        if tcp.sport != SERVER_PORT and tcp.dport != SERVER_PORT:
            continue
        payload = bytes(tcp.payload)
        if not payload:
            continue
        flows[(ip.src, tcp.sport, ip.dst, tcp.dport)].append(
            Segment(seq=int(tcp.seq), data=payload, ts=float(packet.time))
        )

    for flow, segments in sorted(flows.items()):
        blob, offsets = reassemble(segments)
        is_request = flow[3] == SERVER_PORT
        messages = parse_http_messages(blob, offsets, request=is_request)
        if not messages:
            continue
        direction = "request" if is_request else "response"
        print(
            f"FLOW {direction} {flow[0]}:{flow[1]} -> "
            f"{flow[2]}:{flow[3]} count={len(messages)}"
        )
        for ts, first_line, body in messages[:40]:
            try:
                decoded = decode_body(body, key)
            except ValueError as err:
                print(
                    f"  {format_ts(ts)} {first_line} "
                    f"decode_error={type(err).__name__}: {err}"
                )
                continue
            if decoded is None:
                print(f"  {format_ts(ts)} {first_line} undecodable")
                continue

            if is_request:
                obj = decoded.get("message", {}).get("obj", {})
                if not isinstance(obj, dict):
                    print(f"  {format_ts(ts)} {first_line} request_missing_obj")
                    continue
                print(
                    f"  {format_ts(ts)} {first_line} "
                    f"mtype={obj.get('mtype')} target={obj.get('target')}"
                )
                print(f"     data={json.dumps(obj.get('data'), sort_keys=True)[:800]}")
                continue

            data = decoded.get("data")
            preview = data
            if isinstance(data, dict):
                preview = {key: data[key] for key in list(data)[:8]}
            print(f"  {format_ts(ts)} {first_line} code={decoded.get('code')}")
            print(f"     data={json.dumps(preview, sort_keys=True)[:800]}")


if __name__ == "__main__":
    main()
