"""Constants for the Firewalla Local integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Final

DOMAIN: Final = "firewalla_local"
LOGGER: Final = logging.getLogger(__name__)
MANUFACTURER: Final = "Firewalla"

# Entity state attributes
ATTR_RULE_PURPOSE: Final = "purpose"
ATTR_RULE_ID: Final = "rule_id"
ATTR_RULE_TEMPLATE_TARGET: Final = "target"
ATTR_RULE_TARGET_TYPE: Final = "target_type"
ATTR_RULE_TAG_REFS: Final = "tag_refs"
ATTR_RULE_NOTES: Final = "notes"
ATTR_RULE_IS_PAUSED: Final = "is_paused"
ATTR_RULE_PAUSE_UNTIL: Final = "pause_until"

# Service input fields
SERVICE_FIELD_CONFIG_ENTRY_ID: Final = "config_entry_id"
SERVICE_FIELD_CONFIG_ENTRY_NAME: Final = "config_entry_name"
SERVICE_FIELD_RULE_DURATION: Final = "duration"
SERVICE_FIELD_RULE_RESUME_AT: Final = "resume_at"
SERVICE_FIELD_RULE_TARGET: Final = "rule_target"

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

APP_API_BASE: Final = "https://firewalla.encipher.io/app/api/v2"
APP_GROUP_ENDPOINT_CANDIDATES: Final = (
    "/ept/group/me",
    "/ept/groups/me",
)
FIREWALLA_APP_ID: Final = "com.rottiesoft.circle"
FIREWALLA_APP_SECRET: Final = "fbb05afa-9145-41f1-8076-9de8be56f104"
FIREWALLA_APP_VERSION: Final = "1.51.84"

DEFAULT_UPDATE_INTERVAL: Final = timedelta(minutes=1)
DEFAULT_GROUP_POLL_ATTEMPTS: Final = 10
DEFAULT_GROUP_POLL_INTERVAL: Final = 3.0
DEFAULT_INIT_TARGET: Final = "0.0.0.0"
DEFAULT_FIREWALLA_HOST: Final = "fire.walla"
DEFAULT_PAIRING_DEVICE_NAME: Final = "Home Assistant"
DEFAULT_BOX_NAME: Final = "Firewalla"
ENTITY_SUFFIX_SWITCH: Final = "switch"
PLATFORM_SWITCH: Final = "switch"
RULE_ACTION_ALLOW: Final = "allow"
RULE_ACTION_BLOCK: Final = "block"
RULE_PURPOSE_FAMILY: Final = "family"
RULE_TARGET_TAG: Final = "TAG"
RULE_TARGET_TYPE_CATEGORY: Final = "category"
RULE_TARGET_TYPE_DNS: Final = "dns"
RULE_TARGET_TYPE_MAC: Final = "mac"
RULE_TARGET_TYPE_NETWORK: Final = "network"
CONFIG_ERROR_CANNOT_CONNECT: Final = "cannot_connect"
CONFIG_ERROR_INVALID_HOST: Final = "invalid_host"
CONFIG_ERROR_INVALID_QR: Final = "invalid_qr"
CONFIG_ERROR_WRONG_ACCOUNT: Final = "wrong_account"
SERVICE_GET_RUNTIME_INVENTORY: Final = "get_runtime_inventory"
SERVICE_PAUSE_RULE: Final = "pause_rule"
SERVICE_RESUME_RULE: Final = "resume_rule"
TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NAME_AMBIGUOUS: Final = "config_entry_name_ambiguous"
TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NAME_NOT_FOUND: Final = "config_entry_name_not_found"
TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NOT_FOUND: Final = "config_entry_not_found"
TRANS_KEY_EXCEPTION_CONFIG_ENTRY_NOT_LOADED: Final = "config_entry_not_loaded"
TRANS_KEY_EXCEPTION_INVALID_DURATION: Final = "invalid_duration"
TRANS_KEY_EXCEPTION_MULTIPLE_ENTRIES_LOADED: Final = "multiple_entries_loaded"
TRANS_KEY_EXCEPTION_PAUSE_RULE_TIMING_CONFLICT: Final = "pause_rule_timing_conflict"
TRANS_KEY_EXCEPTION_RESUME_AT_IN_PAST: Final = "resume_at_in_past"
TRANS_KEY_EXCEPTION_RULE_TARGET_NOT_FOUND: Final = "rule_target_not_found"
TRANS_KEY_EXCEPTION_WRONG_INTEGRATION_ENTRY: Final = "wrong_integration_entry"
TRANS_KEY_ENTITY_SWITCH_ALLOW_RULE: Final = "allow_rule"
TRANS_KEY_ENTITY_SWITCH_BLOCK_RULE: Final = "block_rule"
TRANS_KEY_PURPOSE_RULE_SWITCH: Final = "purpose_rule_control"
TRANS_PLACEHOLDER_DURATION: Final = "duration"
TRANS_PLACEHOLDER_RULE_NAME: Final = "rule_name"
TRANS_PLACEHOLDER_RULE_TARGET: Final = "rule_target"
