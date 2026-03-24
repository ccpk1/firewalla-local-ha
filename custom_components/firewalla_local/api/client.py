"""Strictly local Firewalla runtime client."""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime
from typing import Final

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
    FirewallaSpeedTestResult,
    FirewallaSystemInfo,
    FirewallaSystemStatus,
)
from .crypto import aes256_cbc_decrypt_from_base64, aes256_cbc_encrypt_to_base64
from .exceptions import (
    FirewallaAuthError,
    FirewallaConnectionError,
    FirewallaProtocolError,
)

_FWMESSAGE_TYPE_MSG: Final = "msg"
_FWMESSAGE_TYPE_JSONDATA: Final = "jsondata"
_FWMESSAGE_OBJECT_TYPE_JSONMSG: Final = "jsonmsg"
_FWMESSAGE_LANGUAGE_ENGLISH: Final = "en"
_FWMESSAGE_TIMEZONE_UTC: Final = "UTC"

_RAW_MESSAGE_KEY: Final = "message"
_RAW_MESSAGE_ERROR_KEY: Final = "error"
_RAW_MESSAGE_DATA_KEY: Final = "data"
_RAW_MESSAGE_CODE_KEY: Final = "code"
_RAW_MESSAGE_TIMESTAMP_KEY: Final = "timestamp"

_COMMAND_MESSAGE_TYPE: Final = "cmd"
_INIT_MESSAGE_TYPE: Final = "init"
_COMMAND_ITEM_KEY: Final = "item"
_COMMAND_VALUE_KEY: Final = "value"
_COMMAND_GET_KEY: Final = "get"
_COMMAND_POLICY_CREATE: Final = "policy:create"
_COMMAND_POLICY_DELETE: Final = "policy:delete"
_COMMAND_POLICY_UPDATE: Final = "policy:update"
_COMMAND_POLICY_ID_KEY: Final = "policyID"

_RAW_RULE_ID_KEY: Final = "pid"
_RAW_RULE_ACTION_KEY: Final = "action"
_RAW_RULE_TARGET_KEY: Final = "target"
_RAW_RULE_TYPE_KEY: Final = "type"
_RAW_RULE_DIRECTION_KEY: Final = "direction"
_RAW_RULE_PURPOSE_KEY: Final = "purpose"
_RAW_RULE_SCOPE_KEY: Final = "scope"
_RAW_RULE_TAGS_KEY: Final = "tag"
_RAW_RULE_DISABLED_KEY: Final = "disabled"
_RAW_RULE_UPDATED_TIME_KEY: Final = "updatedTime"
_RAW_RULE_IDLE_TS_KEY: Final = "idleTs"
_RAW_RULE_TARGET_NAME_KEY: Final = "target_name"
_RAW_RULE_ACTIVATED_TIME_KEY: Final = "activatedTime"
_RAW_RULE_LAST_ACTIVATED_TIME_KEY: Final = "lastActivatedTime"
_RAW_RULE_EXPIRE_KEY: Final = "expire"
_RAW_RULE_AUTO_DELETE_WHEN_EXPIRES_KEY: Final = "autoDeleteWhenExpires"
_RAW_RULE_DNSMASQ_ONLY_KEY: Final = "dnsmasq_only"

