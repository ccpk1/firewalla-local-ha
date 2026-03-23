"""Constants for the Firewalla Local integration."""

from __future__ import annotations

import logging
from datetime import timedelta

DOMAIN = "firewalla_local"
LOGGER = logging.getLogger(__name__)
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=1)
