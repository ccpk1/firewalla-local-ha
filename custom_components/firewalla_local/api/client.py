"""Strictly local Firewalla runtime client."""

# pylint: disable=too-many-lines

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
    FIREWALLA_PROTOCOL_CLIENT_ID,
    FIREWALLA_PROTOCOL_CLIENT_VERSION,
    LOGGER,
)
from ..models import (
    FirewallaApplianceIdentityInput,
    FirewallaApplianceRuntimeInput,
    FirewallaDiskUsageInput,
    FirewallaGroupRuntime,
    FirewallaHostRuntime,
    FirewallaHostVpnClient,
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
    FirewallaRuntimeSnapshot,
    FirewallaSpeedTestRecord,
    FirewallaUserAppUsage,
    FirewallaUserRuntime,
)
from .crypto import aes256_cbc_decrypt_from_base64, aes256_cbc_encrypt_to_base64
from .exceptions import (
    FirewallaAuthError,
    FirewallaConnectionError,
    FirewallaLocalRuntimeNotReadyError,
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
_GET_MESSAGE_TYPE: Final = "get"
_INIT_MESSAGE_TYPE: Final = "init"
_SET_MESSAGE_TYPE: Final = "set"
_COMMAND_ITEM_KEY: Final = "item"
_COMMAND_VALUE_KEY: Final = "value"
_COMMAND_GET_KEY: Final = "get"
_COMMAND_SET_POLICY: Final = "policy"
_COMMAND_POLICY_CREATE: Final = "policy:create"
_COMMAND_POLICY_DELETE: Final = "policy:delete"
_COMMAND_POLICY_UPDATE: Final = "policy:update"
_COMMAND_RUN_INTERNET_SPEED_TEST: Final = "runInternetSpeedtest"
_COMMAND_WAKE_HOST: Final = "wol:wake"
_COMMAND_SET_HOST: Final = "host"
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
_RAW_SYSTEM_DIST_CODENAME_KEY: Final = "distCodename"
_RAW_SYSTEM_GROUP_NAME_KEY: Final = "groupName"
_RAW_SYSTEM_DEVICE_NAME_KEY: Final = "device"
_RAW_SYSTEM_BOOTING_COMPLETE_KEY: Final = "bootingComplete"
_RAW_SYSTEM_CLOUD_CONNECTED_KEY: Final = "cloudConnected"
_RAW_SYSTEM_DDNS_KEY: Final = "ddns"
_RAW_SYSTEM_FIRMWARE_RELEASE_TYPE_KEY: Final = "firmwareReleaseType"
_RAW_SYSTEM_TIMEZONE_KEY: Final = "timezone"
_RAW_SYSTEM_PUBLIC_IP_KEY: Final = "publicIp"
_RAW_SYSTEM_PUBLIC_IPS_KEY: Final = "publicIps"
_RAW_SYSTEM_OS_UPTIME_KEY: Final = "osUptime"
_RAW_SYSTEM_SYS_METRICS_KEY: Final = "sysMetrics"
_RAW_SYSTEM_SYS_METRICS_CPU_USAGE_1_KEY: Final = "cpuUsage1"
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
_RAW_HOST_IP_KEY: Final = "ip"
_RAW_HOST_LAST_ACTIVE_KEY: Final = "lastActive"
_RAW_HOST_FLOWSUMMARY_KEY: Final = "flowsummary"
_RAW_HOST_STALE_KEY: Final = "stale"
_RAW_HOST_POLICY_KEY: Final = "policy"
_RAW_HOST_VPN_CLIENT_KEY: Final = "vpnClient"
_RAW_HOST_STATE_KEY: Final = "state"
_RAW_HOST_PROFILE_ID_KEY: Final = "profileId"
_RAW_USER_AFFILIATED_TAG_KEY: Final = "affiliatedTag"
_RAW_USER_APP_TIME_USAGE_TODAY_KEY: Final = "appTimeUsageToday"
_RAW_USER_INTERNET_TIME_USAGE_TODAY_KEY: Final = "internetTimeUsageToday"
_RAW_USER_TOTAL_MINS_KEY: Final = "totalMins"
_RAW_USER_UNIQUE_MINS_KEY: Final = "uniqueMins"
_RAW_USER_CATEGORY_KEY: Final = "category"
_RAW_USER_UID_KEY: Final = "uid"
_RAW_USER_TYPE_KEY: Final = "type"
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
_RAW_SPEED_TEST_WAN_UUID_KEY: Final = "wanUUID"
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
_RAW_APP_TIME_USAGE_KEY: Final = "appTimeUsage"
_RAW_MONTHLY_WAN_USAGE_KEY: Final = "monthlyDataUsageOnWans"
_RAW_LAST12_WAN_USAGE_KEY: Final = "last12monthlyDataUsageOnWans"

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
        timezone_name: str | None = None,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self.host = host
        self.gid = gid
        self.eid = eid
        self.aid = aid
        self.symmetric_key = symmetric_key
        self.device_name = device_name
        self.timezone_name = timezone_name

    def _build_fwmessage(
        self,
        *,
        message_type: str,
        data: dict[str, object],
        target: str = DEFAULT_INIT_TARGET,
    ) -> dict[str, object]:
        """Build the Firewalla-style local message envelope."""
        timezone_name = self.timezone_name or (
            datetime.now().astimezone().tzname() or _FWMESSAGE_TIMEZONE_UTC
        )
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
                    "appID": FIREWALLA_PROTOCOL_CLIENT_ID,
                    "platform": sys.platform,
                    "timezone": timezone_name,
                    "language": _FWMESSAGE_LANGUAGE_ENGLISH,
                    "version": FIREWALLA_PROTOCOL_CLIENT_VERSION,
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
        LOGGER.debug("Posting Firewalla local runtime payload to host %s", self.host)
        try:
            async with self._session.post(url, json=payload) as response:
                LOGGER.debug(
                    "Firewalla local runtime responded with HTTP %s for host %s",
                    response.status,
                    self.host,
                )
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
        """Send a local Encipher message and return one decrypted data object."""
        data_payload = await self._async_send_local_message_data(
            message_type=message_type,
            data=data,
            target=target,
        )
        if not isinstance(data_payload, dict):
            raise FirewallaProtocolError(
                "Firewalla local runtime payload did not include a data object"
            )

        return data_payload

    async def _async_send_local_message_data(
        self,
        *,
        message_type: str,
        data: dict[str, object],
        target: str = DEFAULT_INIT_TARGET,
    ) -> object:
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
            LOGGER.debug(
                "Firewalla local runtime returned unauthorized for host %s; "
                "retrying once",
                self.host,
            )
            response_status, response_text = await self._async_post_local_payload(
                payload
            )
            if response_status == 401:
                raise FirewallaAuthError(
                    "Firewalla local runtime returned unauthorized after one retry"
                )

        if response_status == 412:
            raise FirewallaLocalRuntimeNotReadyError(
                "Firewalla local runtime has not accepted the new pairing yet: "
                f"HTTP {response_status}: {response_text}"
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
        return data_payload

    async def async_get_runtime_init_payload(self) -> dict[str, object]:
        """Fetch the raw Firewalla init payload from the local runtime."""
        LOGGER.debug("Requesting Firewalla local init payload from host %s", self.host)
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

    async def async_update_rule_control_only(
        self,
        rule_id: str,
        *,
        enabled: bool,
        idle_ts: int | None = None,
    ) -> None:
        """Update only the control fields used for pause or resume."""
        value: dict[str, object] = {
            _RAW_RULE_ID_KEY: rule_id,
            _RAW_RULE_DISABLED_KEY: (
                _RAW_RULE_DISABLED_FALSE_VALUE
                if enabled
                else _RAW_RULE_DISABLED_TRUE_VALUE
            ),
            _RAW_RULE_UPDATED_TIME_KEY: time.time(),
            _RAW_RULE_IDLE_TS_KEY: (
                _RAW_RULE_IDLE_TS_EMPTY_VALUE if enabled or idle_ts is None else idle_ts
            ),
        }

        await self._async_send_local_message(
            message_type=_COMMAND_MESSAGE_TYPE,
            data={
                _COMMAND_ITEM_KEY: _COMMAND_POLICY_UPDATE,
                _COMMAND_VALUE_KEY: value,
            },
            target=DEFAULT_INIT_TARGET,
        )

    async def async_run_internet_speed_test(self, wan_uuid: str) -> dict[str, object]:
        """Run one internet speed test for the requested WAN interface."""
        return await self._async_send_local_message(
            message_type=_COMMAND_MESSAGE_TYPE,
            data={
                _COMMAND_ITEM_KEY: _COMMAND_RUN_INTERNET_SPEED_TEST,
                _COMMAND_VALUE_KEY: {_RAW_SPEED_TEST_WAN_UUID_KEY: wan_uuid},
            },
            target=DEFAULT_INIT_TARGET,
        )

    async def async_wake_host(self, host_mac: str) -> dict[str, object]:
        """Send one Wake-on-LAN command to the requested host."""
        return await self._async_send_local_message(
            message_type=_COMMAND_MESSAGE_TYPE,
            data={
                _COMMAND_ITEM_KEY: _COMMAND_WAKE_HOST,
            },
            target=host_mac,
        )

    async def async_set_host_policy(
        self, host_mac: str, policy_value: dict[str, object]
    ) -> dict[str, object]:
        """Write one host-scoped policy payload to the requested host."""
        return await self._async_send_local_message(
            message_type=_SET_MESSAGE_TYPE,
            data={
                _COMMAND_ITEM_KEY: _COMMAND_SET_POLICY,
                _COMMAND_VALUE_KEY: policy_value,
            },
            target=host_mac,
        )

    async def async_set_host_name(
        self,
        host_mac: str,
        host_name: str,
    ) -> dict[str, object]:
        """Write one host-scoped custom name to the requested host."""
        data_payload = await self._async_send_local_message_data(
            message_type=_SET_MESSAGE_TYPE,
            data={
                _COMMAND_ITEM_KEY: _COMMAND_SET_HOST,
                _COMMAND_VALUE_KEY: {_RAW_NAME_KEY: host_name},
            },
            target=host_mac,
        )
        if data_payload is None:
            return {}
        if isinstance(data_payload, dict):
            return data_payload
        raise FirewallaProtocolError(
            "Firewalla host rename response did not include "
            "a JSON object or null data payload"
        )

    async def async_get_monthly_wan_usage_payload(self) -> dict[str, object]:
        """Fetch the current-month WAN usage payload from the local runtime."""
        return await self._async_send_local_message(
            message_type=_GET_MESSAGE_TYPE,
            data={
                _COMMAND_ITEM_KEY: _RAW_MONTHLY_WAN_USAGE_KEY,
            },
            target=DEFAULT_INIT_TARGET,
        )

    async def async_get_last12_monthly_wan_usage_payload(self) -> dict[str, object]:
        """Fetch the last-12-month WAN usage payload from the local runtime."""
        return await self._async_send_local_message(
            message_type=_GET_MESSAGE_TYPE,
            data={
                _COMMAND_ITEM_KEY: _RAW_LAST12_WAN_USAGE_KEY,
                _COMMAND_VALUE_KEY: {},
            },
            target=DEFAULT_INIT_TARGET,
        )

    async def async_get_usage_history_payload(
        self,
        *,
        scope_type: str,
        target: str,
        begin_timestamp: int,
        end_timestamp: int,
        granularity: str,
        app_ids: tuple[str, ...] | None,
    ) -> dict[str, object]:
        """Fetch one scoped usage-history payload from the local runtime."""
        data: dict[str, object] = {
            _COMMAND_ITEM_KEY: _RAW_APP_TIME_USAGE_KEY,
            _RAW_USER_TYPE_KEY: scope_type,
            "begin": begin_timestamp,
            "end": end_timestamp,
            "granularity": granularity,
        }
        if app_ids is not None:
            data["apps"] = list(app_ids)

        return await self._async_send_local_message(
            message_type=_GET_MESSAGE_TYPE,
            data=data,
            target=target,
        )

    async def async_get_wan_events_payload(
        self,
        *,
        limit_count: int,
        limit_offset: int,
    ) -> list[dict[str, object]]:
        """Fetch the WAN events timeline payload from the local runtime."""
        data_payload = await self._async_send_local_message_data(
            message_type=_GET_MESSAGE_TYPE,
            data={
                _COMMAND_ITEM_KEY: "events",
                _COMMAND_VALUE_KEY: {
                    "limit_count": limit_count,
                    "limit_offset": limit_offset,
                    "parse_json": True,
                    "reverse": True,
                },
            },
            target=DEFAULT_INIT_TARGET,
        )
        if not isinstance(data_payload, list):
            raise FirewallaProtocolError(
                "Firewalla local runtime payload did not include an events list"
            )

        return [item for item in data_payload if isinstance(item, dict)]

    async def async_get_network_interface_payload(
        self,
        *,
        network_uuid: str,
    ) -> dict[str, object]:
        """Fetch one network-interface summary payload from the local runtime."""
        data_payload = await self._async_send_local_message_data(
            message_type=_GET_MESSAGE_TYPE,
            data={_COMMAND_ITEM_KEY: "intf"},
            target=network_uuid,
        )
        if not isinstance(data_payload, dict):
            raise FirewallaProtocolError(
                "Firewalla local runtime payload did not include an intf object"
            )

        return data_payload

    def _extract_appliance_identity(
        self, data: dict[str, object]
    ) -> FirewallaApplianceIdentityInput:
        """Extract the protocol-facing appliance identity input."""
        model = data.get(_RAW_SYSTEM_MODEL_KEY)
        serial_number = data.get(_RAW_SYSTEM_CPU_ID_KEY)
        software_version = data.get(_RAW_SYSTEM_LONG_VERSION_KEY)

        return FirewallaApplianceIdentityInput(
            host=self.host,
            group_name=(
                group_name
                if isinstance((group_name := data.get(_RAW_SYSTEM_GROUP_NAME_KEY)), str)
                and group_name
                else None
            ),
            device_name=(
                device_name
                if isinstance(
                    (device_name := data.get(_RAW_SYSTEM_DEVICE_NAME_KEY)), str
                )
                and device_name
                else None
            ),
            model=model if isinstance(model, str) else None,
            serial_number=serial_number if isinstance(serial_number, str) else None,
            software_version=(
                software_version if isinstance(software_version, str) else None
            ),
        )

    def _extract_appliance_runtime(
        self, data: dict[str, object]
    ) -> FirewallaApplianceRuntimeInput:
        """Extract the protocol-facing appliance runtime input."""
        raw_sys_metrics = data.get(_RAW_SYSTEM_SYS_METRICS_KEY)
        sys_metrics = raw_sys_metrics if isinstance(raw_sys_metrics, dict) else {}
        raw_public_ips = data.get(_RAW_SYSTEM_PUBLIC_IPS_KEY)
        public_ips = (
            {
                interface_name: public_ip
                for interface_name, public_ip in raw_public_ips.items()
                if isinstance(interface_name, str)
                and interface_name
                and isinstance(public_ip, str)
                and public_ip
            }
            if isinstance(raw_public_ips, dict)
            else {}
        )

        raw_disk_info = sys_metrics.get(_RAW_SYSTEM_SYS_METRICS_DISK_INFO_KEY)
        disk_info = raw_disk_info if isinstance(raw_disk_info, list) else []
        disk_usages = tuple(
            FirewallaDiskUsageInput(
                mount=mount,
                capacity_ratio=self._coerce_float(
                    raw_disk.get(_RAW_SYSTEM_SYS_METRICS_DISK_CAPACITY_KEY)
                ),
                used_bytes=self._coerce_float(
                    raw_disk.get(_RAW_SYSTEM_SYS_METRICS_DISK_USED_KEY)
                ),
                size_bytes=self._coerce_float(
                    raw_disk.get(_RAW_SYSTEM_SYS_METRICS_DISK_SIZE_KEY)
                ),
            )
            for raw_disk in disk_info
            if isinstance(raw_disk, dict)
            and isinstance(
                (mount := raw_disk.get(_RAW_SYSTEM_SYS_METRICS_DISK_MOUNT_KEY)), str
            )
            and mount
        )

        return FirewallaApplianceRuntimeInput(
            booting_complete=self._coerce_boolish(
                data.get(_RAW_SYSTEM_BOOTING_COMPLETE_KEY)
            ),
            dist_codename=(
                dist_codename
                if isinstance(
                    (dist_codename := data.get(_RAW_SYSTEM_DIST_CODENAME_KEY)),
                    str,
                )
                and dist_codename
                else None
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
            timezone_name=(
                timezone_name
                if isinstance(
                    (timezone_name := data.get(_RAW_SYSTEM_TIMEZONE_KEY)),
                    str,
                )
                and timezone_name
                else None
            ),
            public_ip=(
                public_ip
                if isinstance((public_ip := data.get(_RAW_SYSTEM_PUBLIC_IP_KEY)), str)
                and public_ip
                else None
            ),
            public_ips=public_ips or None,
            cpu_usage_1m=self._extract_cpu_usage_1m(sys_metrics),
            memory_usage_ratio=self._coerce_float(
                sys_metrics.get(_RAW_SYSTEM_SYS_METRICS_MEMORY_USAGE_KEY)
            ),
            total_memory_mb=self._coerce_float(
                sys_metrics.get(_RAW_SYSTEM_SYS_METRICS_TOTAL_MEMORY_KEY)
            ),
            uptime_seconds=self._coerce_int(data.get(_RAW_SYSTEM_OS_UPTIME_KEY)),
            disk_usages=disk_usages,
        )

    def _extract_cpu_usage_1m(self, sys_metrics: dict[str, object]) -> float | None:
        """Extract a 1-minute average CPU usage percent from cpuUsage1 samples."""
        raw_samples = sys_metrics.get(_RAW_SYSTEM_SYS_METRICS_CPU_USAGE_1_KEY)
        if not isinstance(raw_samples, list):
            return None

        used_percent_samples: list[float] = []
        for raw_sample in raw_samples:
            if not isinstance(raw_sample, dict):
                continue

            user_percent = self._coerce_float(raw_sample.get("user"))
            sys_percent = self._coerce_float(raw_sample.get("sys"))
            iowait_percent = self._coerce_float(raw_sample.get("iowait"))
            if user_percent is None or sys_percent is None or iowait_percent is None:
                continue

            used_percent_samples.append(user_percent + sys_percent + iowait_percent)

        if not used_percent_samples:
            return None

        return round(sum(used_percent_samples) / len(used_percent_samples), 1)

    def _extract_speed_test_records(
        self, data: dict[str, object]
    ) -> tuple[FirewallaSpeedTestRecord, ...]:
        """Extract protocol-facing speed-test records from the payload."""
        raw_results = data.get(_RAW_SPEED_TEST_RESULTS_KEY)
        if not isinstance(raw_results, list):
            return ()

        records: list[FirewallaSpeedTestRecord] = []
        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                continue

            raw_client = raw_result.get(_RAW_SPEED_TEST_CLIENT_KEY)
            raw_measurement = raw_result.get(_RAW_SPEED_TEST_RESULT_KEY)
            raw_server = raw_result.get(_RAW_SPEED_TEST_SERVER_KEY)

            client = raw_client if isinstance(raw_client, dict) else {}
            measurement = raw_measurement if isinstance(raw_measurement, dict) else {}
            server = raw_server if isinstance(raw_server, dict) else {}

            records.append(
                FirewallaSpeedTestRecord(
                    tested_at_timestamp=self._coerce_float(
                        raw_result.get(_RAW_SPEED_TEST_TIMESTAMP_KEY)
                    ),
                    download_mbps=self._coerce_float(
                        measurement.get(_RAW_SPEED_TEST_DOWNLOAD_KEY)
                    ),
                    upload_mbps=self._coerce_float(
                        measurement.get(_RAW_SPEED_TEST_UPLOAD_KEY)
                    ),
                    latency_ms=self._coerce_float(
                        measurement.get(_RAW_SPEED_TEST_LATENCY_KEY)
                    ),
                    jitter_ms=self._coerce_float(
                        measurement.get(_RAW_SPEED_TEST_JITTER_KEY)
                    ),
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
                        if isinstance((isp := client.get(_RAW_SPEED_TEST_ISP_KEY)), str)
                        and isp
                        else None
                    ),
                    public_ip=(
                        public_ip
                        if isinstance(
                            (public_ip := client.get(_RAW_SPEED_TEST_PUBLIC_IP_KEY)),
                            str,
                        )
                        and public_ip
                        else None
                    ),
                    server_country=(
                        server_country
                        if isinstance(
                            (
                                server_country := server.get(
                                    _RAW_SPEED_TEST_SERVER_COUNTRY_KEY
                                )
                            ),
                            str,
                        )
                        and server_country
                        else None
                    ),
                    server_host=(
                        server_host
                        if isinstance(
                            (
                                server_host := server.get(
                                    _RAW_SPEED_TEST_SERVER_HOST_KEY
                                )
                            ),
                            str,
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
                            (
                                server_sponsor := server.get(
                                    _RAW_SPEED_TEST_SERVER_SPONSOR_KEY
                                )
                            ),
                            str,
                        )
                        and server_sponsor
                        else None
                    ),
                    manual=self._coerce_boolish(
                        raw_result.get(_RAW_SPEED_TEST_MANUAL_KEY)
                    ),
                    success=self._coerce_boolish(
                        raw_result.get(_RAW_SPEED_TEST_SUCCESS_KEY)
                    ),
                    vendor=(
                        vendor
                        if isinstance(
                            (vendor := raw_result.get(_RAW_SPEED_TEST_VENDOR_KEY)), str
                        )
                        and vendor
                        else None
                    ),
                    wan_uuid=(
                        wan_uuid
                        if isinstance(
                            (wan_uuid := raw_result.get(_RAW_UUID_KEY)),
                            str,
                        )
                        and wan_uuid
                        else None
                    ),
                )
            )

        return tuple(records)

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
        return {
            host.mac: host.display_name for host in self._normalize_host_inventory(data)
        }

    @staticmethod
    def _normalized_optional_string(value: object) -> str | None:
        """Return a stripped string when one is present."""
        if not isinstance(value, str):
            return None
        stripped_value = value.strip()
        return stripped_value or None

    def _resolve_host_display_names(
        self, raw_host: dict[str, object]
    ) -> tuple[str, str | None]:
        """Resolve the best display name and one fallback name for a host."""
        raw_candidates = (
            raw_host.get(_RAW_NAME_KEY),
            raw_host.get(_RAW_HOST_BACKUP_NAME_KEY),
            raw_host.get("dhcpName"),
            raw_host.get("bonjourName"),
            raw_host.get("localDomain"),
        )
        candidates = [
            candidate
            for raw_candidate in raw_candidates
            if (candidate := self._normalized_optional_string(raw_candidate))
        ]
        unique_candidates = tuple(dict.fromkeys(candidates))

        if unique_candidates:
            return unique_candidates[0], unique_candidates[1] if len(
                unique_candidates
            ) > 1 else None

        if ip_address := self._normalized_optional_string(
            raw_host.get(_RAW_HOST_IP_KEY)
        ):
            return ip_address, None

        host_mac = self._normalized_optional_string(raw_host.get(_RAW_HOST_MAC_KEY))
        return host_mac or _DEFAULT_BOX_NAME, None

    def _resolve_host_group_name(
        self,
        raw_host: dict[str, object],
        *,
        tags: dict[str, str],
        affiliated_users: dict[str, tuple[str, ...]],
    ) -> str | None:
        """Resolve one readable group label from host tag references."""
        raw_tags = raw_host.get("tags")
        if not isinstance(raw_tags, list):
            return None

        resolved_tags: list[str] = []
        for raw_tag_id in raw_tags:
            if not isinstance(raw_tag_id, str) or not raw_tag_id:
                continue
            if not (tag_name := tags.get(raw_tag_id)):
                continue
            if user_names := affiliated_users.get(raw_tag_id):
                resolved_tags.append(f"{tag_name} ({', '.join(user_names)})")
            else:
                resolved_tags.append(tag_name)

        if not resolved_tags:
            return None
        return ", ".join(dict.fromkeys(resolved_tags))

    def _resolve_host_connection_type(
        self,
        raw_host: dict[str, object],
        *,
        device_tags: dict[str, str],
    ) -> str | None:
        """Resolve one readable connection-type label from host device tags."""
        raw_device_tags = raw_host.get(_RAW_DEVICE_TAGS_KEY)
        if not isinstance(raw_device_tags, list):
            return None

        resolved_types = [
            device_tag_name
            for raw_device_tag in raw_device_tags
            if isinstance(raw_device_tag, str)
            and (device_tag_name := device_tags.get(raw_device_tag))
        ]
        if not resolved_types:
            return None
        return ", ".join(dict.fromkeys(resolved_types))

    def _normalize_host_vpn_client(
        self, raw_host: dict[str, object]
    ) -> FirewallaHostVpnClient | None:
        """Normalize the minimal VPN client reference exposed on one host."""
        raw_policy = raw_host.get(_RAW_HOST_POLICY_KEY)
        if not isinstance(raw_policy, dict):
            return None

        raw_vpn_client = raw_policy.get(_RAW_HOST_VPN_CLIENT_KEY)
        if not isinstance(raw_vpn_client, dict):
            return None

        profile_id = self._normalized_optional_string(
            raw_vpn_client.get(_RAW_HOST_PROFILE_ID_KEY)
        )
        state = self._coerce_boolish(raw_vpn_client.get(_RAW_HOST_STATE_KEY))

        if profile_id is None and state is None:
            return None

        return FirewallaHostVpnClient(profile_id=profile_id, state=state)

    def _normalize_host_inventory(
        self, data: dict[str, object]
    ) -> tuple[FirewallaHostRuntime, ...]:
        """Normalize the minimal host inventory used by watched-device surfaces."""
        raw_hosts = data.get(_RAW_HOSTS_KEY)
        if not isinstance(raw_hosts, list):
            return ()

        network_lookup = self._build_network_lookup(data)
        tag_lookup = self._build_named_lookup(data, "tags")
        device_tag_lookup = self._build_named_lookup(data, _RAW_DEVICE_TAGS_KEY)
        affiliated_user_lookup = self._build_affiliated_user_lookup(data)

        normalized_hosts: list[FirewallaHostRuntime] = []
        for raw_host in raw_hosts:
            if not isinstance(raw_host, dict):
                continue

            host_mac = self._normalized_optional_string(raw_host.get(_RAW_HOST_MAC_KEY))
            if host_mac is None:
                continue

            display_name, fallback_name = self._resolve_host_display_names(raw_host)
            flowsummary = raw_host.get(_RAW_HOST_FLOWSUMMARY_KEY)
            normalized_hosts.append(
                FirewallaHostRuntime(
                    mac=host_mac,
                    display_name=display_name,
                    fallback_name=fallback_name,
                    ip_address=self._normalized_optional_string(
                        raw_host.get(_RAW_HOST_IP_KEY)
                    ),
                    group_name=self._resolve_host_group_name(
                        raw_host,
                        tags=tag_lookup,
                        affiliated_users=affiliated_user_lookup,
                    ),
                    network_name=(
                        network_lookup.get(interface_id)
                        if (
                            interface_id := self._normalized_optional_string(
                                raw_host.get(_RAW_INTF_KEY)
                            )
                        )
                        is not None
                        else None
                    ),
                    connection_type=self._resolve_host_connection_type(
                        raw_host,
                        device_tags=device_tag_lookup,
                    ),
                    last_active=self._coerce_float(
                        raw_host.get(_RAW_HOST_LAST_ACTIVE_KEY)
                    ),
                    download_bytes=(
                        self._coerce_int(flowsummary.get("inbytes"))
                        if isinstance(flowsummary, dict)
                        else None
                    ),
                    upload_bytes=(
                        self._coerce_int(flowsummary.get("outbytes"))
                        if isinstance(flowsummary, dict)
                        else None
                    ),
                    stale=self._coerce_boolish(raw_host.get(_RAW_HOST_STALE_KEY)),
                    vpn_client=self._normalize_host_vpn_client(raw_host),
                    group_ids=tuple(
                        sorted(
                            raw_group_id
                            for raw_group_id in raw_host.get("tags", [])
                            if isinstance(raw_group_id, str) and raw_group_id
                        )
                    )
                    if isinstance(raw_host.get("tags"), list)
                    else (),
                    user_ids=tuple(
                        sorted(
                            raw_user_id
                            for raw_user_id in raw_host.get(_RAW_USER_TAGS_KEY, [])
                            if isinstance(raw_user_id, str) and raw_user_id
                        )
                    )
                    if isinstance(raw_host.get(_RAW_USER_TAGS_KEY), list)
                    else (),
                )
            )

        return tuple(normalized_hosts)

    def _normalize_user_inventory(
        self, data: dict[str, object]
    ) -> tuple[FirewallaUserRuntime, ...]:
        """Normalize watched-user data from the local runtime payload."""
        raw_user_tags = data.get(_RAW_USER_TAGS_KEY)
        if not isinstance(raw_user_tags, dict):
            return ()

        group_lookup = self._build_named_lookup(data, "tags")
        normalized_users: list[FirewallaUserRuntime] = []
        for raw_user_id, raw_user in raw_user_tags.items():
            if not isinstance(raw_user_id, str) or not raw_user_id:
                continue
            if not isinstance(raw_user, dict):
                continue

            user_type = self._normalized_optional_string(
                raw_user.get(_RAW_USER_TYPE_KEY)
            )
            if user_type is not None and user_type != "user":
                continue

            user_id = self._normalized_optional_string(raw_user.get(_RAW_USER_UID_KEY))
            if user_id is None:
                user_id = raw_user_id

            user_name = self._normalized_optional_string(raw_user.get(_RAW_NAME_KEY))
            if user_name is None:
                user_name = user_id

            affiliated_group_id = self._normalized_optional_string(
                raw_user.get(_RAW_USER_AFFILIATED_TAG_KEY)
            )
            raw_app_usage_today = raw_user.get(_RAW_USER_APP_TIME_USAGE_TODAY_KEY)
            raw_internet_usage_today = raw_user.get(
                _RAW_USER_INTERNET_TIME_USAGE_TODAY_KEY
            )
            app_usage_today = (
                self._normalize_user_app_usage_today(raw_app_usage_today)
                if isinstance(raw_app_usage_today, dict)
                else ()
            )
            raw_total_minutes_today = (
                self._coerce_int(raw_internet_usage_today.get(_RAW_USER_TOTAL_MINS_KEY))
                if isinstance(raw_internet_usage_today, dict)
                else None
            )
            raw_unique_minutes_today = (
                self._coerce_int(
                    raw_internet_usage_today.get(_RAW_USER_UNIQUE_MINS_KEY)
                )
                if isinstance(raw_internet_usage_today, dict)
                else None
            )

            if raw_total_minutes_today is None and isinstance(
                raw_app_usage_today, dict
            ):
                raw_total_minutes_today = self._coerce_int(
                    raw_app_usage_today.get(_RAW_USER_TOTAL_MINS_KEY)
                )

            if raw_unique_minutes_today is None and isinstance(
                raw_app_usage_today, dict
            ):
                raw_unique_minutes_today = self._coerce_int(
                    raw_app_usage_today.get(_RAW_USER_UNIQUE_MINS_KEY)
                )

            total_minutes_today = raw_total_minutes_today
            if total_minutes_today is None and app_usage_today:
                total_minutes_today = sum(
                    usage.total_minutes for usage in app_usage_today
                )

            unique_minutes_today = raw_unique_minutes_today
            if unique_minutes_today is None and app_usage_today:
                unique_minutes_today = sum(
                    usage.unique_minutes for usage in app_usage_today
                )

            normalized_users.append(
                FirewallaUserRuntime(
                    user_id=user_id,
                    name=user_name,
                    affiliated_group_id=affiliated_group_id,
                    affiliated_group_name=(
                        group_lookup.get(affiliated_group_id)
                        if affiliated_group_id is not None
                        else None
                    ),
                    total_minutes_today=total_minutes_today,
                    unique_minutes_today=unique_minutes_today,
                    app_usage_today=app_usage_today,
                )
            )

        return tuple(
            sorted(
                normalized_users,
                key=lambda user: (user.name.casefold(), user.user_id),
            )
        )

    def _normalize_group_inventory(
        self, data: dict[str, object]
    ) -> tuple[FirewallaGroupRuntime, ...]:
        """Normalize group inventory from the Firewalla tag collection."""
        group_lookup = self._build_named_lookup(data, "tags")
        return tuple(
            FirewallaGroupRuntime(group_id=group_id, name=group_name)
            for group_id, group_name in sorted(
                group_lookup.items(),
                key=lambda item: (item[1].casefold(), item[0]),
            )
        )

    def _normalize_user_app_usage_today(
        self, raw_app_usage_today: dict[str, object]
    ) -> tuple[FirewallaUserAppUsage, ...]:
        """Normalize per-app usage buckets from one user payload."""
        normalized_usage: list[FirewallaUserAppUsage] = []
        for app_id, raw_app_usage in raw_app_usage_today.items():
            if app_id in {_RAW_USER_TOTAL_MINS_KEY, _RAW_USER_UNIQUE_MINS_KEY}:
                continue
            if not isinstance(app_id, str) or not app_id:
                continue
            if not isinstance(raw_app_usage, dict):
                continue

            total_minutes = self._coerce_int(
                raw_app_usage.get(_RAW_USER_TOTAL_MINS_KEY)
            )
            unique_minutes = self._coerce_int(
                raw_app_usage.get(_RAW_USER_UNIQUE_MINS_KEY)
            )
            if total_minutes is None and unique_minutes is None:
                continue

            normalized_usage.append(
                FirewallaUserAppUsage(
                    app_id=app_id,
                    category=self._normalized_optional_string(
                        raw_app_usage.get(_RAW_USER_CATEGORY_KEY)
                    ),
                    total_minutes=0 if total_minutes is None else total_minutes,
                    unique_minutes=0 if unique_minutes is None else unique_minutes,
                )
            )

        return tuple(
            sorted(
                normalized_usage,
                key=lambda usage: (-usage.total_minutes, usage.app_id.casefold()),
            )
        )

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
        self,
        data: dict[str, object],
        *,
        host_lookup: dict[str, str],
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
        hosts = self._normalize_host_inventory(data)
        groups = self._normalize_group_inventory(data)
        users = self._normalize_user_inventory(data)
        return FirewallaRuntimeSnapshot(
            appliance_identity=self._extract_appliance_identity(data),
            appliance_runtime=self._extract_appliance_runtime(data),
            policy_rules=self._normalize_policy_rules(
                data,
                host_lookup={host.mac: host.display_name for host in hosts},
            ),
            exception_rule_count=self._count_exception_rules(data),
            hosts=hosts,
            groups=groups,
            users=users,
            speed_test_results=self._extract_speed_test_records(data),
        )

    async def async_get_runtime_snapshot(self) -> FirewallaRuntimeSnapshot:
        """Fetch the runtime snapshot used by the coordinator."""
        return self.build_runtime_snapshot(await self.async_get_runtime_init_payload())
