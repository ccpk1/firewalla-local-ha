"""Decode a widened Firewalla capture: local runtime, push streams, and cloud.

Companion to ``utils/analyze_capture.py``. Where that helper focuses on the
local runtime request/response contract on port ``8833``, this helper is for
captures that also include the app's cloud and push traffic. It reports:

- **every** HTTP method on the local runtime port, not only ``POST``
- server-sent ``event:liveStats`` streams, decoded through the box key and then
  the box's own zlib layer
- TLS server-name (SNI), endpoint, and byte summaries, so cloud-only mutations
  are still visible even though TLS content stays opaque
- DNS queries and a per-port payload tally, to catch traffic that is neither
  local nor TLS

Take these captures on the box with a filter along the lines of::

    host <client-ip> and ( port 8833 or port 443 or port 80 or port 8443 or port 53 )

Usage::

    python -m utils.analyze_capture_wide <pcap> [--client-ip <ip>] [--sni-only]

The box key is read from the working ``firewalla_local`` config entry, so no
re-pairing is needed. See ``docs/REVERSE_ENGINEERING_WORKFLOW.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scapy.layers.dns import DNS, DNSQR
from scapy.layers.inet import IP, TCP, UDP
from scapy.utils import rdpcap

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.analyze_capture import (
    Segment,
    decode_body,
    load_symmetric_key,
    parse_http_messages,
    reassemble,
)

LOCAL_PORT = 8833
TLS_PORTS = {443, 8443}


def format_ts(value: float) -> str:
    """Render a packet timestamp in UTC ISO form."""
    return datetime.fromtimestamp(value, UTC).isoformat()


def dechunk(blob: bytes) -> bytes:
    """Decode a chunked transfer-encoding body into its raw bytes."""
    output = bytearray()
    index = 0
    while index < len(blob):
        line_end = blob.find(b"\r\n", index)
        if line_end < 0:
            break
        size_field = blob[index:line_end].split(b";")[0].strip()
        try:
            size = int(size_field, 16)
        except ValueError:
            break
        if size == 0:
            break
        start = line_end + 2
        output.extend(blob[start : start + size])
        index = start + size + 2
    return bytes(output)


def decode_sse(blob: bytes, key: str) -> list[tuple[str, dict[str, object] | None]]:
    """Decode an SSE stream into (event name, decoded payload) pairs.

    The box wraps each event as ``event:liveStats`` plus an AES-256-CBC base64
    ``data:`` line. The decrypted JSON is a small envelope
    ``{"compressed": 1, "payload": "<base64 zlib>"}``, so a second base64 and
    zlib pass is required to reach the real payload.
    """
    from custom_components.firewalla_local.api import crypto

    events: list[tuple[str, dict[str, object] | None]] = []
    for block in dechunk(blob).split(b"\n\n"):
        event_name = ""
        payload_b64 = ""
        for line in block.split(b"\n"):
            if line.startswith(b"event:"):
                event_name = line[len(b"event:") :].decode("latin1").strip()
            elif line.startswith(b"data:"):
                payload_b64 = line[len(b"data:") :].decode("latin1").strip()
        if not payload_b64:
            continue
        decoded: dict[str, object] | None = None
        try:
            plaintext = crypto.aes256_cbc_decrypt_from_base64(payload_b64, key)
            parsed = json.loads(plaintext)
        except ValueError, json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            decoded = parsed
            inner = parsed.get("payload")
            if parsed.get("compressed") and isinstance(inner, str):
                import base64
                import zlib

                try:
                    inflated = zlib.decompress(base64.b64decode(inner))
                    unpacked = json.loads(inflated)
                except ValueError, zlib.error:
                    unpacked = None
                if isinstance(unpacked, dict):
                    decoded = unpacked
        events.append((event_name, decoded))
    return events


def extract_sni(blob: bytes) -> str | None:
    """Extract the SNI hostname from a TLS ClientHello byte stream."""
    if len(blob) < 44 or blob[0] != 0x16 or blob[5] != 0x01:
        return None
    pos = 9 + 2 + 32  # record + handshake header, then version + random
    if pos >= len(blob):
        return None
    pos += 1 + blob[pos]  # session id
    if pos + 2 > len(blob):
        return None
    pos += 2 + int.from_bytes(blob[pos : pos + 2], "big")  # cipher suites
    if pos >= len(blob):
        return None
    pos += 1 + blob[pos]  # compression methods
    if pos + 2 > len(blob):
        return None
    end = min(pos + 2 + int.from_bytes(blob[pos : pos + 2], "big"), len(blob))
    pos += 2
    while pos + 4 <= end:
        ext_type = int.from_bytes(blob[pos : pos + 2], "big")
        ext_len = int.from_bytes(blob[pos + 2 : pos + 4], "big")
        body = pos + 4
        if ext_type == 0x0000:
            name_len = int.from_bytes(blob[body + 3 : body + 5], "big")
            return blob[body + 5 : body + 5 + name_len].decode("latin1", "ignore")
        pos = body + ext_len
    return None


def collect_flows(
    pcap: Path, client_ip: str | None
) -> tuple[
    dict[tuple[str, int, str, int], list[Segment]],
    list[tuple[float, str, str]],
    list[float],
]:
    """Bucket a pcap into TCP flows, DNS queries, and packet times."""
    flows: dict[tuple[str, int, str, int], list[Segment]] = defaultdict(list)
    dns_queries: list[tuple[float, str, str]] = []
    times: list[float] = []
    for packet in rdpcap(str(pcap)):
        if IP not in packet:
            continue
        ip = packet[IP]
        times.append(float(packet.time))
        if client_ip and client_ip not in (ip.src, ip.dst):
            continue
        if UDP in packet and DNS in packet and packet[DNS].qr == 0:
            question = packet[DNSQR]
            if question is not None:
                name = question.qname.decode("latin1", "ignore").rstrip(".")
                dns_queries.append((float(packet.time), name, ip.dst))
            continue
        if TCP not in packet:
            continue
        tcp = packet[TCP]
        payload = bytes(tcp.payload)
        if not payload:
            continue
        flows[(ip.src, int(tcp.sport), ip.dst, int(tcp.dport))].append(
            Segment(seq=int(tcp.seq), data=payload, ts=float(packet.time))
        )
    return flows, dns_queries, times


def print_local_runtime(
    flows: dict[tuple[str, int, str, int], list[Segment]], key: str
) -> None:
    """Print every local-runtime HTTP message and decoded SSE summary."""
    print(f"\n### LOCAL RUNTIME (port {LOCAL_PORT})")
    local = {
        flow: segments
        for flow, segments in flows.items()
        if LOCAL_PORT in (flow[1], flow[3])
    }
    if not local:
        print("  (no local runtime flows — the action may be cloud-only)")
        return
    for flow, segments in sorted(local.items()):
        is_request = flow[3] == LOCAL_PORT
        blob, offsets = reassemble(segments)
        if not is_request:
            header_end = blob.find(b"\r\n\r\n")
            header = blob[:header_end].decode("latin1", "ignore")
            if "event-stream" in header:
                events = decode_sse(blob[header_end + 4 :], key)
                counts: dict[str, int] = defaultdict(int)
                samples: dict[str, str] = {}
                undecoded = 0
                for name, payload in events:
                    counts[name] += 1
                    if payload is None:
                        undecoded += 1
                    elif name not in samples:
                        samples[name] = json.dumps(payload, sort_keys=True)[:180]
                if events:
                    print(
                        f"  SSE {flow[0]}:{flow[1]} -> {flow[2]}:{flow[3]} "
                        f"events={dict(counts)} undecoded={undecoded}"
                    )
                    for name, sample in samples.items():
                        print(f"      {name} sample={sample}")
                continue
        for message in parse_http_messages(blob, offsets, request=is_request):
            if not message.first_line:
                continue
            method, _, rest = message.first_line.partition(" ")
            path = rest.split(" ")[0].split("?")[0]
            try:
                decoded = decode_body(message.body, key)
            except ValueError:
                decoded = None
            if decoded is None:
                print(f"  {format_ts(message.ts or 0)} {method} {path}")
                continue
            obj = decoded.get("message", {})
            inner = obj.get("obj") if isinstance(obj, dict) else None
            inner = inner if isinstance(inner, dict) else {}
            data = inner.get("data")
            if isinstance(data, dict) and data.get("item") == "batchAction":
                print(f"  {format_ts(message.ts or 0)} {method} {path} batchAction:")
                for step in data.get("value", []):
                    if not isinstance(step, dict):
                        continue
                    step_data = step.get("data") or {}
                    value = step_data.get("value")
                    if step_data.get("item") == "policy" and isinstance(value, dict):
                        picked = {
                            key: value.get(key)
                            for key in ("tags", "userTags")
                            if key in value
                        }
                        print(
                            f"      {step.get('mtype')} policy "
                            f"target={step.get('target')} {picked}"
                        )
                    else:
                        print(
                            f"      {step.get('mtype')} {step_data.get('item')} "
                            f"value={json.dumps(value, sort_keys=True)[:110]}"
                        )
                continue
            print(
                f"  {format_ts(message.ts or 0)} {method} {path} "
                f"mtype={inner.get('mtype')} target={inner.get('target')} "
                f"data={json.dumps(data, sort_keys=True)[:170]}"
            )


def print_tls(flows: dict[tuple[str, int, str, int], list[Segment]]) -> None:
    """Print TLS client-hello endpoints, SNI, and byte totals."""
    print("\n### TLS FLOWS (SNI / endpoint)")
    servers: dict[tuple[str, int], dict[str, object]] = {}
    for (src, sport, dst, dport), segments in sorted(flows.items()):
        if not TLS_PORTS & {sport, dport}:
            continue
        blob, _ = reassemble(segments)
        sni = extract_sni(blob) if dport in TLS_PORTS and blob[:1] == b"\x16" else None
        server = (dst, dport) if dport in TLS_PORTS else (src, sport)
        times = [segment.ts for segment in segments]
        entry = servers.setdefault(
            server,
            {"sni": sni, "bytes": 0, "first": min(times), "last": max(times)},
        )
        entry["bytes"] = int(entry["bytes"]) + len(blob)
        entry["first"] = min(float(entry["first"]), min(times))
        entry["last"] = max(float(entry["last"]), max(times))
        if sni:
            entry["sni"] = sni
    if not servers:
        print("  (no TLS client-hello flows)")
    for (host, port), info in sorted(
        servers.items(), key=lambda item: item[1]["first"]
    ):
        print(
            f"  {host}:{port} sni={info['sni'] or '<none>'} "
            f"bytes={info['bytes']} {format_ts(float(info['first']))} -> "
            f"{format_ts(float(info['last']))}"
        )


def print_dns(queries: list[tuple[float, str, str]]) -> None:
    """Print captured DNS questions."""
    print("\n### DNS QUERIES")
    if not queries:
        print("  (none captured)")
    for when, name, server in sorted(queries):
        print(f"  {format_ts(when)} {name} -> {server}")


def main() -> None:
    """Decode a widened capture and print the four evidence sections."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_path", type=Path, help="Path to the .pcap file")
    parser.add_argument("--client-ip", help="Only analyze flows for this client IP")
    parser.add_argument(
        "--sni-only",
        action="store_true",
        help="Print only the TLS SNI/endpoint section",
    )
    args = parser.parse_args()

    flows, dns_queries, times = collect_flows(args.capture_path, args.client_ip)
    if not times:
        print("No IP packets found for the selected filter")
        return

    print("=" * 72)
    print(f"CAPTURE {args.capture_path}")
    print(f"WINDOW  {format_ts(min(times))} -> {format_ts(max(times))}")
    print(f"PACKETS {len(times)}")
    print("=" * 72)

    print_tls(flows)
    if args.sni_only:
        return

    print_local_runtime(flows, load_symmetric_key())
    print_dns(dns_queries)


if __name__ == "__main__":
    main()
