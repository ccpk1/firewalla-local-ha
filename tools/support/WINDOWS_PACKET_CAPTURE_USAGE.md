# Windows Firewalla packet capture

Copy these three files into the same folder on the Windows machine:

- `capture_firewalla_packets.py`
- `capture_firewalla_packets_requirements.txt`
- `run_capture_firewalla_packets.bat`

Then open Command Prompt in that folder and run:

```bat
run_capture_firewalla_packets.bat --host fire.walla
```

If `fire.walla` does not resolve correctly in that environment, use the router IP
address instead:

```bat
run_capture_firewalla_packets.bat --host 192.168.202.1
```

If you know the client IP involved in the traffic you want to observe, reduce
noise in the raw capture with `--client-ip`:

```bat
run_capture_firewalla_packets.bat --host fire.walla --client-ip 192.168.202.173
```

You can also use a router IP in the same command:

```bat
run_capture_firewalla_packets.bat --host 192.168.202.1 --client-ip 192.168.202.173
```

What the batch file does:

- creates a local virtual environment in `.venv_firewalla_capture`
- installs `paramiko` and `scp`
- runs the Windows Firewalla packet capture helper

The capture file is saved in the folder where the batch file is running, with a
name like `firewalla_capture_YYYYMMDD-HHMMSS.pcap`.

Notes:

- The SSH username is hardcoded as `pi`
- The SSH port is hardcoded as `22`
- You will be prompted for the SSH password
- `--host` can be either `fire.walla` or the Firewalla box IP address
- `--client-ip` is optional and limits the remote `tcpdump` to the client IP
  you want to monitor
- When pairing from the Firewalla mobile app, `--client-ip` should be the phone
  IP address of the device doing the pairing
- When monitoring Home Assistant traffic instead, `--client-ip` should be the
  IP address of the Home Assistant instance
- The helper currently captures `tcp port 8833`, optionally narrowed to one
  client IP
- The raw `.pcap` may contain sensitive device and network information