_RAW_SYSTEM_MODEL_KEY: Final = "model"
_RAW_SYSTEM_CPU_ID_KEY: Final = "cpuid"
_RAW_SYSTEM_LONG_VERSION_KEY: Final = "longVersion"
_RAW_SYSTEM_GROUP_NAME_KEY: Final = "groupName"
_RAW_SYSTEM_DEVICE_NAME_KEY: Final = "device"
_RAW_SYSTEM_BOOTING_COMPLETE_KEY: Final = "bootingComplete"
_RAW_SYSTEM_CLOUD_CONNECTED_KEY: Final = "cloudConnected"
_RAW_SYSTEM_DDNS_KEY: Final = "ddns"
_RAW_SYSTEM_FIRMWARE_RELEASE_TYPE_KEY: Final = "firmwareReleaseType"
_RAW_SYSTEM_PUBLIC_IP_KEY: Final = "publicIp"
_RAW_SYSTEM_PUBLIC_IPS_KEY: Final = "publicIps"
_RAW_SYSTEM_SYS_METRICS_KEY: Final = "sysMetrics"
_RAW_SYSTEM_SYS_METRICS_CPU_LOAD_5_KEY: Final = "load5"
_RAW_SYSTEM_SYS_METRICS_MEMORY_USAGE_KEY: Final = "memUsage"
_RAW_SYSTEM_SYS_METRICS_TOTAL_MEMORY_KEY: Final = "totalMem"
_RAW_SYSTEM_SYS_METRICS_DISK_INFO_KEY: Final = "diskInfo"
_RAW_SYSTEM_SYS_METRICS_DISK_MOUNT_KEY: Final = "mount"
_RAW_SYSTEM_SYS_METRICS_DISK_CAPACITY_KEY: Final = "capacity"
_RAW_SYSTEM_SYS_METRICS_DISK_USED_KEY: Final = "used"
_RAW_SYSTEM_SYS_METRICS_DISK_SIZE_KEY: Final = "size"
_RAW_CUSTOMIZED_CATEGORIES_KEY: Final = "customizedCategories"
_RAW_NETWORK_PROFILES_KEY: Final = "networkProfiles"
_RAW_NETWORK_CONFIG_KEY: Final = "networkConfig"
_RAW_INTERFACE_KEY: Final = "interface"
_RAW_META_KEY: Final = "meta"
_RAW_UUID_KEY: Final = "uuid"
_RAW_NAME_KEY: Final = "name"
_RAW_DESC_KEY: Final = "desc"
_RAW_INTF_KEY: Final = "intf"
_RAW_DEVICE_TAGS_KEY: Final = "deviceTags"
_RAW_USER_TAGS_KEY: Final = "userTags"
_RAW_HOSTS_KEY: Final = "hosts"
_RAW_HOST_MAC_KEY: Final = "mac"
_RAW_HOST_BACKUP_NAME_KEY: Final = "bname"
_RAW_EXCEPTION_RULES_KEY: Final = "exceptionRules"
_RAW_POLICY_RULES_KEY: Final = "policyRules"
_RAW_SPEED_TEST_RESULTS_KEY: Final = "internetSpeedtestResults"
_RAW_SPEED_TEST_CLIENT_KEY: Final = "client"
_RAW_SPEED_TEST_RESULT_KEY: Final = "result"
_RAW_SPEED_TEST_SERVER_KEY: Final = "server"
_RAW_SPEED_TEST_TIMESTAMP_KEY: Final = "timestamp"
_RAW_SPEED_TEST_MANUAL_KEY: Final = "manual"
_RAW_SPEED_TEST_SUCCESS_KEY: Final = "success"
_RAW_SPEED_TEST_VENDOR_KEY: Final = "vendor"
_RAW_SPEED_TEST_PUBLIC_IP_KEY: Final = "publicIp"
_RAW_SPEED_TEST_ISP_KEY: Final = "isp"
_RAW_SPEED_TEST_DOWNLOAD_KEY: Final = "download"
_RAW_SPEED_TEST_UPLOAD_KEY: Final = "upload"
_RAW_SPEED_TEST_LATENCY_KEY: Final = "latency"
_RAW_SPEED_TEST_JITTER_KEY: Final = "jitter"
_RAW_SPEED_TEST_PACKET_LOSS_KEY: Final = "ploss"
_RAW_SPEED_TEST_DOWNLOAD_MBYTES_KEY: Final = "dlMbytes"
_RAW_SPEED_TEST_UPLOAD_MBYTES_KEY: Final = "ulMbytes"
_RAW_SPEED_TEST_SERVER_COUNTRY_KEY: Final = "country"
_RAW_SPEED_TEST_SERVER_HOST_KEY: Final = "host"
_RAW_SPEED_TEST_SERVER_ID_KEY: Final = "id"
_RAW_SPEED_TEST_SERVER_LOCATION_KEY: Final = "location"
_RAW_SPEED_TEST_SERVER_SPONSOR_KEY: Final = "sponsor"

_RAW_TAG_PREFIX_GROUP: Final = "tag"
_RAW_TAG_PREFIX_DEVICE: Final = "dtag"
_RAW_TAG_PREFIX_USER: Final = "utag"
_RAW_TAG_PREFIX_USER_ALT: Final = "userTag"
_RAW_TAG_PREFIX_NETWORK: Final = "intf"
_RAW_TAG_SEPARATOR: Final = ":"

