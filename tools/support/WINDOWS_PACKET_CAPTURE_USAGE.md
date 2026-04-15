# Windows Firewalla packet capture

Copy these three files into the same folder on the Windows machine:

- `capture_firewalla_packets.py`
- `capture_firewalla_packets_requirements.txt`
- `run_capture_firewalla_packets.bat`

Then open Command Prompt in that folder and run one capture command at a time.

Before you worry about packet capture, first update to the latest Firewalla
Local build and try pairing again. The pairing process was reworked to match
the native Firewalla app flow more closely, and many users should not need a
capture after updating.

Recommended troubleshooting workflow:

1. Update to the latest Firewalla Local build and try pairing again first.
2. If pairing still fails, capture one successful phone pairing in the same
  environment.
3. Capture one Home Assistant pairing attempt from the updated integration.
4. Copy the relevant Home Assistant pairing log lines from that Home Assistant
  attempt.
5. Share the two safe report zip files and the Home Assistant log lines.
6. Keep the raw `.pcap` files private unless you are explicitly asked to share
  them privately.

For most users, the full capture workflow should take around 10 minutes.
The safe report zip is generated locally on your side so you can share the
comparison data without uploading the raw packet capture by default.

Recommended successful phone capture:

```bat
run_capture_firewalla_packets.bat --host fire.walla --label phone-success
```

Recommended Home Assistant capture:

```bat
run_capture_firewalla_packets.bat --host fire.walla --label home-assistant-attempt
```

If you know the client IP for the device involved in the capture, include it to
reduce noise.

Example successful phone capture with a phone IP filter:

```bat
run_capture_firewalla_packets.bat --host fire.walla --label phone-success --client-ip 192.168.202.173
```

If `fire.walla` does not resolve correctly in that environment, use the router IP
address instead:

```bat
run_capture_firewalla_packets.bat --host 192.168.202.1 --label phone-success
```

Example Home Assistant capture with a Home Assistant IP filter:

```bat
run_capture_firewalla_packets.bat --host fire.walla --label home-assistant-attempt --client-ip 192.168.202.220
```

You can also use a router IP in the same command:

```bat
run_capture_firewalla_packets.bat --host 192.168.202.1 --label home-assistant-attempt --client-ip 192.168.202.220
```

What the batch file does:

- creates a local virtual environment in `.venv_firewalla_capture`
- installs `paramiko`, `scp`, and `scapy`
- runs the Windows Firewalla packet capture helper
- builds a local safe report zip from cleartext HTTP metadata and TCP lifecycle
  events

The capture file is saved in the folder where the batch file is running, with a
name like `firewalla_capture_YYYYMMDD-HHMMSS.pcap`.

The safe report zip is saved in the same folder, with a name like
`firewalla_capture_YYYYMMDD-HHMMSS_phone-success_safe_report.zip`.

Notes:

- The SSH username is hardcoded as `pi`
- The SSH port is hardcoded as `22`
- You will be prompted for the SSH password
- `--host` can be either `fire.walla` or the Firewalla box IP address
- `--label` is optional but recommended so the output files clearly identify the
  successful phone capture versus the Home Assistant capture
- `--client-ip` is optional and limits the remote `tcpdump` to the client IP
  you want to monitor
- When pairing from the Firewalla mobile app, `--client-ip` should be the phone
  IP address of the device doing the pairing
- When monitoring Home Assistant traffic instead, `--client-ip` should be the
  IP address of the Home Assistant instance
- The helper currently captures `tcp port 8833`, optionally narrowed to one
  client IP
- The safe report includes cleartext metadata such as request lines, response
  status lines, selected headers like `User-Agent`, content lengths, and TCP
  disconnect events
- The safe report also summarizes connection reuse, request method order,
  response status order, repeated `412` responses, and whether live-stream
  traffic was observed
- The safe report does not decrypt payloads and does not include the raw `.pcap`
- The raw `.pcap` may contain sensitive device and network information