"""Constants for the Firewalla integration."""

from __future__ import annotations

import logging
from datetime import timedelta

DOMAIN = "firewalla"
LOGGER = logging.getLogger(__name__)
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=1)