_RULE_TARGET_TAG: Final = "TAG"
_RULE_TARGET_LIST_PREFIX: Final = "TL-"
_RULE_TARGET_TYPE_CATEGORY: Final = "category"
_RULE_TARGET_TYPE_MAC: Final = "mac"
_RULE_TARGET_TYPE_NETWORK: Final = "network"

_QOS_PREFIX: Final = "qos_"
_QOS_LABEL_PREFIX: Final = "QoS "
_DEFAULT_BOX_NAME: Final = "Firewalla"
_BOOLISH_TRUE_VALUES: Final = {"1", "true", "yes"}
_BOOLISH_FALSE_VALUES: Final = {"0", "false", "no", ""}
_DISABLED_TRUE_VALUES: Final = {"1", "true", "True", 1}
_RAW_RULE_DISABLED_FALSE_VALUE: Final = 0
_RAW_RULE_DISABLED_TRUE_VALUE: Final = 1
_RAW_RULE_IDLE_TS_EMPTY_VALUE: Final = ""
_SYSTEM_STATUS_PRIMARY_DISK_MOUNTS: Final = (
    "/",
    "/boot",
    "/boot/efi",
    "/var/lib/docker",
    "/log",
    "/data",
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
        timezone_name = datetime.now().astimezone().tzname() or _FWMESSAGE_TIMEZONE_UTC
        return {
            "mtype": _FWMESSAGE_TYPE_MSG,
            _RAW_MESSAGE_KEY: {
                "mtype": _FWMESSAGE_TYPE_MSG,
                "type": _FWMESSAGE_TYPE_JSONDATA,
                "msg": "",
                "from": self.device_name,
                "obj": {
                    "type": _FWMESSAGE_OBJECT_TYPE_JSONMSG,
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
                    "language": _FWMESSAGE_LANGUAGE_ENGLISH,
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
        payload = {
            _RAW_MESSAGE_KEY: encrypted_message,
            _RAW_MESSAGE_TIMESTAMP_KEY: int(time.time()),
        }

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

        if response_error := response_payload.get(_RAW_MESSAGE_ERROR_KEY):
            raise FirewallaProtocolError(
                f"Firewalla local runtime returned an error: {response_error}"
            )

        response_message = response_payload.get(_RAW_MESSAGE_KEY)
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

        if decrypted_payload.get(_RAW_MESSAGE_CODE_KEY) != 200:
            raise FirewallaProtocolError(
                "Firewalla local runtime returned code "
                f"{decrypted_payload.get(_RAW_MESSAGE_CODE_KEY)}"
            )

        data_payload = decrypted_payload.get(_RAW_MESSAGE_DATA_KEY)
        if not isinstance(data_payload, dict):
            raise FirewallaProtocolError(
                "Firewalla local runtime payload did not include a data object"
            )

        return data_payload

    async def async_get_runtime_init_payload(self) -> dict[str, object]:
        """Fetch the raw Firewalla init payload from the local runtime."""
        return await self._async_send_local_message(
            message_type=_INIT_MESSAGE_TYPE,
            data={_COMMAND_GET_KEY: DEFAULT_INIT_TARGET},
            target=DEFAULT_INIT_TARGET,
        )

    async def async_create_rule(self, template: FirewallaRuleTemplate) -> None:
        """Create one persistent rule from a stored template."""
        await self._async_send_local_message(
            message_type=_COMMAND_MESSAGE_TYPE,
            data={
                _COMMAND_ITEM_KEY: _COMMAND_POLICY_CREATE,
                _COMMAND_VALUE_KEY: template.build_create_value(
                    updated_time=time.time()
                ),
            },
            target=DEFAULT_INIT_TARGET,
        )

    async def async_delete_rule(self, rule_id: str) -> None:
        """Delete one existing policy rule by ID."""
        await self._async_send_local_message(
            message_type=_COMMAND_MESSAGE_TYPE,
            data={
                _COMMAND_ITEM_KEY: _COMMAND_POLICY_DELETE,
                _COMMAND_VALUE_KEY: {_COMMAND_POLICY_ID_KEY: rule_id},
            },
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
        value[_RAW_RULE_ID_KEY] = rule.rule_id
        value[_RAW_RULE_DISABLED_KEY] = (
            _RAW_RULE_DISABLED_FALSE_VALUE if enabled else _RAW_RULE_DISABLED_TRUE_VALUE
        )
        value[_RAW_RULE_UPDATED_TIME_KEY] = time.time()

        if enabled:
            value[_RAW_RULE_IDLE_TS_KEY] = _RAW_RULE_IDLE_TS_EMPTY_VALUE
        elif idle_ts is not None:
            value[_RAW_RULE_IDLE_TS_KEY] = idle_ts
        elif _RAW_RULE_IDLE_TS_KEY in value:
            value[_RAW_RULE_IDLE_TS_KEY] = _RAW_RULE_IDLE_TS_EMPTY_VALUE

        await self._async_send_local_message(
            message_type=_COMMAND_MESSAGE_TYPE,
            data={
                _COMMAND_ITEM_KEY: _COMMAND_POLICY_UPDATE,
                _COMMAND_VALUE_KEY: value,
            },
            target=DEFAULT_INIT_TARGET,
        )

    def _build_system_info(self, data: dict[str, object]) -> FirewallaSystemInfo:
        """Build normalized system information from the init payload."""
        model = data.get(_RAW_SYSTEM_MODEL_KEY)
        serial_number = data.get(_RAW_SYSTEM_CPU_ID_KEY)
        software_version = data.get(_RAW_SYSTEM_LONG_VERSION_KEY)

        return FirewallaSystemInfo(
            host=self.host,
            name=str(
                data.get(_RAW_SYSTEM_GROUP_NAME_KEY)
                or data.get(_RAW_SYSTEM_DEVICE_NAME_KEY)
                or _DEFAULT_BOX_NAME
            ),
            model=model if isinstance(model, str) else None,
            serial_number=serial_number if isinstance(serial_number, str) else None,
            software_version=(
                software_version if isinstance(software_version, str) else None
            ),
        )

    def _build_system_status(self, data: dict[str, object]) -> FirewallaSystemStatus:
        """Build normalized system-status state from the init payload."""
        raw_sys_metrics = data.get(_RAW_SYSTEM_SYS_METRICS_KEY)
        sys_metrics = raw_sys_metrics if isinstance(raw_sys_metrics, dict) else {}
        wan_ips = self._build_wan_ips(data)
        memory_usage_ratio = self._coerce_float(
            sys_metrics.get(_RAW_SYSTEM_SYS_METRICS_MEMORY_USAGE_KEY)
        )
        memory_usage_percent = self._build_memory_usage_percent(sys_metrics)

        return FirewallaSystemStatus(
            booting_complete=self._coerce_boolish(
                data.get(_RAW_SYSTEM_BOOTING_COMPLETE_KEY)
            ),
            cloud_connected=self._coerce_boolish(
                data.get(_RAW_SYSTEM_CLOUD_CONNECTED_KEY)
            ),
            ddns=(
                ddns
                if isinstance((ddns := data.get(_RAW_SYSTEM_DDNS_KEY)), str) and ddns
                else None
            ),
            firmware_release_type=(
                firmware_release_type
                if isinstance(
                    (
                        firmware_release_type := data.get(
                            _RAW_SYSTEM_FIRMWARE_RELEASE_TYPE_KEY
                        )
                    ),
                    str,
                )
                and firmware_release_type
                else None
            ),
            wan_ip=self._build_wan_ip(data, wan_ips),
            wan_ips=wan_ips,
            cpu_load_5m=self._coerce_float(
                sys_metrics.get(_RAW_SYSTEM_SYS_METRICS_CPU_LOAD_5_KEY)
            ),
            memory_usage_percent=memory_usage_percent,
            memory_free_mb=self._build_memory_free_mb(sys_metrics, memory_usage_ratio),
            disk_usage_percent_by_mount=self._build_disk_usage_percent_by_mount(
                sys_metrics
            ),
        )

    def _build_wan_ip(
        self, data: dict[str, object], wan_ips: dict[str, str] | None
    ) -> str | None:
        """Build the primary WAN public IP from the init payload."""
        raw_public_ip = data.get(_RAW_SYSTEM_PUBLIC_IP_KEY)
        if isinstance(raw_public_ip, str) and raw_public_ip:
            return raw_public_ip
        if wan_ips:
            return next(iter(wan_ips.values()))
        return None

    def _build_wan_ips(self, data: dict[str, object]) -> dict[str, str] | None:
        """Build the WAN public IP map keyed by interface name."""
        raw_public_ips = data.get(_RAW_SYSTEM_PUBLIC_IPS_KEY)
        if not isinstance(raw_public_ips, dict):
            return None

        wan_ips = {
            interface_name: public_ip
            for interface_name, public_ip in raw_public_ips.items()
            if isinstance(interface_name, str)
            and interface_name
            and isinstance(public_ip, str)
            and public_ip
        }
        return wan_ips or None

    def _build_memory_usage_percent(
        self, sys_metrics: dict[str, object]
    ) -> float | None:
        """Build the memory usage percentage from the sysMetrics payload."""
        memory_usage_ratio = self._coerce_float(
            sys_metrics.get(_RAW_SYSTEM_SYS_METRICS_MEMORY_USAGE_KEY)
        )
        if memory_usage_ratio is None:
            return None
        return round(memory_usage_ratio * 100, 1)

    def _build_memory_free_mb(
        self, sys_metrics: dict[str, object], memory_usage_ratio: float | None
    ) -> float | None:
        """Build free memory in megabytes from the sysMetrics payload."""
        total_memory_mb = self._coerce_float(
            sys_metrics.get(_RAW_SYSTEM_SYS_METRICS_TOTAL_MEMORY_KEY)
        )
        if total_memory_mb is None or memory_usage_ratio is None:
            return None
        return round(total_memory_mb * (1 - memory_usage_ratio), 1)

    def _build_disk_usage_percent_by_mount(
        self, sys_metrics: dict[str, object]
    ) -> dict[str, int] | None:
        """Build a filtered disk usage map for important system mounts."""
        raw_disk_info = sys_metrics.get(_RAW_SYSTEM_SYS_METRICS_DISK_INFO_KEY)
        if not isinstance(raw_disk_info, list):
            return None

        usage_by_mount: dict[str, int] = {}
        for raw_disk in raw_disk_info:
            if not isinstance(raw_disk, dict):
                continue

            mount = raw_disk.get(_RAW_SYSTEM_SYS_METRICS_DISK_MOUNT_KEY)
            if (
                not isinstance(mount, str)
                or mount not in _SYSTEM_STATUS_PRIMARY_DISK_MOUNTS
            ):
                continue

            usage_ratio = self._coerce_float(
                raw_disk.get(_RAW_SYSTEM_SYS_METRICS_DISK_CAPACITY_KEY)
            )
            if usage_ratio is None:
                used = self._coerce_float(
                    raw_disk.get(_RAW_SYSTEM_SYS_METRICS_DISK_USED_KEY)
                )
                size = self._coerce_float(
                    raw_disk.get(_RAW_SYSTEM_SYS_METRICS_DISK_SIZE_KEY)
                )
                if used is None or size is None or size == 0:
                    continue
                usage_ratio = used / size

            usage_by_mount[mount] = round(usage_ratio * 100)

        filtered_usage = {
            mount: usage_by_mount[mount]
            for mount in _SYSTEM_STATUS_PRIMARY_DISK_MOUNTS
            if mount in usage_by_mount
        }
        return filtered_usage or None

    def _build_latest_speed_test(
        self, data: dict[str, object]
    ) -> FirewallaSpeedTestResult | None:
        """Build the latest successful internet speed-test result."""
        raw_results = data.get(_RAW_SPEED_TEST_RESULTS_KEY)
        if not isinstance(raw_results, list):
            return None

        successful_results: list[tuple[float, dict[str, object]]] = []
        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                continue

            timestamp = self._coerce_float(
                raw_result.get(_RAW_SPEED_TEST_TIMESTAMP_KEY)
            )
            success = self._coerce_boolish(raw_result.get(_RAW_SPEED_TEST_SUCCESS_KEY))
            if timestamp is None or success is not True:
                continue

            successful_results.append((timestamp, raw_result))

        if not successful_results:
            return None

        latest_timestamp, latest_result = max(
            successful_results,
            key=lambda item: item[0],
        )

        raw_client = latest_result.get(_RAW_SPEED_TEST_CLIENT_KEY)
        raw_measurement = latest_result.get(_RAW_SPEED_TEST_RESULT_KEY)
        raw_server = latest_result.get(_RAW_SPEED_TEST_SERVER_KEY)

        client = raw_client if isinstance(raw_client, dict) else {}
        measurement = raw_measurement if isinstance(raw_measurement, dict) else {}
        server = raw_server if isinstance(raw_server, dict) else {}

        return FirewallaSpeedTestResult(
            tested_at_timestamp=latest_timestamp,
            download_mbps=self._coerce_float(
                measurement.get(_RAW_SPEED_TEST_DOWNLOAD_KEY)
            ),
            upload_mbps=self._coerce_float(measurement.get(_RAW_SPEED_TEST_UPLOAD_KEY)),
            latency_ms=self._coerce_float(measurement.get(_RAW_SPEED_TEST_LATENCY_KEY)),
            jitter_ms=self._coerce_float(measurement.get(_RAW_SPEED_TEST_JITTER_KEY)),
            packet_loss_percent=self._coerce_float(
                measurement.get(_RAW_SPEED_TEST_PACKET_LOSS_KEY)
            ),
            download_megabytes=self._coerce_float(
                measurement.get(_RAW_SPEED_TEST_DOWNLOAD_MBYTES_KEY)
            ),
            upload_megabytes=self._coerce_float(
                measurement.get(_RAW_SPEED_TEST_UPLOAD_MBYTES_KEY)
            ),
            isp=(
                isp
                if isinstance((isp := client.get(_RAW_SPEED_TEST_ISP_KEY)), str) and isp
                else None
            ),
            public_ip=(
                public_ip
                if isinstance(
                    (public_ip := client.get(_RAW_SPEED_TEST_PUBLIC_IP_KEY)), str
                )
                and public_ip
                else None
            ),
            server_country=(
                server_country
                if isinstance(
                    (server_country := server.get(_RAW_SPEED_TEST_SERVER_COUNTRY_KEY)),
                    str,
                )
                and server_country
                else None
            ),
            server_host=(
                server_host
                if isinstance(
                    (server_host := server.get(_RAW_SPEED_TEST_SERVER_HOST_KEY)), str
                )
                and server_host
                else None
            ),
            server_id=(
                server_id
                if isinstance(
                    (server_id := server.get(_RAW_SPEED_TEST_SERVER_ID_KEY)),
                    str,
                )
                and server_id
                else None
            ),
            server_location=(
                server_location
                if isinstance(
                    (
                        server_location := server.get(
                            _RAW_SPEED_TEST_SERVER_LOCATION_KEY
                        )
                    ),
                    str,
                )
                and server_location
                else None
            ),
            server_sponsor=(
                server_sponsor
                if isinstance(
                    (server_sponsor := server.get(_RAW_SPEED_TEST_SERVER_SPONSOR_KEY)),
                    str,
                )
                and server_sponsor
                else None
            ),
            manual=self._coerce_boolish(latest_result.get(_RAW_SPEED_TEST_MANUAL_KEY)),
            success=True,
            vendor=(
                vendor
                if isinstance(
                    (vendor := latest_result.get(_RAW_SPEED_TEST_VENDOR_KEY)),
                    str,
                )
                and vendor
                else None
            ),
        )

    def _build_category_lookup(self, data: dict[str, object]) -> dict[str, str]:
        """Build a lookup of category identifiers to human-readable names."""
        raw_categories = data.get(_RAW_CUSTOMIZED_CATEGORIES_KEY)
        if not isinstance(raw_categories, dict):
            return {}

        category_lookup: dict[str, str] = {}
        for category_id, raw_category in raw_categories.items():
            if not isinstance(category_id, str) or not category_id:
                continue
            if not isinstance(raw_category, dict):
                continue

            app_name = raw_category.get("app")
            if isinstance(app_name, str) and app_name.startswith(_QOS_PREFIX):
                category_lookup[category_id] = (
                    f"{_QOS_LABEL_PREFIX}"
                    f"{app_name.removeprefix(_QOS_PREFIX).replace('_', ' ').title()}"
                )
                continue

            category_name = raw_category.get(_RAW_NAME_KEY)
            if isinstance(category_name, str) and category_name:
                category_lookup[category_id] = category_name

        return category_lookup

    def _build_network_lookup(self, data: dict[str, object]) -> dict[str, str]:
        """Build a lookup of network UUIDs to readable network names."""
        raw_network_profiles = data.get(_RAW_NETWORK_PROFILES_KEY)
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

        raw_network_config = data.get(_RAW_NETWORK_CONFIG_KEY)
        if isinstance(raw_network_config, dict):
            raw_interfaces = raw_network_config.get(_RAW_INTERFACE_KEY)
            self._merge_network_config_lookup(raw_interfaces, network_lookup)

        return network_lookup

    def _resolve_network_display_name(
        self, raw_profile: dict[str, object]
    ) -> str | None:
        """Resolve the best available display name from one network profile."""
        for key in (_RAW_DESC_KEY, _RAW_NAME_KEY, _RAW_INTF_KEY):
            value = raw_profile.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _merge_network_config_lookup(
        self, raw_interfaces: object, network_lookup: dict[str, str]
    ) -> None:
        """Merge readable network names from networkConfig.interface metadata."""
        if isinstance(raw_interfaces, dict):
            meta = raw_interfaces.get(_RAW_META_KEY)
            if isinstance(meta, dict):
                network_id = meta.get(_RAW_UUID_KEY)
                if isinstance(network_id, str) and network_id:
                    for candidate in (
                        meta.get(_RAW_NAME_KEY),
                        raw_interfaces.get(_RAW_DESC_KEY),
                        raw_interfaces.get(_RAW_NAME_KEY),
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

            item_name = raw_item.get(_RAW_NAME_KEY)
            if isinstance(item_name, str) and item_name:
                named_lookup[item_id] = item_name

        return named_lookup

    def _build_affiliated_user_lookup(
        self, data: dict[str, object]
    ) -> dict[str, tuple[str, ...]]:
        """Build a lookup of group tags to affiliated user names."""
        raw_user_tags = data.get(_RAW_USER_TAGS_KEY)
        if not isinstance(raw_user_tags, dict):
            return {}

        affiliated_users: dict[str, list[str]] = {}
        for raw_user_tag in raw_user_tags.values():
            if not isinstance(raw_user_tag, dict):
                continue

            affiliated_tag = raw_user_tag.get("affiliatedTag")
            user_name = raw_user_tag.get(_RAW_NAME_KEY)
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
        raw_hosts = data.get(_RAW_HOSTS_KEY)
        if not isinstance(raw_hosts, list):
            return {}

        host_lookup: dict[str, str] = {}
        for raw_host in raw_hosts:
            if not isinstance(raw_host, dict):
                continue

            host_mac = raw_host.get(_RAW_HOST_MAC_KEY)
            host_name = raw_host.get(_RAW_NAME_KEY) or raw_host.get(
                _RAW_HOST_BACKUP_NAME_KEY
            )
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
        tag_prefix, _, tag_value = tag_reference.partition(_RAW_TAG_SEPARATOR)
        if not tag_value:
            return None

        if tag_prefix == _RAW_TAG_PREFIX_GROUP:
            if tag_name := tags.get(tag_value):
                if user_names := affiliated_users.get(tag_value):
                    return f"{tag_name} ({', '.join(user_names)})"
                return tag_name
            return None
        if tag_prefix == _RAW_TAG_PREFIX_DEVICE:
            return device_tags.get(tag_value)
        if tag_prefix in {_RAW_TAG_PREFIX_USER, _RAW_TAG_PREFIX_USER_ALT}:
            return user_tags.get(tag_value)
        if tag_prefix == _RAW_TAG_PREFIX_NETWORK:
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
        raw_tags = raw_rule.get(_RAW_RULE_TAGS_KEY)
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
        explicit_target_name = raw_rule.get(_RAW_RULE_TARGET_NAME_KEY)
        if isinstance(explicit_target_name, str) and explicit_target_name:
            return explicit_target_name

        if target_type == _RULE_TARGET_TYPE_MAC:
            if target == _RULE_TARGET_TAG:
                raw_tags = raw_rule.get(_RAW_RULE_TAGS_KEY)
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

        if target_type == _RULE_TARGET_TYPE_NETWORK:
            return networks.get(target)

        if target_type == _RULE_TARGET_TYPE_CATEGORY:
            if target in categories:
                return categories[target]
            if target.startswith(_RULE_TARGET_LIST_PREFIX):
                trimmed_target = target.removeprefix(_RULE_TARGET_LIST_PREFIX)
                if trimmed_target in categories:
                    return categories[trimmed_target]
            if target.replace("_", "").isalnum() and not target.startswith(
                _RULE_TARGET_LIST_PREFIX
            ):
                return target.replace("_", " ")
            if "_" in target and not target.startswith(_RULE_TARGET_LIST_PREFIX):
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
            if lowered in _BOOLISH_TRUE_VALUES:
                return True
            if lowered in _BOOLISH_FALSE_VALUES:
                return False
        return None

    def _normalize_policy_rules(
        self, data: dict[str, object]
    ) -> tuple[FirewallaPolicyRule, ...]:
        """Normalize Firewalla policy rules into a stable typed MVP shape."""
        raw_rules = data.get(_RAW_POLICY_RULES_KEY)
        if not isinstance(raw_rules, list):
            return ()

        category_lookup = self._build_category_lookup(data)
        network_lookup = self._build_network_lookup(data)
        tag_lookup = self._build_named_lookup(data, "tags")
        device_tag_lookup = self._build_named_lookup(data, _RAW_DEVICE_TAGS_KEY)
        user_tag_lookup = self._build_named_lookup(data, _RAW_USER_TAGS_KEY)
        affiliated_user_lookup = self._build_affiliated_user_lookup(data)
        host_lookup = self._build_host_lookup(data)

        normalized_rules: list[FirewallaPolicyRule] = []
        for raw_rule in raw_rules:
            if not isinstance(raw_rule, dict):
                continue

            raw_rule_id = raw_rule.get(_RAW_RULE_ID_KEY)
            raw_action = raw_rule.get(_RAW_RULE_ACTION_KEY)
            raw_target = raw_rule.get(_RAW_RULE_TARGET_KEY)
            raw_target_type = raw_rule.get(_RAW_RULE_TYPE_KEY)
            if not isinstance(raw_rule_id, str) or not raw_rule_id:
                continue
            if not isinstance(raw_action, str) or not raw_action:
                continue
            if not isinstance(raw_target, str) or not raw_target:
                continue
            if not isinstance(raw_target_type, str) or not raw_target_type:
                continue

            direction = raw_rule.get(_RAW_RULE_DIRECTION_KEY)
            purpose = raw_rule.get(_RAW_RULE_PURPOSE_KEY)
            scope_value = raw_rule.get(_RAW_RULE_SCOPE_KEY)
            scope = (
                tuple(item for item in scope_value if isinstance(item, str) and item)
                if isinstance(scope_value, list)
                else ()
            )
            raw_tag_refs = raw_rule.get(_RAW_RULE_TAGS_KEY)
            tag_refs = (
                tuple(item for item in raw_tag_refs if isinstance(item, str) and item)
                if isinstance(raw_tag_refs, list)
                else ()
            )

            disabled = raw_rule.get(_RAW_RULE_DISABLED_KEY)
            enabled = disabled not in _DISABLED_TRUE_VALUES
            if isinstance(disabled, bool):
                enabled = not disabled

            activated_time = self._coerce_float(
                raw_rule.get(_RAW_RULE_ACTIVATED_TIME_KEY)
            )
            updated_time = self._coerce_float(raw_rule.get(_RAW_RULE_UPDATED_TIME_KEY))
            last_activated_time = self._coerce_float(
                raw_rule.get(_RAW_RULE_LAST_ACTIVATED_TIME_KEY)
            )
            expire_seconds = self._coerce_int(raw_rule.get(_RAW_RULE_EXPIRE_KEY))
            auto_delete_when_expires = self._coerce_boolish(
                raw_rule.get(_RAW_RULE_AUTO_DELETE_WHEN_EXPIRES_KEY)
            )
            dnsmasq_only = self._coerce_boolish(
                raw_rule.get(_RAW_RULE_DNSMASQ_ONLY_KEY)
            )
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
        raw_exception_rules = data.get(_RAW_EXCEPTION_RULES_KEY)
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
            system_status=self._build_system_status(data),
            latest_speed_test=self._build_latest_speed_test(data),
        )

    async def async_get_runtime_snapshot(self) -> FirewallaRuntimeSnapshot:
        """Fetch the runtime snapshot used by the coordinator."""
        return self.build_runtime_snapshot(await self.async_get_runtime_init_payload())

    async def async_get_system_info(self) -> FirewallaSystemInfo:
        """Fetch basic system information from the local init response."""
        return (await self.async_get_runtime_snapshot()).system_info
