"""Constants for the Firewalla Local integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Final

DOMAIN: Final = "firewalla_local"
LOGGER: Final = logging.getLogger(__name__)
MANUFACTURER: Final = "Firewalla"

# Entity state attributes
ATTR_INTEGRATION: Final = "integration"
ATTR_PURPOSE: Final = "purpose"
ATTR_RULE_PURPOSE: Final = "purpose"
ATTR_RULE_ID: Final = "rule_id"
ATTR_RULE_NAME: Final = "rule_name"
ATTR_RULE_APPLIES_TO: Final = "applies_to"
ATTR_RULE_APPLIES_TO_KIND: Final = "applies_to_kind"
ATTR_RULE_CATEGORY: Final = "category"
ATTR_RULE_CUSTOM_NAME: Final = "custom_name"
ATTR_RULE_ACTION: Final = "action"
ATTR_RULE_TEMPLATE_TARGET: Final = "target"
ATTR_RULE_TARGET_TYPE: Final = "target_type"
ATTR_RULE_TAG_REFS: Final = "tag_refs"
ATTR_RULE_NOTES: Final = "notes"
ATTR_RULE_IS_PAUSED: Final = "is_paused"
ATTR_RULE_PAUSE_UNTIL: Final = "pause_until"
ATTR_RULE_PAUSE_REMAINING_SECONDS: Final = "pause_remaining_seconds"
ATTR_RULE_ACTIVE_TIME_SCHEDULE: Final = "active_time_schedule"
ATTR_RULE_APP_TIME_PERIOD: Final = "app_time_period"
ATTR_RULE_APP_TIME_QUOTA: Final = "app_time_quota"
ATTR_RULE_APP_TIME_USED: Final = "app_time_used"
ATTR_RULE_SCHEDULE_START_CRON: Final = "schedule_start_cron"
ATTR_RULE_SCHEDULE_DURATION: Final = "schedule_duration"
ATTR_RULE_SCHEDULE_DAYS: Final = "schedule_days"
ATTR_RULE_SCHEDULE_NEXT_START: Final = "schedule_next_start"
ATTR_RULE_SCHEDULE_NEXT_END: Final = "schedule_next_end"
ATTR_RULE_TIME_LIMIT_PERIOD_CRON: Final = "time_limit_period_cron"
ATTR_RULE_TIME_LIMIT_QUOTA: Final = "time_limit_quota"
ATTR_RULE_TIME_LIMIT_USED: Final = "time_limit_used"
ATTR_RULE_CURRENT_STATE_REASON: Final = "current_state_reason"
ATTR_RULE_LOCAL_PORT: Final = "local_port"
ATTR_RULE_PROTOCOL: Final = "protocol"
ATTR_RULE_TRUST: Final = "trust"
ATTR_RULE_USE_BF: Final = "use_bf"
ATTR_RULE_UPNP: Final = "upnp"
ATTR_RULE_QDISC: Final = "qdisc"
ATTR_RULE_RATE_LIMIT: Final = "rate_limit"
ATTR_RULE_TRAFFIC_DIRECTION: Final = "traffic_direction"
ATTR_RULE_APP_NAME: Final = "app_name"
ATTR_RULE_APP_UID: Final = "app_uid"
ATTR_RULE_DISTURB_LEVEL: Final = "disturb_level"
ATTR_SYSTEM_BOX_IMAGE_CODENAME: Final = "box_image_codename"
ATTR_SYSTEM_BOX_IMAGE_VERSION: Final = "box_image_version"
ATTR_SYSTEM_BOOT_COMPLETE: Final = "boot_complete"
ATTR_SYSTEM_CPU_USAGE_1M: Final = "cpu_usage_1m"
ATTR_SYSTEM_CLOUD_CONNECTED: Final = "cloud_connected"
ATTR_SYSTEM_DEVICES_OFFLINE: Final = "devices_offline"
ATTR_SYSTEM_DEVICES_ONLINE: Final = "devices_online"
ATTR_SYSTEM_DEVICES_TOTAL: Final = "devices_total"
ATTR_SYSTEM_CURRENT_WAN_USAGE: Final = "current_wan_usage"
ATTR_SYSTEM_DDNS: Final = "ddns"
ATTR_SYSTEM_DISK_USAGE_PERCENT_BY_MOUNT: Final = "disk_usage_percent_by_mount"
ATTR_SYSTEM_FIRMWARE_RELEASE_TYPE: Final = "firmware_release_type"
ATTR_SYSTEM_MEMORY_FREE_MB: Final = "memory_free_mb"
ATTR_SYSTEM_SOFTWARE_VERSION: Final = "software_version"
ATTR_SYSTEM_MEMORY_USAGE_PERCENT: Final = "memory_usage_percent"
ATTR_SYSTEM_RUNTIME_DATA_UPDATED_AT: Final = "runtime_data_updated_at"
ATTR_SYSTEM_UPTIME: Final = "uptime"
ATTR_SYSTEM_UPTIME_SECONDS: Final = "uptime_seconds"
ATTR_SYSTEM_WAN_IP: Final = "wan_ip"
ATTR_SYSTEM_WAN_IPS: Final = "wan_ips"
ATTR_WATCHED_DEVICE_CONNECTION_TYPE: Final = "connection_type"
ATTR_WATCHED_DEVICE_DEVICE_GROUP: Final = "device_group"
ATTR_WATCHED_DEVICE_HOST_NAME: Final = "host_name"
ATTR_WATCHED_DEVICE_HOST_DEVICE_TYPE: Final = "host_device_type"
ATTR_WATCHED_DEVICE_DNS_DOMAIN: Final = "dns_domain"
ATTR_WATCHED_DEVICE_DOWNLOAD_USAGE: Final = "download_usage"
ATTR_WATCHED_DEVICE_DNS_FQDN: Final = "dns_fqdn"
ATTR_WATCHED_DEVICE_DNS_HOSTNAME: Final = "dns_hostname"
ATTR_WATCHED_DEVICE_IP_ADDRESS: Final = "ip_address"
ATTR_WATCHED_DEVICE_LAST_ACTIVE: Final = "last_active"
ATTR_WATCHED_DEVICE_NETWORK_NAME: Final = "network_name"
ATTR_WATCHED_DEVICE_UPLOAD_USAGE: Final = "upload_usage"
ATTR_WATCHED_USER_APP_USAGE_BY_APP: Final = "app_usage_by_app"
ATTR_WATCHED_USER_ASSOCIATED_DEVICE_COUNT: Final = "associated_device_count"
ATTR_WATCHED_USER_ASSOCIATED_DEVICE_GROUP: Final = "associated_device_group"
ATTR_WATCHED_USER_ASSOCIATED_DEVICES: Final = "associated_devices"
ATTR_WATCHED_USER_LAST_ACTIVE: Final = "last_active"
ATTR_WATCHED_USER_UNIQUE_USAGE_TODAY: Final = "unique_usage_today"
ATTR_SPEED_TEST_DOWNLOAD_MBYTES: Final = "download_megabytes"
ATTR_SPEED_TEST_ISP: Final = "isp"
ATTR_SPEED_TEST_JITTER: Final = "jitter"
ATTR_SPEED_TEST_LATENCY: Final = "latency"
ATTR_SPEED_TEST_MANUAL: Final = "manual"
ATTR_SPEED_TEST_PACKET_LOSS: Final = "packet_loss"
ATTR_SPEED_TEST_PUBLIC_IP: Final = "public_ip"
ATTR_SPEED_TEST_SERVER_COUNTRY: Final = "server_country"
ATTR_SPEED_TEST_SERVER_HOST: Final = "server_host"
ATTR_SPEED_TEST_SERVER_ID: Final = "server_id"
ATTR_SPEED_TEST_SERVER_LOCATION: Final = "server_location"
ATTR_SPEED_TEST_SERVER_SPONSOR: Final = "server_sponsor"
ATTR_SPEED_TEST_SUCCESS: Final = "success"
ATTR_SPEED_TEST_TESTED_AT: Final = "tested_at"
ATTR_SPEED_TEST_UPLOAD: Final = "upload_speed"
ATTR_SPEED_TEST_UPLOAD_MBYTES: Final = "upload_megabytes"
ATTR_SPEED_TEST_VENDOR: Final = "vendor"
ATTR_SPEED_TEST_WAN_NAME: Final = "wan_name"
ATTR_SPEED_TEST_WAN_UUID: Final = "wan_uuid"

# Service input fields
SERVICE_FIELD_CONFIG_ENTRY_ID: Final = "config_entry_id"
SERVICE_FIELD_CONFIG_ENTRY_NAME: Final = "config_entry_name"
SERVICE_FIELD_DETAIL: Final = "detail"
SERVICE_FIELD_ENABLED: Final = "enabled"
SERVICE_FIELD_INCLUDE: Final = "include"
SERVICE_FIELD_CURRENT_PERIODS: Final = "current_periods"
SERVICE_FIELD_HISTORY_COUNT: Final = "history_count"
SERVICE_FIELD_HISTORY_PERIOD: Final = "history_period"
SERVICE_FIELD_HOST_ID: Final = "host_id"
SERVICE_FIELD_HOST_MAC: Final = "host_mac"
SERVICE_FIELD_HOST_NAME: Final = "host_name"
SERVICE_FIELD_CONFIRM: Final = "confirm"
SERVICE_FIELD_DNS_HOSTNAME: Final = "dns_hostname"
SERVICE_FIELD_MODE: Final = "mode"
SERVICE_FIELD_NEW_NAME: Final = "new_name"
SERVICE_FIELD_HOST_DEVICE_TYPE: Final = "host_device_type"
SERVICE_FIELD_USAGE_HISTORY_APP_IDS: Final = "app_ids"
SERVICE_FIELD_USAGE_HISTORY_BEGIN: Final = "begin"
SERVICE_FIELD_USAGE_HISTORY_END: Final = "end"
SERVICE_FIELD_USAGE_HISTORY_GRANULARITY: Final = "granularity"
SERVICE_FIELD_USAGE_HISTORY_SCOPE_KIND: Final = "scope_kind"
SERVICE_FIELD_USAGE_HISTORY_SCOPE_TARGET: Final = "scope_target"
SERVICE_FIELD_LIMIT: Final = "limit"
SERVICE_FIELD_NETWORK_NAME: Final = "network_name"
SERVICE_FIELD_NETWORK_UUID: Final = "network_uuid"
SERVICE_FIELD_OFFSET: Final = "offset"
SERVICE_FIELD_REFRESH: Final = "refresh"
SERVICE_FIELD_RESERVED_IPV4: Final = "reserved_ipv4"
SERVICE_FIELD_SECTIONS: Final = "sections"
SERVICE_FIELD_RULE_DURATION: Final = "duration"
SERVICE_FIELD_RULE_RESUME_AT: Final = "resume_at"
SERVICE_FIELD_RULE_TARGET: Final = "rule_target"
SERVICE_FIELD_TOP_N: Final = "top_n"
SERVICE_FIELD_WAN_NAME: Final = "wan_name"
SERVICE_FIELD_WAN_UUID: Final = "wan_uuid"
SERVICE_FIELD_WINDOW: Final = "window"
SERVICE_FIELD_SSID_PROFILE_ID: Final = "ssid_profile_id"
SERVICE_FIELD_WRITE_PATTERN: Final = "write_pattern"

# Config entry data and options keys
CONF_AID: Final = "aid"
CONF_EID: Final = "eid"
CONF_GID: Final = "gid"
CONF_HOST: Final = "host"
CONF_LICENSE: Final = "license"
CONF_LOCAL_IP: Final = "local_ip"
CONF_QR_JSON: Final = "qr_json"
CONF_SELECTED_RULE_IDS: Final = "selected_rule_ids"
CONF_SELECTED_RULE_TEMPLATES: Final = "selected_rule_templates"
CONF_SYMMETRIC_KEY: Final = "symmetric_key"
CONF_DEVICE_TRACKERS: Final = "device_trackers"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_DEVICE_TRACKER_AWAY_WINDOW: Final = "device_tracker_away_window"
CONF_WATCHED_DEVICE_ONLINE_WINDOW: Final = "watched_device_online_window"
CONF_WATCHED_DEVICES: Final = "watched_devices"
CONF_WATCHED_USERS: Final = "watched_users"

APP_API_BASE: Final = "https://firewalla.encipher.io/app/api/v2"
APP_GROUP_ENDPOINT_CANDIDATES: Final = (
    "/ept/group/me",
    "/ept/groups/me",
)
FIREWALLA_PROTOCOL_CLIENT_ID: Final = "com.rottiesoft.circle"
FIREWALLA_PROTOCOL_CLIENT_KEY: Final = "fbb05afa-9145-41f1-8076-9de8be56f104"
FIREWALLA_PROTOCOL_CLIENT_VERSION: Final = "1.68.89"

DEFAULT_UPDATE_INTERVAL_MINUTES: Final = 3
DEFAULT_DEVICE_TRACKER_AWAY_WINDOW_MINUTES: Final = 15
DEFAULT_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES: Final = 5
MIN_UPDATE_INTERVAL_MINUTES: Final = 1
MIN_DEVICE_TRACKER_AWAY_WINDOW_MINUTES: Final = 5
MIN_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES: Final = 3
MAX_UPDATE_INTERVAL_MINUTES: Final = 10
DEFAULT_UPDATE_INTERVAL: Final = timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES)
DEFAULT_GROUP_POLL_ATTEMPTS: Final = 20
DEFAULT_GROUP_POLL_INTERVAL: Final = 3.0
DEFAULT_INIT_TARGET: Final = "0.0.0.0"
DEFAULT_FIREWALLA_HOST: Final = "fire.walla"
DEFAULT_PAIRING_DEVICE_NAME: Final = "Firewalla-Local-HA-v1"
DEFAULT_BOX_NAME: Final = "Firewalla"
ENTITY_SUFFIX_BINARY_SENSOR: Final = "binary_sensor"
ENTITY_SUFFIX_BUTTON: Final = "button"
ENTITY_SUFFIX_DEVICE_TRACKER: Final = "device_tracker"
ENTITY_SUFFIX_SENSOR: Final = "sensor"
ENTITY_SUFFIX_SWITCH: Final = "switch"
PLATFORM_BINARY_SENSOR: Final = "binary_sensor"
PLATFORM_BUTTON: Final = "button"
PLATFORM_DEVICE_TRACKER: Final = "device_tracker"
PLATFORM_SENSOR: Final = "sensor"
PLATFORM_SWITCH: Final = "switch"
RULE_ACTION_ALLOW: Final = "allow"
RULE_ACTION_BLOCK: Final = "block"
RULE_ACTION_DISTURB: Final = "disturb"
RULE_ACTION_QOS: Final = "qos"
RULE_ACTION_ROUTE: Final = "route"
RULE_STATE_REASON_DISABLED: Final = "disabled"
RULE_STATE_REASON_ENABLED: Final = "enabled"
RULE_STATE_REASON_OFF_SCHEDULE: Final = "off_schedule"
RULE_STATE_REASON_ON_SCHEDULE: Final = "on_schedule"
RULE_STATE_REASON_PAUSED: Final = "paused"
RULE_STATE_REASON_TIME_LIMIT_ACTIVE: Final = "time_limit_active"
RULE_STATE_REASON_TIME_LIMIT_REACHED: Final = "time_limit_reached"
RULE_PURPOSE_DAP: Final = "dap"
RULE_PURPOSE_FIREWALL: Final = "firewall"
RULE_PURPOSE_FAMILY: Final = "family"
RULE_PURPOSE_PORT_FORWARDING: Final = "port_forwarding"
RULE_TARGET_TAG: Final = "TAG"
RULE_TARGET_TYPE_CATEGORY: Final = "category"
RULE_TARGET_TYPE_DNS: Final = "dns"
RULE_TARGET_TYPE_IP: Final = "ip"
RULE_TARGET_TYPE_MAC: Final = "mac"
RULE_TARGET_TYPE_NETWORK: Final = "network"
RULE_TARGET_TYPE_REMOTE_PORT: Final = "remotePort"
CONFIG_ERROR_CANNOT_CONNECT: Final = "cannot_connect"
CONFIG_ERROR_INVALID_HOST: Final = "invalid_host"
CONFIG_ERROR_INVALID_QR: Final = "invalid_qr"
CONFIG_ERROR_WRONG_ACCOUNT: Final = "wrong_account"
SERVICE_GET_RUNTIME_INVENTORY: Final = "get_runtime_inventory"
SERVICE_GET_HOST_NAME_MAPPING: Final = "get_host_name_mapping"
SERVICE_GET_NETWORK_SEGMENT_REPORT: Final = "get_network_segment_report"
SERVICE_GET_NETWORK_SEGMENT_USAGE: Final = "get_network_segment_usage"
SERVICE_GET_SPEED_TEST_RESULTS: Final = "get_speed_test_results"
SERVICE_GET_TIME_USAGE_REPORT: Final = "get_time_usage_report"
SERVICE_GET_WAN_DATA_USAGE: Final = "get_wan_data_usage"
SERVICE_GET_WAN_EVENTS: Final = "get_wan_events"
SERVICE_SET_HOST_NAME: Final = "set_host_name"
SERVICE_SET_HOST_DNS_HOSTNAME: Final = "set_host_dns_hostname"
SERVICE_SET_HOST_DEVICE_TYPE: Final = "set_host_device_type"
SERVICE_SET_HOST_DHCP_RESERVATION: Final = "set_host_dhcp_reservation"
SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_OFFLINE: Final = "set_host_notify_when_next_offline"
SERVICE_SET_HOST_NOTIFY_WHEN_NEXT_ONLINE: Final = "set_host_notify_when_next_online"
SERVICE_WAKE_HOST: Final = "wake_host"
SERVICE_DELETE_HOST: Final = "delete_host"
SERVICE_PAUSE_RULE: Final = "pause_rule"
SERVICE_RESUME_RULE: Final = "resume_rule"
SERVICE_RUN_INTERNET_SPEED_TEST: Final = "run_internet_speed_test"
SERVICE_SET_SSID_PAUSED: Final = "set_ssid_paused"
SERVICE_GET_WIRELESS_STATUS: Final = "get_wireless_status"
WRITE_PATTERN_SET_APC: Final = "set_apc"
WRITE_PATTERN_CMD_APC: Final = "cmd_apc"
WRITE_PATTERN_SET_NETWORKCONFIG: Final = "set_networkconfig"
WRITE_PATTERN_OPTIONS: Final = (
    WRITE_PATTERN_SET_APC,
    WRITE_PATTERN_CMD_APC,
    WRITE_PATTERN_SET_NETWORKCONFIG,
)
HOST_DEVICE_TYPE_OPTIONS: Final = (
    "desktop",
    "phone",
    "tablet",
    "wearable",
    "personal_default",
    "console",
    "smart speaker",
    "tv",
    "projector",
    "entertainment_default",
    "switch",
    "automation",
    "iot_default",
    "peripheral",
    "router",
    "camera",
    "network_default",
    "nas",
    "printer",
    "security",
    "sensor",
    "car browser",
    "business",
    "medical",
    "ap",
)
TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NAME_AMBIGUOUS: Final = "config_entry_name_ambiguous"
TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NAME_NOT_FOUND: Final = "config_entry_name_not_found"
TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NOT_FOUND: Final = "config_entry_not_found"
TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NOT_LOADED: Final = "config_entry_not_loaded"
TRANS_KEY_EXCEPTION_INVALID_DURATION: Final = "invalid_duration"
TRANS_KEY_EXCEPTION_MULTIPLE_ENTRIES_LOADED: Final = "multiple_entries_loaded"
TRANS_KEY_EXCEPTION_HOST_NAME_AMBIGUOUS: Final = "host_name_ambiguous"
TRANS_KEY_EXCEPTION_HOST_NOT_FOUND: Final = "host_not_found"
TRANS_KEY_EXCEPTION_HOST_RESERVATION_IPV4_CONFLICT: Final = (
    "host_reservation_ipv4_conflict"
)
TRANS_KEY_EXCEPTION_HOST_RESERVATION_IPV4_IN_USE: Final = "host_reservation_ipv4_in_use"
TRANS_KEY_EXCEPTION_HOST_RESERVATION_IPV4_INVALID: Final = (
    "host_reservation_ipv4_invalid"
)
TRANS_KEY_EXCEPTION_HOST_RESERVATION_IPV4_NETWORK_AMBIGUOUS: Final = (
    "host_reservation_ipv4_network_ambiguous"
)
TRANS_KEY_EXCEPTION_HOST_RESERVATION_IPV4_NETWORK_NOT_FOUND: Final = (
    "host_reservation_ipv4_network_not_found"
)
TRANS_KEY_EXCEPTION_HOST_RESERVATION_IPV4_OUT_OF_RANGE: Final = (
    "host_reservation_ipv4_out_of_range"
)
TRANS_KEY_EXCEPTION_HOST_RESERVATION_IPV4_REQUIRED: Final = (
    "host_reservation_ipv4_required"
)
TRANS_KEY_EXCEPTION_HOST_REQUIRED: Final = "host_required"
TRANS_KEY_EXCEPTION_HOST_SELECTOR_CONFLICT: Final = "host_selector_conflict"
TRANS_KEY_EXCEPTION_HOST_WAKE_NOT_SUPPORTED: Final = "host_wake_not_supported"
TRANS_KEY_EXCEPTION_NETWORK_SEGMENT_REPORT_FAILED: Final = (
    "network_segment_report_failed"
)
TRANS_KEY_EXCEPTION_NETWORK_SEGMENT_USAGE_FAILED: Final = "network_segment_usage_failed"
TRANS_KEY_EXCEPTION_NETWORK_NAME_AMBIGUOUS: Final = "network_name_ambiguous"
TRANS_KEY_EXCEPTION_NETWORK_NOT_FOUND: Final = "network_not_found"
TRANS_KEY_EXCEPTION_NETWORK_REQUIRED: Final = "network_required"
TRANS_KEY_EXCEPTION_NETWORK_USAGE_WINDOW_REQUIRED: Final = (
    "network_usage_window_required"
)
TRANS_KEY_EXCEPTION_NETWORK_SELECTOR_CONFLICT: Final = "network_selector_conflict"
TRANS_KEY_ENTITY_BUTTON_SYNC_RUNTIME: Final = "sync_runtime"
TRANS_KEY_EXCEPTION_PAUSE_RULE_TIMING_CONFLICT: Final = "pause_rule_timing_conflict"
TRANS_KEY_EXCEPTION_RESUME_AT_IN_PAST: Final = "resume_at_in_past"
TRANS_KEY_EXCEPTION_RULE_TARGET_NOT_FOUND: Final = "rule_target_not_found"
TRANS_KEY_EXCEPTION_SSID_PROFILE_NOT_FOUND: Final = "ssid_profile_not_found"
TRANS_KEY_EXCEPTION_RUN_INTERNET_SPEED_TEST_FAILED: Final = (
    "run_internet_speed_test_failed"
)
TRANS_KEY_EXCEPTION_SET_HOST_DHCP_RESERVATION_FAILED: Final = (
    "set_host_dhcp_reservation_failed"
)
TRANS_KEY_EXCEPTION_SET_HOST_DNS_HOSTNAME_FAILED: Final = "set_host_dns_hostname_failed"
TRANS_KEY_EXCEPTION_SET_HOST_DEVICE_TYPE_FAILED: Final = "set_host_device_type_failed"
TRANS_KEY_EXCEPTION_SET_HOST_NAME_FAILED: Final = "set_host_name_failed"
TRANS_KEY_EXCEPTION_SET_HOST_NOTIFY_FAILED: Final = "set_host_notify_failed"
TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_NAME_AMBIGUOUS: Final = (
    "speed_test_wan_name_ambiguous"
)
TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_NOT_FOUND: Final = "speed_test_wan_not_found"
TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_REQUIRED: Final = "speed_test_wan_required"
TRANS_KEY_EXCEPTION_SPEED_TEST_WAN_SELECTOR_CONFLICT: Final = (
    "speed_test_wan_selector_conflict"
)
TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_END_BEFORE_BEGIN: Final = (
    "time_usage_report_end_before_begin"
)
TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_AMBIGUOUS: Final = (
    "time_usage_report_scope_ambiguous"
)
TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_SCOPE_NOT_FOUND: Final = (
    "time_usage_report_scope_not_found"
)
TRANS_KEY_EXCEPTION_TIME_USAGE_REPORT_FAILED: Final = "time_usage_report_failed"
TRANS_KEY_EXCEPTION_WAKE_HOST_FAILED: Final = "wake_host_failed"
TRANS_KEY_EXCEPTION_DELETE_HOST_FAILED: Final = "delete_host_failed"
TRANS_KEY_EXCEPTION_DELETE_HOST_CONFIRM_REQUIRED: Final = "delete_host_confirm_required"
TRANS_KEY_EXCEPTION_WAN_DATA_USAGE_FAILED: Final = "wan_data_usage_failed"
TRANS_KEY_EXCEPTION_WAN_DATA_USAGE_HISTORY_PERIOD_REQUIRED: Final = (
    "wan_data_usage_history_period_required"
)
TRANS_KEY_EXCEPTION_WAN_EVENTS_FAILED: Final = "wan_events_failed"
TRANS_KEY_EXCEPTION_WRONG_INTEGRATION_ENTRY: Final = "wrong_integration_entry"
TRANS_KEY_ENTITY_BINARY_SENSOR_SYSTEM_STATUS: Final = "system_status"
TRANS_KEY_ENTITY_BINARY_SENSOR_WATCHED_DEVICE: Final = "watched_device"
TRANS_KEY_ENTITY_DEVICE_TRACKER_PRESENCE: Final = "presence"
TRANS_KEY_ENTITY_SENSOR_WAN_SPEED_TEST_DOWNLOAD: Final = "wan_speed_test_download"
TRANS_KEY_ENTITY_SENSOR_WAN_SPEED_TEST_LATENCY: Final = "wan_speed_test_latency"
TRANS_KEY_ENTITY_SENSOR_WAN_SPEED_TEST_UPLOAD: Final = "wan_speed_test_upload"
TRANS_KEY_ENTITY_SENSOR_WATCHED_USER_TODAY_USAGE: Final = "watched_user_today_usage"
TRANS_KEY_ENTITY_SWITCH_ALLOW_RULE: Final = "allow_rule"
TRANS_KEY_ENTITY_SWITCH_BLOCK_RULE: Final = "block_rule"
TRANS_KEY_PURPOSE_DEVICE_TRACKER_PRESENCE: Final = "purpose_device_tracker_presence"
TRANS_KEY_PURPOSE_SYSTEM_BOOT_STATUS: Final = "purpose_system_boot_status"
TRANS_KEY_PURPOSE_WATCHED_DEVICE_CONNECTIVITY: Final = (
    "purpose_watched_device_connectivity"
)
TRANS_KEY_PURPOSE_WATCHED_USER_USAGE: Final = "purpose_watched_user_usage"
TRANS_KEY_PURPOSE_SPEED_TEST: Final = "purpose_speed_test"
TRANS_KEY_PURPOSE_RUNTIME_SYNC_BUTTON: Final = "purpose_runtime_sync_button"
TRANS_KEY_PURPOSE_RULE_SWITCH: Final = "purpose_rule_control"
TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE: Final = "unavailable_device"
TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE_TRACKER: Final = "unavailable_device_tracker"
TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE: Final = "unavailable_rule"
TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE_SUFFIX: Final = "unavailable_rule_suffix"
TRANS_KEY_OPTION_LABEL_UNAVAILABLE_USER: Final = "unavailable_user"
TRANS_PLACEHOLDER_DURATION: Final = "duration"
TRANS_PLACEHOLDER_HOST_MATCHES: Final = "host_matches"
TRANS_PLACEHOLDER_HOST_NAME: Final = "host_name"
TRANS_PLACEHOLDER_NETWORK_NAME: Final = "network_name"
TRANS_PLACEHOLDER_NETWORK_UUID: Final = "network_uuid"
TRANS_PLACEHOLDER_RESERVED_IPV4: Final = "reserved_ipv4"
TRANS_PLACEHOLDER_RULE_NAME: Final = "rule_name"
TRANS_PLACEHOLDER_RULE_TARGET: Final = "rule_target"
TRANS_PLACEHOLDER_SSID_PROFILE_ID: Final = "ssid_profile_id"
TRANS_PLACEHOLDER_SCOPE_KIND: Final = "scope_kind"
TRANS_PLACEHOLDER_SCOPE_TARGET: Final = "scope_target"
TRANS_PLACEHOLDER_WAN_NAME: Final = "wan_name"
TRANS_PLACEHOLDER_WAN_UUID: Final = "wan_uuid"
