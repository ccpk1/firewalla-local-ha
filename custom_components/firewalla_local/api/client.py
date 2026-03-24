"""Strictly local Firewalla runtime client."""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError

from ..const import (
    DEFAULT_INIT_TARGET,
    FIREWALLA_APP_ID,
    FIREWALLA_APP_VERSION,
)
from ..models import (
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
    FirewallaRuntimeSnapshot,
    FirewallaSystemInfo,
)
from .crypto import aes256_cbc_decrypt_from_base64, aes256_cbc_encrypt_to_base64
from .exceptions import (
    FirewallaAuthError,
    FirewallaConnectionError,
    FirewallaProtocolError,
)


class FirewallaApiClient:
    """Strictly local client for the Encipher runtime endpoint."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        gid: str,
        eid: str,
        aid: str,
        symmetric_key: str,
        device_name: str,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self.host = host
        self.gid = gid
        self.eid = eid
        self.aid = aid
        self.symmetric_key = symmetric_key
        self.device_name = device_name

    def _build_fwmessage(
        self,
        *,
        message_type: str,
        data: dict[str, object],
        target: str = DEFAULT_INIT_TARGET,
    ) -> dict[str, object]:
        """Build the Firewalla-style local message envelope."""
        timezone_name = datetime.now().astimezone().tzname() or "UTC"
        return {
            "mtype": "msg",
            "message": {
                "mtype": "msg",
                "type": "jsondata",
                "msg": "",
                "from": self.device_name,
                "obj": {
                    "type": "jsonmsg",
                    "id": str(uuid.uuid4()),
                    "mtype": message_type,
                    "target": target,
                    "data": data,
                },
                "appInfo": {
                    "deviceName": self.device_name,
                    "appID": FIREWALLA_APP_ID,
                    "platform": sys.platform,
                    "timezone": timezone_name,
                    "language": "en",
                    "version": FIREWALLA_APP_VERSION,
                    "eid": self.eid,
                },
                "compressMode": 1,
            },
        }

    async def _async_post_local_payload(
        self, payload: dict[str, object]
    ) -> tuple[int, str]:
        """Post an encrypted payload to the local runtime endpoint."""
        url = f"http://{self.host}:8833/v1/encipher/message/{self.gid}"
        try:
            async with self._session.post(url, json=payload) as response:
                return response.status, await response.text()
        except ClientError as err:
            raise FirewallaConnectionError(
                f"Could not reach Firewalla box at {self.host}: {err}"
            ) from err

    async def _async_send_local_message(
        self,
        *,
        message_type: str,
        data: dict[str, object],
        target: str = DEFAULT_INIT_TARGET,
    ) -> dict[str, object]:
        """Send a local Encipher message and return the decrypted data payload."""
        message = self._build_fwmessage(
            message_type=message_type,
            data=data,
            target=target,
        )
        encrypted_message = aes256_cbc_encrypt_to_base64(
            json.dumps(message, separators=(",", ":")),
            self.symmetric_key,
        )
        payload = {"message": encrypted_message, "timestamp": int(time.time())}

        response_status, response_text = await self._async_post_local_payload(payload)
        if response_status == 401:
            response_status, response_text = await self._async_post_local_payload(
                payload
            )
            if response_status == 401:
                raise FirewallaAuthError(
                    "Firewalla local runtime returned unauthorized after one retry"
                )

        if response_status != 200:
            raise FirewallaProtocolError(
                "Firewalla local runtime returned HTTP "
                f"{response_status}: {response_text}"
            )

        try:
            response_payload = json.loads(response_text)
        except json.JSONDecodeError as err:
            raise FirewallaProtocolError(
                "Firewalla local runtime response was not valid JSON"
            ) from err

        if not isinstance(response_payload, dict):
            raise FirewallaProtocolError(
                "Firewalla local runtime response was not a JSON object"
            )

        if response_error := response_payload.get("error"):
            raise FirewallaProtocolError(
                f"Firewalla local runtime returned an error: {response_error}"
            )

        response_message = response_payload.get("message")
        if not isinstance(response_message, str) or not response_message:
            raise FirewallaProtocolError(
                "Firewalla local runtime response did not include an encrypted message"
            )

        decrypted = aes256_cbc_decrypt_from_base64(response_message, self.symmetric_key)
        try:
            decrypted_payload = json.loads(decrypted)
        except json.JSONDecodeError as err:
            raise FirewallaProtocolError(
                "Firewalla local runtime decrypted payload was not valid JSON"
            ) from err

        if not isinstance(decrypted_payload, dict):
            raise FirewallaProtocolError(
                "Firewalla local runtime decrypted payload was not a JSON object"
            )

        if decrypted_payload.get("code") != 200:
            raise FirewallaProtocolError(
                f"Firewalla local runtime returned code {decrypted_payload.get('code')}"
            )

        data_payload = decrypted_payload.get("data")
        if not isinstance(data_payload, dict):
            raise FirewallaProtocolError(
                "Firewalla local runtime payload did not include a data object"
            )

        return data_payload

    async def async_get_runtime_init_payload(self) -> dict[str, object]:
        """Fetch the raw Firewalla init payload from the local runtime."""
        return await self._async_send_local_message(
            message_type="init",
            data={"get": DEFAULT_INIT_TARGET},
            target=DEFAULT_INIT_TARGET,
        )

    async def async_create_rule(self, template: FirewallaRuleTemplate) -> None:
        """Create one persistent rule from a stored template."""
        await self._async_send_local_message(
            message_type="cmd",
            data={
                "item": "policy:create",
                "value": template.build_create_value(updated_time=time.time()),
            },
            target=DEFAULT_INIT_TARGET,
        )

    async def async_delete_rule(self, rule_id: str) -> None:
        """Delete one existing policy rule by ID."""
        await self._async_send_local_message(
            message_type="cmd",
            data={"item": "policy:delete", "value": {"policyID": rule_id}},
            target=DEFAULT_INIT_TARGET,
        )

    async def async_update_rule(
        self,
        rule: FirewallaPolicyRule,
        *,
        enabled: bool,
        idle_ts: int | None = None,
    ) -> None:
        """Update one existing policy rule in place."""
        value = dict(rule.raw_update_payload)
        value["pid"] = rule.rule_id
        value["disabled"] = 0 if enabled else 1
        value["updatedTime"] = time.time()

        if enabled:
            value["idleTs"] = ""
        elif idle_ts is not None:
            value["idleTs"] = idle_ts
        elif "idleTs" in value:
            value["idleTs"] = ""

        await self._async_send_local_message(
            message_type="cmd",
            data={"item": "policy:update", "value": value},
            target=DEFAULT_INIT_TARGET,
        )

    def _build_system_info(self, data: dict[str, object]) -> FirewallaSystemInfo:
        """Build normalized system information from the init payload."""
        model = data.get("model")
        serial_number = data.get("cpuid")
        software_version = data.get("longVersion")

        return FirewallaSystemInfo(
            host=self.host,
            name=str(data.get("groupName") or data.get("device") or "Firewalla"),
            model=model if isinstance(model, str) else None,
            serial_number=serial_number if isinstance(serial_number, str) else None,
            software_version=(
                software_version if isinstance(software_version, str) else None
            ),
        )

    def _build_category_lookup(self, data: dict[str, object]) -> dict[str, str]:
        """Build a lookup of category identifiers to human-readable names."""
        raw_categories = data.get("customizedCategories")
        if not isinstance(raw_categories, dict):
            return {}

        category_lookup: dict[str, str] = {}
        for category_id, raw_category in raw_categories.items():
            if not isinstance(category_id, str) or not category_id:
                continue
            if not isinstance(raw_category, dict):
                continue

            app_name = raw_category.get("app")
            if isinstance(app_name, str) and app_name.startswith("qos_"):
                category_lookup[category_id] = (
                    f"QoS {app_name.removeprefix('qos_').replace('_', ' ').title()}"
                )
                continue

            category_name = raw_category.get("name")
            if isinstance(category_name, str) and category_name:
                category_lookup[category_id] = category_name

        return category_lookup

    def _build_network_lookup(self, data: dict[str, object]) -> dict[str, str]:
        """Build a lookup of network UUIDs to readable network names."""
        raw_network_profiles = data.get("networkProfiles")
        network_lookup: dict[str, str] = {}

        if isinstance(raw_network_profiles, dict):
            for network_id, raw_profile in raw_network_profiles.items():
                if not isinstance(network_id, str) or not network_id:
                    continue
                if not isinstance(raw_profile, dict):
                    continue

                display_name = self._resolve_network_display_name(raw_profile)
                if display_name is not None:
                    network_lookup[network_id] = display_name

        raw_network_config = data.get("networkConfig")
        if isinstance(raw_network_config, dict):
            raw_interfaces = raw_network_config.get("interface")
            self._merge_network_config_lookup(raw_interfaces, network_lookup)

        return network_lookup

    def _resolve_network_display_name(
        self, raw_profile: dict[str, object]
    ) -> str | None:
        """Resolve the best available display name from one network profile."""
        for key in ("desc", "name", "intf"):
            value = raw_profile.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _merge_network_config_lookup(
        self, raw_interfaces: object, network_lookup: dict[str, str]
    ) -> None:
        """Merge readable network names from networkConfig.interface metadata."""
        if isinstance(raw_interfaces, dict):
            meta = raw_interfaces.get("meta")
            if isinstance(meta, dict):
                network_id = meta.get("uuid")
                if isinstance(network_id, str) and network_id:
                    for candidate in (
                        meta.get("name"),
                        raw_interfaces.get("desc"),
                        raw_interfaces.get("name"),
                    ):
                        if isinstance(candidate, str) and candidate:
                            network_lookup[network_id] = candidate
                            break

            for value in raw_interfaces.values():
                self._merge_network_config_lookup(value, network_lookup)
            return

        if isinstance(raw_interfaces, list):
            for value in raw_interfaces:
                self._merge_network_config_lookup(value, network_lookup)

    def _build_named_lookup(self, data: dict[str, object], key: str) -> dict[str, str]:
        """Build a uid-to-name lookup for Firewalla tag collections."""
        raw_collection = data.get(key)
        if not isinstance(raw_collection, dict):
            return {}

        named_lookup: dict[str, str] = {}
        for item_id, raw_item in raw_collection.items():
            if not isinstance(item_id, str) or not item_id:
                continue
            if not isinstance(raw_item, dict):
                continue

            item_name = raw_item.get("name")
            if isinstance(item_name, str) and item_name:
                named_lookup[item_id] = item_name

        return named_lookup

    def _build_affiliated_user_lookup(
        self, data: dict[str, object]
    ) -> dict[str, tuple[str, ...]]:
        """Build a lookup of group tags to affiliated user names."""
        raw_user_tags = data.get("userTags")
        if not isinstance(raw_user_tags, dict):
            return {}

        affiliated_users: dict[str, list[str]] = {}
        for raw_user_tag in raw_user_tags.values():
            if not isinstance(raw_user_tag, dict):
                continue

            affiliated_tag = raw_user_tag.get("affiliatedTag")
            user_name = raw_user_tag.get("name")
            if (
                not isinstance(affiliated_tag, str)
                or not affiliated_tag
                or not isinstance(user_name, str)
                or not user_name
            ):
                continue

            affiliated_users.setdefault(affiliated_tag, []).append(user_name)

        return {
            tag_id: tuple(sorted(user_names))
            for tag_id, user_names in affiliated_users.items()
        }

    def _build_host_lookup(self, data: dict[str, object]) -> dict[str, str]:
        """Build a lookup of host MAC addresses to host names."""
        raw_hosts = data.get("hosts")
        if not isinstance(raw_hosts, list):
            return {}

        host_lookup: dict[str, str] = {}
        for raw_host in raw_hosts:
            if not isinstance(raw_host, dict):
                continue

            host_mac = raw_host.get("mac")
            host_name = raw_host.get("name") or raw_host.get("bname")
            if (
                isinstance(host_mac, str)
                and host_mac
                and isinstance(host_name, str)
                and host_name
            ):
                host_lookup[host_mac] = host_name

        return host_lookup

    def _resolve_tag_reference_name(
        self,
        tag_reference: str,
        *,
        tags: dict[str, str],
        device_tags: dict[str, str],
        user_tags: dict[str, str],
        networks: dict[str, str],
        affiliated_users: dict[str, tuple[str, ...]],
    ) -> str | None:
        """Resolve a Firewalla tag reference string into a readable name."""
        tag_prefix, _, tag_value = tag_reference.partition(":")
        if not tag_value:
            return None

        if tag_prefix == "tag":
            if tag_name := tags.get(tag_value):
                if user_names := affiliated_users.get(tag_value):
                    return f"{tag_name} ({', '.join(user_names)})"
                return tag_name
            return None
        if tag_prefix == "dtag":
            return device_tags.get(tag_value)
        if tag_prefix in {"utag", "userTag"}:
            return user_tags.get(tag_value)
        if tag_prefix == "intf":
            return networks.get(tag_value)
        return None

    def _resolve_rule_applicability(
        self,
        raw_rule: dict[str, object],
        *,
        tags: dict[str, str],
        device_tags: dict[str, str],
        user_tags: dict[str, str],
        networks: dict[str, str],
        affiliated_users: dict[str, tuple[str, ...]],
    ) -> tuple[str, ...]:
        """Resolve tag-based rule applicability into readable labels."""
        raw_tags = raw_rule.get("tag")
        if not isinstance(raw_tags, list):
            return ()

        resolved_tags = [
            resolved_name
            for tag_reference in raw_tags
            if isinstance(tag_reference, str)
            and (
                resolved_name := self._resolve_tag_reference_name(
                    tag_reference,
                    tags=tags,
                    device_tags=device_tags,
                    user_tags=user_tags,
                    networks=networks,
                    affiliated_users=affiliated_users,
                )
            )
        ]
        return tuple(dict.fromkeys(resolved_tags))

    def _resolve_target_name(
        self,
        raw_rule: dict[str, object],
        *,
        target: str,
        target_type: str,
        categories: dict[str, str],
        networks: dict[str, str],
        tags: dict[str, str],
        device_tags: dict[str, str],
        user_tags: dict[str, str],
        hosts: dict[str, str],
        affiliated_users: dict[str, tuple[str, ...]],
    ) -> str | None:
        """Resolve a human-readable target name for one policy rule."""
        explicit_target_name = raw_rule.get("target_name")
        if isinstance(explicit_target_name, str) and explicit_target_name:
            return explicit_target_name

        if target_type == "mac":
            if target == "TAG":
                raw_tags = raw_rule.get("tag")
                if isinstance(raw_tags, list):
                    resolved_tags = [
                        resolved_name
                        for tag_reference in raw_tags
                        if isinstance(tag_reference, str)
                        and (
                            resolved_name := self._resolve_tag_reference_name(
                                tag_reference,
                                tags=tags,
                                device_tags=device_tags,
                                user_tags=user_tags,
                                networks=networks,
                                affiliated_users=affiliated_users,
                            )
                        )
                    ]
                    if resolved_tags:
                        return ", ".join(resolved_tags)

            return hosts.get(target)

        if target_type == "network":
            return networks.get(target)

        if target_type == "category":
            if target in categories:
                return categories[target]
            if target.startswith("TL-"):
                trimmed_target = target.removeprefix("TL-")
                if trimmed_target in categories:
                    return categories[trimmed_target]
            if target.replace("_", "").isalnum() and not target.startswith("TL-"):
                return target.replace("_", " ")
            if "_" in target and not target.startswith("TL-"):
                return target.replace("_", " ")

        return None

    def _coerce_float(self, value: object) -> float | None:
        """Coerce Firewalla numeric-like values to float when possible."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value:
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _coerce_int(self, value: object) -> int | None:
        """Coerce Firewalla numeric-like values to int when possible."""
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value:
            try:
                return int(float(value))
            except ValueError:
                return None
        return None

    def _coerce_boolish(self, value: object) -> bool | None:
        """Coerce Firewalla bool-like values to bool when possible."""
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes"}:
                return True
            if lowered in {"0", "false", "no", ""}:
                return False
        return None

    def _normalize_policy_rules(
        self, data: dict[str, object]
    ) -> tuple[FirewallaPolicyRule, ...]:
        """Normalize Firewalla policy rules into a stable typed MVP shape."""
        raw_rules = data.get("policyRules")
        if not isinstance(raw_rules, list):
            return ()

        category_lookup = self._build_category_lookup(data)
        network_lookup = self._build_network_lookup(data)
        tag_lookup = self._build_named_lookup(data, "tags")
        device_tag_lookup = self._build_named_lookup(data, "deviceTags")
        user_tag_lookup = self._build_named_lookup(data, "userTags")
        affiliated_user_lookup = self._build_affiliated_user_lookup(data)
        host_lookup = self._build_host_lookup(data)

        normalized_rules: list[FirewallaPolicyRule] = []
        for raw_rule in raw_rules:
            if not isinstance(raw_rule, dict):
                continue

            raw_rule_id = raw_rule.get("pid")
            raw_action = raw_rule.get("action")
            raw_target = raw_rule.get("target")
            raw_target_type = raw_rule.get("type")
            if not isinstance(raw_rule_id, str) or not raw_rule_id:
                continue
            if not isinstance(raw_action, str) or not raw_action:
                continue
            if not isinstance(raw_target, str) or not raw_target:
                continue
            if not isinstance(raw_target_type, str) or not raw_target_type:
                continue

            direction = raw_rule.get("direction")
            purpose = raw_rule.get("purpose")
            scope_value = raw_rule.get("scope")
            scope = (
                tuple(item for item in scope_value if isinstance(item, str) and item)
                if isinstance(scope_value, list)
                else ()
            )
            raw_tag_refs = raw_rule.get("tag")
            tag_refs = (
                tuple(item for item in raw_tag_refs if isinstance(item, str) and item)
                if isinstance(raw_tag_refs, list)
                else ()
            )

            disabled = raw_rule.get("disabled")
            enabled = disabled not in {"1", "true", "True", 1}
            if isinstance(disabled, bool):
                enabled = not disabled

            activated_time = self._coerce_float(raw_rule.get("activatedTime"))
            updated_time = self._coerce_float(raw_rule.get("updatedTime"))
            last_activated_time = self._coerce_float(raw_rule.get("lastActivatedTime"))
            expire_seconds = self._coerce_int(raw_rule.get("expire"))
            auto_delete_when_expires = self._coerce_boolish(
                raw_rule.get("autoDeleteWhenExpires")
            )
            dnsmasq_only = self._coerce_boolish(raw_rule.get("dnsmasq_only"))
            expires_at = (
                activated_time + expire_seconds
                if activated_time is not None and expire_seconds is not None
                else None
            )

            target_name = self._resolve_target_name(
                raw_rule,
                target=raw_target,
                target_type=raw_target_type,
                categories=category_lookup,
                networks=network_lookup,
                tags=tag_lookup,
                device_tags=device_tag_lookup,
                user_tags=user_tag_lookup,
                hosts=host_lookup,
                affiliated_users=affiliated_user_lookup,
            )
            applies_to = self._resolve_rule_applicability(
                raw_rule,
                tags=tag_lookup,
                device_tags=device_tag_lookup,
                user_tags=user_tag_lookup,
                networks=network_lookup,
                affiliated_users=affiliated_user_lookup,
            )

            normalized_rules.append(
                FirewallaPolicyRule(
                    rule_id=raw_rule_id,
                    action=raw_action,
                    target=raw_target,
                    target_type=raw_target_type,
                    direction=direction if isinstance(direction, str) else None,
                    enabled=enabled,
                    purpose=purpose if isinstance(purpose, str) else None,
                    scope=scope,
                    tag_refs=tag_refs,
                    target_name=target_name,
                    applies_to=applies_to,
                    activated_time=activated_time,
                    updated_time=updated_time,
                    last_activated_time=last_activated_time,
                    expire_seconds=expire_seconds,
                    expires_at=expires_at,
                    auto_delete_when_expires=auto_delete_when_expires,
                    dnsmasq_only=dnsmasq_only,
                    raw_update_payload=dict(raw_rule),
                )
            )

        return tuple(normalized_rules)

    def _count_exception_rules(self, data: dict[str, object]) -> int:
        """Return the number of exception rules exposed by the init payload."""
        raw_exception_rules = data.get("exceptionRules")
        if not isinstance(raw_exception_rules, list):
            return 0
        return len(raw_exception_rules)

    def build_runtime_snapshot(
        self, data: dict[str, object]
    ) -> FirewallaRuntimeSnapshot:
        """Build a coordinator-ready snapshot from one raw init payload."""
        return FirewallaRuntimeSnapshot(
            system_info=self._build_system_info(data),
            policy_rules=self._normalize_policy_rules(data),
            exception_rule_count=self._count_exception_rules(data),
        )

    async def async_get_runtime_snapshot(self) -> FirewallaRuntimeSnapshot:
        """Fetch the runtime snapshot used by the coordinator."""
        return self.build_runtime_snapshot(await self.async_get_runtime_init_payload())

    async def async_get_system_info(self) -> FirewallaSystemInfo:
        """Fetch basic system information from the local init response."""
        return (await self.async_get_runtime_snapshot()).system_info
