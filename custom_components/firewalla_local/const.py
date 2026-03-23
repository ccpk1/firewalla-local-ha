"""Constants for the Firewalla Local integration."""

from __future__ import annotations

import logging
from datetime import timedelta

DOMAIN = "firewalla_local"
LOGGER = logging.getLogger(__name__)
CONF_CONFIG_ENTRY_ID = "config_entry_id"
CONF_CONFIG_ENTRY_NAME = "config_entry_name"
CONF_AID = "aid"
CONF_EID = "eid"
CONF_GID = "gid"
CONF_HOST = "host"
CONF_LICENSE = "license"
CONF_QR_JSON = "qr_json"
CONF_SELECTED_RULE_IDS = "selected_rule_ids"
CONF_SYMMETRIC_KEY = "symmetric_key"
LEGACY_CONF_LOCAL_IP = "local_ip"

APP_API_BASE = "https://firewalla.encipher.io/app/api/v2"
APP_GROUP_ENDPOINT_CANDIDATES = (
	"/ept/group/me",
	"/ept/groups/me",
)
FIREWALLA_APP_ID = "com.rottiesoft.circle"
FIREWALLA_APP_SECRET = "fbb05afa-9145-41f1-8076-9de8be56f104"
FIREWALLA_APP_VERSION = "1.51.84"

DEFAULT_UPDATE_INTERVAL = timedelta(minutes=1)
DEFAULT_GROUP_POLL_ATTEMPTS = 10
DEFAULT_GROUP_POLL_INTERVAL = 3.0
DEFAULT_INIT_TARGET = "0.0.0.0"
DEFAULT_FIREWALLA_HOST = "fire.walla"
DEFAULT_PAIRING_DEVICE_NAME = "Home Assistant"
SERVICE_GET_RUNTIME_INVENTORY = "get_runtime_inventory"
