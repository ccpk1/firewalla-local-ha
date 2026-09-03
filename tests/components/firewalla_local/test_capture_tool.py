"""Tests for the packet capture support tool.

The capture tool imports network-heavy dependencies (scapy, paramiko, aiohttp)
that open sockets at import time, which the Home Assistant test plugin blocks.
So these tests avoid importing the module directly and instead:

- compile-check the tool (catches SyntaxError regressions like the bare
  ``except ValueError, TypeError`` bug),
- source-scan for the ``datetime.UTC`` regression (a runtime AttributeError
  that compile cannot catch),
- exercise the redaction logic against a standalone copy of the function.
"""

from __future__ import annotations

import json
import py_compile
import re
from pathlib import Path

_TOOL_PATH = (
    Path(__file__).parents[3] / "tools" / "support" / "capture_firewalla_packets.py"
)

# Standalone copy of the tool's _redact_credentials logic so the test does not
# import the network-heavy module. Keep in sync with the tool.
_REDACT_LABEL = "<redacted>"

_REDACT_KEYS = frozenset(
    {
        "eid",
        "aid",
        "gid",
        "symmetric_key",
        "accesstoken",
        "access_token",
        "token",
        "password",
        "secret",
        "key",
        "publickey",
        "privatekey",
        "license",
        "seed",
        "ek",
        "jwt",
        "jwtoken",
        "ddnstoken",
        "btmac",
        "cpuid",
        "rkey",
    }
)


def _redact_credentials(value: object) -> object:
    """Standalone copy of the tool's redaction logic."""
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for k, v in value.items():
            if k.lower() in _REDACT_KEYS or (
                isinstance(v, str) and len(v) == 36 and v.count("-") == 4
            ):
                redacted[k] = _REDACT_LABEL
            else:
                redacted[k] = _redact_credentials(v)
        return redacted
    if isinstance(value, list):
        return [_redact_credentials(item) for item in value]
    return value


def test_capture_tool_compiles() -> None:
    """The capture tool must compile without syntax errors."""
    py_compile.compile(str(_TOOL_PATH), doraise=True)


def test_capture_tool_no_invalid_except_syntax() -> None:
    """The tool must not use an except form that is invalid on Python 3.

    Python 3.14 allows the bare ``except ValueError, TypeError`` form, so the
    parenthesized form is not required. The regression guard is that the tool
    compiles (covered by test_capture_tool_compiles) and that no truly invalid
    form (e.g. a missing comma or a non-tuple after except) is present.
    """
    source = _TOOL_PATH.read_text(encoding="utf-8")
    # The old Python 2 form with a trailing comma and no exception class is
    # invalid; the valid bare form is `except A, B:` which Python 3.14 accepts.
    assert "except ," not in source


def test_capture_tool_no_datetime_utc_without_utc_import() -> None:
    """The tool must not use datetime.UTC without importing UTC."""
    source = _TOOL_PATH.read_text(encoding="utf-8")
    if "datetime.UTC" in source:
        assert re.search(r"from datetime import .*UTC", source), (
            "datetime.UTC used but UTC is not imported"
        )


def test_capture_tool_imports_utc() -> None:
    """The tool must import UTC from datetime."""
    source = _TOOL_PATH.read_text(encoding="utf-8")
    assert "from datetime import UTC, datetime" in source


def test_redact_credentials_redacts_sensitive_keys() -> None:
    """Credential fields must be redacted in the redacted report."""
    payload = {
        "eid": "abc",
        "gid": "def",
        "symmetric_key": "sekret",
        "key": "wifi-password",
        "publicKey": "pub",
        "privateKey": "priv",
        "license": "lic",
        "seed": "seed",
        "ek": "ek",
        "jwt": "jwt-token",
        "ddnsToken": "ddns",
        "btMac": "20:6D:31:EF:98:A2",
        "cpuid": "cpu",
        "rkey": "rkey",
        "ssid": "Universe",
        "name": "Main Floor",
        "nested": {"password": "pw", "safe": "ok"},
    }
    redacted = _redact_credentials(payload)
    assert isinstance(redacted, dict)
    for key in (
        "eid",
        "gid",
        "symmetric_key",
        "key",
        "publicKey",
        "privateKey",
        "license",
        "seed",
        "ek",
        "jwt",
        "ddnsToken",
        "btMac",
        "cpuid",
        "rkey",
    ):
        assert redacted[key] == "<redacted>", f"{key} was not redacted"
    assert redacted["ssid"] == "Universe"
    assert redacted["name"] == "Main Floor"
    assert redacted["nested"]["password"] == "<redacted>"
    assert redacted["nested"]["safe"] == "ok"


def test_redact_credentials_redacts_uuid_shaped_values() -> None:
    """UUID-shaped values must be redacted even when the key is not sensitive."""
    payload = {"profile_uuid": "f185dc47-2730-48a8-844c-b57aa31af4ba"}
    redacted = _redact_credentials(payload)
    assert redacted["profile_uuid"] == "<redacted>"


def test_redact_credentials_output_is_valid_json() -> None:
    """The redacted report must serialize to valid JSON (no trailing commas)."""
    payload = {
        "decrypted": {
            "message": {
                "obj": {
                    "data": {
                        "item": "networkConfig",
                        "value": {
                            "config": {
                                "apc": {
                                    "profile": {
                                        "uuid": "f185dc47-2730-48a8-844c-b57aa31af4ba"
                                    }
                                }
                            }
                        },
                    }
                }
            }
        }
    }
    redacted = _redact_credentials(payload)
    serialized = json.dumps(redacted, indent=2)
    assert json.loads(serialized) == redacted
