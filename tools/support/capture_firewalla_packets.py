"""Windows helper to capture Firewalla packets over SSH.

This support tool is intentionally narrow:

- prompt for router IP address or hostname and SSH password
- SSH to the Firewalla box as user ``pi`` on port ``22``
- start a remote tcpdump capture in the background
- wait for the user to reproduce the behavior they want to capture
- stop the capture, download the pcap, and clean up remote files

It does not perform any packet parsing, decryption, or redaction.
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import sys
import time
from contextlib import suppress
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

if TYPE_CHECKING:
    from paramiko import SSHClient


SSH_PORT: Final = 22
SSH_USER: Final = "pi"
REMOTE_PCAP_PATH: Final = "/tmp/firewalla_capture.pcap"
REMOTE_PID_PATH: Final = "/tmp/firewalla_capture.pid"
DEFAULT_CONNECT_TIMEOUT: Final = 10.0
DEFAULT_CAPTURE_FILTER: Final = "tcp port 8833"


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


def build_local_capture_path(output_dir: Path) -> Path:
    """Return one timestamped local output path for the downloaded pcap."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return output_dir / f"firewalla_capture_{timestamp}.pcap"


def build_capture_filter(client_ip: str | None) -> str:
    """Return the tcpdump filter for the requested capture scope."""
    if not client_ip:
        return DEFAULT_CAPTURE_FILTER

    validated_ip = ipaddress.ip_address(client_ip)
    return f"{DEFAULT_CAPTURE_FILTER} and host {validated_ip}"


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
    local_capture_path = build_local_capture_path(args.output_dir)

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

        print()
        print(f"Success. Capture saved to: {local_capture_path}")
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
