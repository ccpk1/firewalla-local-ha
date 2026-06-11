# Windows Firewalla packet capture

Copy these three files into the same folder on the Windows machine:

- `capture_firewalla_packets.py`
- `capture_firewalla_packets_requirements.txt`
- `run_capture_firewalla_packets.bat`

Then open Command Prompt in that folder and run one capture command at a time.

## Quick start — one capture, key, and decoded analysis

This workflow captures a phone pairing, saves the box-level symmetric key, and
produces a shareable redacted report of the decrypted message structure.

**Before you start:** Enable SSH Console in your Firewalla mobile app
(Settings > Advanced > Configurations > SSH Console) and note the password.

### Step 1 — Save the QR JSON to a file

Open the Firewalla app on your phone. Go to Settings > Advanced > Allow
Additional Pairing. A QR code appears. Use your phone's text recognition to
copy the raw JSON content and save it to a file named `qr.txt` in the capture
folder.

### Step 2 — Start the capture

Open Command Prompt in the capture folder and run:

```bat
run_capture_firewalla_packets.bat --host fire.walla --label phone --client-ip <phone-ip> --qr-file qr.txt --email 'your@email.com'
```

Replace `<phone-ip>` with your phone's IP address on your local network.

The script will:
1. Ask for the Firewalla SSH password
2. Run cloud provisioning to obtain the box-level symmetric key (saves as `.key`)
3. Start tcpdump on the Firewalla box
4. Wait for you to perform the pairing

### Step 3 — Generate a fresh QR and pair your phone

The QR code used for provisioning is now consumed. While the capture is
running and waiting, generate a **fresh** QR code:

1. Toggle "Allow Additional Pairing" OFF, then ON again in the Firewalla app
2. Scan the new QR code with your phone to complete the pairing
3. The phone's traffic is now being captured

### Step 4 — Stop the capture

After the phone finishes pairing, press **Enter** in the Command Prompt window.
The script stops tcpdump, downloads the pcap, and creates:
- `firewalla_capture_...pcap` — the raw network capture
- `provisioning_key_....key` — the symmetric key (can decrypt this pcap)
- Safe report zip — HTTP metadata only, no decrypted content

### Step 5 — Decode and inspect the phone's messages

Decrypt the pcap using the saved key to see what the phone sent:

```bat
python capture_firewalla_packets.py --decode firewalla_capture_...pcap --key-file provisioning_key_....key
```

This prints every decrypted HTTP request and response — the full message
structure the phone used during pairing.

### Step 6 — Share a redacted report (no sensitive data)

To share the analysis without exposing credential values:

```bat
python capture_firewalla_packets.py --decode firewalla_capture_...pcap --key-file provisioning_key_....key --redacted-report analysis.json
```

This replaces credential fields (`eid`, `aid`, `gid`, tokens, UUIDs) with
`<redacted>` while preserving the full message structure. Share the
`analysis.json` file — no keys, IPs, or network metadata included.

---

## Alternative: basic troubleshooting with safe reports only

If you only need to share HTTP-level metadata (request counts, response status
codes, content lengths) without decrypting payloads, you can skip the QR
provisioning step and use `--client-ip` only:

```bat
run_capture_firewalla_packets.bat --host fire.walla --label phone --client-ip 192.168.202.173
```

This produces a safe report zip with HTTP metadata and TCP events, but no key
file. The raw pcap stays on your machine.

---

## What the batch file does

- creates a local virtual environment in `.venv_firewalla_capture`
- installs `paramiko`, `scp`, `scapy`, `aiohttp`, and `cryptography`
- optionally runs cloud provisioning to capture the symmetric key
- runs the Windows Firewalla packet capture helper
- builds a local safe report zip from cleartext HTTP metadata and TCP lifecycle
  events

The capture file is saved in the folder where the batch file is running, with a
name like `firewalla_capture_YYYYMMDD-HHMMSS.pcap`.

The provisioning key file (when `--qr-file` is used) is saved alongside the
pcap with a name like `provisioning_key_YYYYMMDD_HHMMSS.key`. Keep this file
private — it can decrypt the pcap. Only share it with the raw pcap privately.

The safe report zip is saved in the same folder, with a name like
`firewalla_capture_YYYYMMDD-HHMMSS_phone-success_safe_report.zip`.

---

## Notes

- The SSH username is hardcoded as `pi`
- The SSH port is hardcoded as `22`
- You will be prompted for the SSH password
- `--host` can be either `fire.walla` or the Firewalla box IP address
- `--label` is optional but recommended so output files clearly identify the
  capture purpose
- `--client-ip` is optional and limits the remote `tcpdump` to the client IP
  you want to monitor
- Use `--qr-file` instead of `--qr-json` on Windows to avoid shell quoting
  issues with the JSON payload
- The provisioning step consumes the QR code — generate a fresh one for the
  actual phone pairing (Step 3)
- The symmetric key is per-box, not per-client. The key from any provisioning
  session decrypts all traffic to that box
- The safe report includes cleartext metadata such as request lines, response
  status lines, selected headers like `User-Agent`, content lengths, and TCP
  disconnect events
- The safe report does not decrypt payloads and does not include the raw `.pcap`
- The raw `.pcap` may contain sensitive device and network information