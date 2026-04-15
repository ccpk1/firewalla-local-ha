"""Config flow for Firewalla Local."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import Mapping
from typing import Final, Self, TypedDict, cast

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import translation as translation_helper
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    FirewallaApiClient,
    FirewallaApiError,
    FirewallaConnectionError,
    FirewallaLocalPairingTimeoutError,
    FirewallaLocalRuntimeNotReadyError,
    FirewallaPairingTimeoutError,
    FirewallaValidationError,
    async_provision_firewalla_credentials,
    generate_firewalla_keys,
    load_qr_json,
)
from .const import (
    CONF_AID,
    CONF_DEVICE_TRACKER_AWAY_WINDOW,
    CONF_DEVICE_TRACKERS,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_QR_JSON,
    CONF_SELECTED_RULE_IDS,
    CONF_SELECTED_RULE_TEMPLATES,
    CONF_SYMMETRIC_KEY,
    CONF_UPDATE_INTERVAL,
    CONF_WATCHED_DEVICE_ONLINE_WINDOW,
    CONF_WATCHED_DEVICES,
    CONF_WATCHED_USERS,
    CONFIG_ERROR_CANNOT_CONNECT,
    CONFIG_ERROR_INVALID_HOST,
    CONFIG_ERROR_INVALID_QR,
    CONFIG_ERROR_WRONG_ACCOUNT,
    DEFAULT_BOX_NAME,
    DEFAULT_DEVICE_TRACKER_AWAY_WINDOW_MINUTES,
    DEFAULT_FIREWALLA_HOST,
    DEFAULT_PAIRING_DEVICE_NAME,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DEFAULT_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES,
    DOMAIN,
    LOGGER,
    MAX_UPDATE_INTERVAL_MINUTES,
    MIN_DEVICE_TRACKER_AWAY_WINDOW_MINUTES,
    MIN_UPDATE_INTERVAL_MINUTES,
    MIN_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES,
    TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE,
    TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE_TRACKER,
    TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE,
    TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE_SUFFIX,
    TRANS_KEY_OPTION_LABEL_UNAVAILABLE_USER,
)
from .coordinator import (
    async_update_entry_options,
    cache_pending_pairing_init_payload,
)
from .managers import (
    FirewallaHostManager,
    FirewallaRuleManager,
    FirewallaUserManager,
)
from .models import (
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
    format_policy_rule_label,
)

_STEP_ID_INIT: Final = "init"
_STEP_ID_EDIT_DEVICE_TRACKERS: Final = "edit_device_trackers"
_STEP_ID_EDIT_RULE_SELECTION: Final = "edit_rule_selection"
_STEP_ID_EDIT_WATCHED_DEVICES: Final = "edit_watched_devices"
_STEP_ID_EDIT_WATCHED_USERS: Final = "edit_watched_users"
_STEP_ID_GENERAL_OPTIONS: Final = "general_options"
_STEP_ID_REAUTH_CONFIRM: Final = "reauth_confirm"
_STEP_ID_RECONFIGURE: Final = "reconfigure"
_STEP_ID_RULE_SELECTION: Final = "rule_selection"
_STEP_ID_SYSTEM_SETTINGS: Final = "system_settings"
_STEP_ID_USER: Final = "user"
_OPTION_RETURN_TO_MAIN_MENU: Final = "return_to_main_menu"
_CONFIG_ERROR_CLOUD_LINK_TIMEOUT: Final = "cloud_link_timeout"
_CONFIG_ERROR_LOCAL_PAIRING_TIMEOUT: Final = "local_pairing_timeout"
_LOCAL_RUNTIME_VALIDATION_FAST_ATTEMPTS: Final = 5
_LOCAL_RUNTIME_VALIDATION_FAST_INTERVAL: Final = 2.0
_LOCAL_RUNTIME_VALIDATION_SLOW_INTERVAL: Final = 5.0
_LOCAL_RUNTIME_VALIDATION_TIMEOUT: Final = 90.0


class PairingUserInput(TypedDict):
    """Validated user input for pairing and reauth flows."""

    host: str
    qr_json: str


class RuleSelectionOptionsInput(TypedDict, total=False):
    """Validated user input for the options flow."""

    selected_rule_ids: list[str]
    return_to_main_menu: bool


class SystemSettingsOptionsInput(TypedDict):
    """Validated system-settings input for the options flow."""

    device_tracker_away_window: int
    update_interval: int
    return_to_main_menu: bool
    watched_device_online_window: int


class DeviceTrackersOptionsInput(TypedDict, total=False):
    """Validated device-tracker input for the options flow."""

    device_trackers: list[str]
    return_to_main_menu: bool


class WatchedDevicesOptionsInput(TypedDict, total=False):
    """Validated watched-device input for the options flow."""

    watched_devices: list[str]
    return_to_main_menu: bool


class WatchedUsersOptionsInput(TypedDict, total=False):
    """Validated watched-user input for the options flow."""

    watched_users: list[str]
    return_to_main_menu: bool


def _normalize_host(host: str) -> str:
    """Normalize a host or IP override used for the local runtime target."""
    normalized_host = host.strip().lower()
    if not normalized_host:
        raise ValueError("Host cannot be empty")
    return normalized_host


def _format_rule_option(rule: FirewallaPolicyRule) -> str:
    """Build a compact label for one selectable Firewalla rule."""
    return f"[{rule.rule_id}] {format_policy_rule_label(rule)}"


def _resolve_default_pairing_host() -> str | None:
    """Resolve the default Firewalla hostname to one IPv4 address when possible."""
    try:
        addrinfo = socket.getaddrinfo(
            DEFAULT_FIREWALLA_HOST,
            None,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return None

    for family, _socktype, _proto, _canonname, sockaddr in addrinfo:
        if family is not socket.AF_INET:
            continue
        candidate = cast(str, sockaddr[0])
        try:
            ipaddress.IPv4Address(candidate)
        except ipaddress.AddressValueError:
            continue
        return candidate

    return None


def _pairing_monotonic() -> float:
    """Return a monotonic clock for pairing instrumentation."""
    return time.monotonic()


def _get_local_runtime_validation_interval(attempt: int) -> float:
    """Return the next wait interval for local pairing activation retries."""
    if attempt <= _LOCAL_RUNTIME_VALIDATION_FAST_ATTEMPTS:
        return _LOCAL_RUNTIME_VALIDATION_FAST_INTERVAL
    return _LOCAL_RUNTIME_VALIDATION_SLOW_INTERVAL


class FirewallaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Firewalla Local."""

    VERSION = 1
    MINOR_VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> FirewallaOptionsFlow:
        """Return the options flow handler."""
        return FirewallaOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.license: str | None = None
        self.host: str | None = None
        self._suggested_host: str | None = None

    @staticmethod
    def _build_pairing_schema(*, host: str | None = None) -> vol.Schema:
        """Build the pairing form schema for user and reauth flows."""
        schema: dict[vol.Marker, object] = {
            vol.Required(CONF_QR_JSON): str,
        }
        if host is None:
            schema = {
                vol.Required(CONF_HOST, default=DEFAULT_FIREWALLA_HOST): str,
                vol.Required(CONF_QR_JSON): str,
            }
        else:
            schema = {
                vol.Required(CONF_HOST, default=host): str,
                vol.Required(CONF_QR_JSON): str,
            }
        return vol.Schema(schema)

    async def _async_pair_firewalla(
        self, user_input: PairingUserInput
    ) -> tuple[dict[str, str], str] | None:
        """Validate pairing input and return durable credential data plus title."""
        host = _normalize_host(user_input[CONF_HOST])
        qr_data = load_qr_json(user_input[CONF_QR_JSON])
        pairing_started_at = _pairing_monotonic()

        LOGGER.info("Starting Firewalla pairing for host %s", host)

        self.license = qr_data.license
        self.host = host

        LOGGER.info("Generating Firewalla pairing keypair for host %s", host)
        keys = await self.hass.async_add_executor_job(generate_firewalla_keys)
        LOGGER.info("Requesting Firewalla cloud provisioning for host %s", host)
        credentials = await async_provision_firewalla_credentials(
            async_get_clientsession(self.hass),
            qr_data=qr_data,
            host=host,
            keys=keys,
        )
        cloud_provisioning_elapsed = _pairing_monotonic() - pairing_started_at
        LOGGER.info(
            "Cloud provisioning completed for host %s after %.1fs; validating "
            "local runtime",
            credentials.host,
            cloud_provisioning_elapsed,
        )
        client = FirewallaApiClient(
            session=async_get_clientsession(self.hass),
            host=credentials.host,
            gid=credentials.gid,
            eid=credentials.eid,
            aid=credentials.aid,
            symmetric_key=credentials.symmetric_key,
            device_name=DEFAULT_PAIRING_DEVICE_NAME,
            timezone_name=self.hass.config.time_zone,
        )
        LOGGER.info(
            "Starting Firewalla local runtime validation for host %s "
            "(aid present: %s, device name: %s, timezone: %s)",
            credentials.host,
            bool(credentials.aid),
            DEFAULT_PAIRING_DEVICE_NAME,
            self.hass.config.time_zone,
        )
        local_validation_started_at = _pairing_monotonic()
        attempt = 0
        while True:
            attempt += 1
            try:
                pairing_payload = await client.async_get_pairing_runtime_init_payload(
                    log_as_info=True
                )
            except FirewallaLocalRuntimeNotReadyError as err:
                elapsed = _pairing_monotonic() - local_validation_started_at
                if elapsed >= _LOCAL_RUNTIME_VALIDATION_TIMEOUT:
                    raise FirewallaLocalPairingTimeoutError(
                        "Local runtime did not accept the new pairing before "
                        f"timing out after {attempt} attempts and {elapsed:.1f}s"
                    ) from err

                wait_interval = min(
                    _get_local_runtime_validation_interval(attempt),
                    _LOCAL_RUNTIME_VALIDATION_TIMEOUT - elapsed,
                )
                LOGGER.info(
                    "Firewalla local runtime is not ready for paired credentials "
                    "on host %s yet (attempt %s, elapsed %.1fs/%ss); waiting %.1fs "
                    "before retry",
                    host,
                    attempt,
                    elapsed,
                    _LOCAL_RUNTIME_VALIDATION_TIMEOUT,
                    wait_interval,
                )
                await asyncio.sleep(wait_interval)
                continue
            except FirewallaConnectionError as err:
                elapsed = _pairing_monotonic() - local_validation_started_at
                if elapsed >= _LOCAL_RUNTIME_VALIDATION_TIMEOUT:
                    raise FirewallaLocalPairingTimeoutError(
                        "Local runtime did not accept the new pairing before "
                        f"timing out after {attempt} attempts and {elapsed:.1f}s"
                    ) from err

                wait_interval = min(
                    _LOCAL_RUNTIME_VALIDATION_SLOW_INTERVAL,
                    _LOCAL_RUNTIME_VALIDATION_TIMEOUT - elapsed,
                )
                LOGGER.info(
                    "Firewalla local runtime disconnected during paired credential "
                    "activation on host %s (attempt %s, elapsed %.1fs/%ss); "
                    "waiting %.1fs before retry",
                    host,
                    attempt,
                    elapsed,
                    _LOCAL_RUNTIME_VALIDATION_TIMEOUT,
                    wait_interval,
                )
                await asyncio.sleep(wait_interval)
                continue

            cache_pending_pairing_init_payload(
                self.hass, credentials.license, pairing_payload
            )
            validation_elapsed = _pairing_monotonic() - local_validation_started_at
            total_elapsed = _pairing_monotonic() - pairing_started_at
            LOGGER.info(
                "Firewalla local runtime validation succeeded for host %s after "
                "%s attempt(s) and %.1fs of local wait (total pairing %.1fs)",
                host,
                attempt,
                validation_elapsed,
                total_elapsed,
            )
            break

        title_name = credentials.box_name or DEFAULT_BOX_NAME
        return (
            {
                CONF_LICENSE: credentials.license,
                CONF_HOST: credentials.host,
                CONF_GID: credentials.gid,
                CONF_EID: credentials.eid,
                CONF_AID: credentials.aid,
                CONF_SYMMETRIC_KEY: credentials.symmetric_key,
            },
            f"{title_name} ({credentials.host})",
        )

    def is_matching(self, other_flow: Self) -> bool:
        """Return True if another flow targets the same Firewalla license."""
        return other_flow.license == self.license

    async def async_step_user(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                typed_user_input = PairingUserInput(
                    host=cast(str, user_input[CONF_HOST]),
                    qr_json=cast(str, user_input[CONF_QR_JSON]),
                )
                host = _normalize_host(typed_user_input[CONF_HOST])
                qr_data = load_qr_json(typed_user_input[CONF_QR_JSON])
            except ValueError:
                LOGGER.warning("Rejected Firewalla pairing request with empty host")
                errors["base"] = CONFIG_ERROR_INVALID_HOST
            except FirewallaValidationError:
                LOGGER.warning(
                    "Rejected Firewalla pairing request with invalid QR JSON"
                )
                errors["base"] = CONFIG_ERROR_INVALID_QR
            else:
                self.license = qr_data.license
                self.host = host
                await self.async_set_unique_id(qr_data.license)
                self._abort_if_unique_id_configured()

                try:
                    pairing_result = await self._async_pair_firewalla(typed_user_input)
                except FirewallaPairingTimeoutError as err:
                    LOGGER.warning(
                        "Firewalla pairing timed out waiting for cloud group "
                        "visibility "
                        "for host %s: %s",
                        host,
                        err,
                    )
                    errors["base"] = _CONFIG_ERROR_CLOUD_LINK_TIMEOUT
                except FirewallaLocalPairingTimeoutError as err:
                    LOGGER.warning(
                        "Firewalla pairing timed out waiting for local runtime "
                        "activation for host %s: %s",
                        host,
                        err,
                    )
                    errors["base"] = _CONFIG_ERROR_LOCAL_PAIRING_TIMEOUT
                except FirewallaApiError as err:
                    LOGGER.warning(
                        "Firewalla pairing failed for host %s: %s",
                        host,
                        err,
                    )
                    errors["base"] = CONFIG_ERROR_CANNOT_CONNECT
                else:
                    assert pairing_result is not None
                    entry_data, title = pairing_result
                    return self.async_create_entry(title=title, data=entry_data)

        if self._suggested_host is None:
            self._suggested_host = await self.hass.async_add_executor_job(
                _resolve_default_pairing_host
            )

        return self.async_show_form(
            step_id=_STEP_ID_USER,
            data_schema=self._build_pairing_schema(host=self._suggested_host or ""),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, object]
    ) -> ConfigFlowResult:
        """Start reauthentication for an existing entry."""
        self.license = cast(str, entry_data[CONF_LICENSE])
        self.host = cast(str, entry_data[CONF_HOST])
        await self.async_set_unique_id(self.license)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Refresh credentials for an existing Firewalla entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                typed_user_input = PairingUserInput(
                    host=cast(str, user_input[CONF_HOST]),
                    qr_json=cast(str, user_input[CONF_QR_JSON]),
                )
                pairing_result = await self._async_pair_firewalla(typed_user_input)
            except ValueError:
                LOGGER.warning("Rejected Firewalla reauth request with empty host")
                errors["base"] = CONFIG_ERROR_INVALID_HOST
            except FirewallaValidationError:
                LOGGER.warning("Rejected Firewalla reauth request with invalid QR JSON")
                errors["base"] = CONFIG_ERROR_INVALID_QR
            except FirewallaPairingTimeoutError as err:
                LOGGER.warning(
                    "Firewalla reauth timed out waiting for cloud group visibility "
                    "for host %s: %s",
                    cast(str, user_input[CONF_HOST]),
                    err,
                )
                errors["base"] = _CONFIG_ERROR_CLOUD_LINK_TIMEOUT
            except FirewallaLocalPairingTimeoutError as err:
                LOGGER.warning(
                    "Firewalla reauth timed out waiting for local runtime "
                    "activation for host %s: %s",
                    cast(str, user_input[CONF_HOST]),
                    err,
                )
                errors["base"] = _CONFIG_ERROR_LOCAL_PAIRING_TIMEOUT
            except FirewallaApiError as err:
                LOGGER.warning(
                    "Firewalla reauth failed for host %s: %s",
                    cast(str, user_input[CONF_HOST]),
                    err,
                )
                errors["base"] = CONFIG_ERROR_CANNOT_CONNECT
            else:
                assert pairing_result is not None
                entry_data, _title = pairing_result
                await self.async_set_unique_id(entry_data[CONF_LICENSE])
                self._abort_if_unique_id_mismatch(reason=CONFIG_ERROR_WRONG_ACCOUNT)
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates=entry_data,
                )

        return self.async_show_form(
            step_id=_STEP_ID_REAUTH_CONFIRM,
            data_schema=self._build_pairing_schema(host=self.host),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                host = _normalize_host(cast(str, user_input[CONF_HOST]))
            except ValueError:
                errors["base"] = CONFIG_ERROR_INVALID_HOST
            else:
                self.host = host
                entry = self._get_reconfigure_entry()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_HOST: host},
                )

        entry = self._get_reconfigure_entry()
        return self.async_show_form(
            step_id=_STEP_ID_RECONFIGURE,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=entry.data[CONF_HOST],
                    ): str
                }
            ),
            errors=errors,
        )


class FirewallaOptionsFlow(OptionsFlow):
    """Handle mutable Firewalla Local options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry
        self._option_label_cache: dict[str, str] | None = None

    async def _async_get_option_labels(self) -> dict[str, str]:
        """Return translation-backed labels used in dynamic option rows."""
        if self._option_label_cache is not None:
            return self._option_label_cache

        hass = self.hass
        assert hass is not None

        translations = await translation_helper.async_get_translations(
            hass,
            hass.config.language,
            "exceptions",
            integrations=[DOMAIN],
        )
        self._option_label_cache = {
            TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE: translations.get(
                f"component.{DOMAIN}.exceptions."
                f"{TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE}.message",
                TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE,
            ),
            TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE_SUFFIX: translations.get(
                f"component.{DOMAIN}.exceptions."
                f"{TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE_SUFFIX}.message",
                TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE_SUFFIX,
            ),
            TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE: translations.get(
                f"component.{DOMAIN}.exceptions."
                f"{TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE}.message",
                TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE,
            ),
            TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE_TRACKER: translations.get(
                f"component.{DOMAIN}.exceptions."
                f"{TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE_TRACKER}.message",
                TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE_TRACKER,
            ),
            TRANS_KEY_OPTION_LABEL_UNAVAILABLE_USER: translations.get(
                f"component.{DOMAIN}.exceptions."
                f"{TRANS_KEY_OPTION_LABEL_UNAVAILABLE_USER}.message",
                TRANS_KEY_OPTION_LABEL_UNAVAILABLE_USER,
            ),
        }
        return self._option_label_cache

    def _get_rule_manager(self) -> FirewallaRuleManager | None:
        """Return the loaded rule manager when runtime data is available."""
        runtime_data = getattr(self._config_entry, "runtime_data", None)
        if runtime_data is None:
            return None
        rule_manager = getattr(runtime_data, "rule_manager", None)
        if isinstance(rule_manager, FirewallaRuleManager):
            return rule_manager
        return None

    def _get_host_manager(self) -> FirewallaHostManager | None:
        """Return the loaded host manager when runtime data is available."""
        runtime_data = getattr(self._config_entry, "runtime_data", None)
        if runtime_data is None:
            return None
        host_manager = getattr(runtime_data, "host_manager", None)
        if isinstance(host_manager, FirewallaHostManager):
            return host_manager
        return None

    def _get_user_manager(self) -> FirewallaUserManager | None:
        """Return the loaded user manager when runtime data is available."""
        runtime_data = getattr(self._config_entry, "runtime_data", None)
        if runtime_data is None:
            return None
        user_manager = getattr(runtime_data, "user_manager", None)
        if isinstance(user_manager, FirewallaUserManager):
            return user_manager
        return None

    def _get_rule_choices(self) -> dict[str, str]:
        """Return selectable rule IDs from the live coordinator snapshot."""
        if rule_manager := self._get_rule_manager():
            return rule_manager.get_switch_candidate_choices()

        runtime_data = getattr(self._config_entry, "runtime_data", None)
        if runtime_data is None:
            return {}

        snapshot = runtime_data.coordinator.data
        if snapshot is None:
            return {}

        return FirewallaRuleManager.get_switch_candidate_choices_for_snapshot(snapshot)

    def _get_stored_rule_templates(self) -> dict[str, FirewallaRuleTemplate]:
        """Return persisted rule templates keyed by source rule ID."""
        templates = FirewallaRuleManager.load_selected_templates(
            self._config_entry.options,
            None,
        )
        return {template.source_rule_id: template for template in templates}

    def _get_missing_rule_choices(
        self,
        live_rule_choices: dict[str, str],
        *,
        unavailable_rule_label: str,
        unavailable_rule_suffix: str,
    ) -> dict[str, str]:
        """Return persisted selections whose backing live rules are missing."""
        stored_selected_rule_ids = self._config_entry.options.get(
            CONF_SELECTED_RULE_IDS, []
        )
        if not isinstance(stored_selected_rule_ids, list):
            return {}

        stored_templates = self._get_stored_rule_templates()
        missing_rule_choices: dict[str, str] = {}
        for rule_id in stored_selected_rule_ids:
            if not isinstance(rule_id, str) or rule_id in live_rule_choices:
                continue

            if template := stored_templates.get(rule_id):
                missing_rule_choices[rule_id] = (
                    f"[{rule_id}] {template.name} {unavailable_rule_suffix}"
                )
            else:
                missing_rule_choices[rule_id] = f"[{rule_id}] {unavailable_rule_label}"

        return missing_rule_choices

    def _get_rule_templates(self) -> dict[str, FirewallaRuleTemplate]:
        """Return supported switch templates keyed by the source rule ID."""
        if rule_manager := self._get_rule_manager():
            return rule_manager.get_switch_candidate_templates()

        runtime_data = getattr(self._config_entry, "runtime_data", None)
        if runtime_data is None:
            return {}

        snapshot = runtime_data.coordinator.data
        if snapshot is None:
            return {}

        return FirewallaRuleManager.get_switch_candidate_templates_for_snapshot(
            snapshot
        )

    def _get_stored_update_interval(self) -> int:
        """Return the persisted update interval or the default when unset."""
        raw_update_interval: object = self._config_entry.options.get(
            CONF_UPDATE_INTERVAL,
            DEFAULT_UPDATE_INTERVAL_MINUTES,
        )
        if isinstance(raw_update_interval, bool) or not isinstance(
            raw_update_interval, int
        ):
            return DEFAULT_UPDATE_INTERVAL_MINUTES

        if not (
            MIN_UPDATE_INTERVAL_MINUTES
            <= raw_update_interval
            <= MAX_UPDATE_INTERVAL_MINUTES
        ):
            return DEFAULT_UPDATE_INTERVAL_MINUTES

        return raw_update_interval

    def _get_stored_minute_option(
        self, option_key: str, default: int, minimum: int
    ) -> int:
        """Return one validated minute-based stored option."""
        raw_value: object = self._config_entry.options.get(option_key, default)
        if isinstance(raw_value, bool) or not isinstance(raw_value, int):
            return default
        if raw_value < minimum:
            return default
        return raw_value

    def _get_stored_device_tracker_away_window(self) -> int:
        """Return the persisted device-tracker away window in minutes."""
        return self._get_stored_minute_option(
            CONF_DEVICE_TRACKER_AWAY_WINDOW,
            DEFAULT_DEVICE_TRACKER_AWAY_WINDOW_MINUTES,
            MIN_DEVICE_TRACKER_AWAY_WINDOW_MINUTES,
        )

    def _get_stored_watched_device_online_window(self) -> int:
        """Return the persisted watched-device online window in minutes."""
        return self._get_stored_minute_option(
            CONF_WATCHED_DEVICE_ONLINE_WINDOW,
            DEFAULT_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES,
            MIN_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES,
        )

    def _get_stored_rule_selection(
        self,
    ) -> tuple[list[str], tuple[FirewallaRuleTemplate, ...]]:
        """Return the current persisted rule selection state."""
        stored_selected_rule_ids = self._config_entry.options.get(
            CONF_SELECTED_RULE_IDS, []
        )
        if not isinstance(stored_selected_rule_ids, list):
            return [], ()

        stored_rule_templates = self._get_stored_rule_templates()
        selected_rule_ids = [
            rule_id
            for rule_id in stored_selected_rule_ids
            if isinstance(rule_id, str) and rule_id in stored_rule_templates
        ]
        return selected_rule_ids, tuple(
            stored_rule_templates[rule_id] for rule_id in selected_rule_ids
        )

    def _get_stored_watched_devices(self) -> list[str]:
        """Return the currently persisted watched-device MACs."""
        raw_watched_devices = self._config_entry.options.get(CONF_WATCHED_DEVICES, [])
        if not isinstance(raw_watched_devices, list):
            return []
        return [mac for mac in raw_watched_devices if isinstance(mac, str) and mac]

    def _get_stored_watched_users(self) -> list[str]:
        """Return the currently persisted watched-user identifiers."""
        raw_watched_users = self._config_entry.options.get(CONF_WATCHED_USERS, [])
        if not isinstance(raw_watched_users, list):
            return []
        return [
            user_id
            for user_id in raw_watched_users
            if isinstance(user_id, str) and user_id
        ]

    def _get_stored_device_trackers(self) -> list[str]:
        """Return the currently persisted device-tracker MACs."""
        raw_device_trackers = self._config_entry.options.get(CONF_DEVICE_TRACKERS, [])
        if not isinstance(raw_device_trackers, list):
            return []
        return [mac for mac in raw_device_trackers if isinstance(mac, str) and mac]

    def _get_watched_device_choices(self) -> dict[str, str]:
        """Return selectable watched devices keyed by MAC."""
        if host_manager := self._get_host_manager():
            return host_manager.get_watched_device_choices()

        runtime_data = getattr(self._config_entry, "runtime_data", None)
        if runtime_data is None:
            return {}

        snapshot = runtime_data.coordinator.data
        if snapshot is None:
            return {}

        return FirewallaHostManager.get_watched_device_choices_for_hosts(snapshot.hosts)

    def _get_device_tracker_choices(self) -> dict[str, str]:
        """Return selectable device trackers keyed by MAC."""
        if host_manager := self._get_host_manager():
            return host_manager.get_device_tracker_choices()

        runtime_data = getattr(self._config_entry, "runtime_data", None)
        if runtime_data is None:
            return {}

        snapshot = runtime_data.coordinator.data
        if snapshot is None:
            return {}

        return FirewallaHostManager.get_device_tracker_choices_for_hosts(snapshot.hosts)

    def _get_missing_device_tracker_choices(
        self,
        live_device_tracker_choices: dict[str, str],
        *,
        unavailable_device_tracker_label: str,
    ) -> dict[str, str]:
        """Return device-tracker selections missing from the latest runtime."""
        return {
            mac: f"[{mac}] {unavailable_device_tracker_label}"
            for mac in self._get_stored_device_trackers()
            if mac not in live_device_tracker_choices
        }

    def _get_missing_watched_device_choices(
        self,
        live_watched_device_choices: dict[str, str],
        *,
        unavailable_watched_device_label: str,
    ) -> dict[str, str]:
        """Return watched-device selections missing from the latest runtime."""
        return {
            mac: f"[{mac}] {unavailable_watched_device_label}"
            for mac in self._get_stored_watched_devices()
            if mac not in live_watched_device_choices
        }

    def _get_watched_user_choices(self) -> dict[str, str]:
        """Return selectable watched users keyed by user identifier."""
        if user_manager := self._get_user_manager():
            return user_manager.get_watched_user_choices()

        runtime_data = getattr(self._config_entry, "runtime_data", None)
        if runtime_data is None:
            return {}

        snapshot = runtime_data.coordinator.data
        if snapshot is None:
            return {}

        return FirewallaUserManager.get_watched_user_choices_for_snapshot(snapshot)

    def _get_missing_watched_user_choices(
        self,
        live_watched_user_choices: dict[str, str],
        *,
        unavailable_watched_user_label: str,
    ) -> dict[str, str]:
        """Return watched-user selections missing from the latest runtime."""
        return {
            user_id: f"[{user_id}] {unavailable_watched_user_label}"
            for user_id in self._get_stored_watched_users()
            if user_id not in live_watched_user_choices
        }

    def _build_options_payload(
        self,
        *,
        device_trackers: list[str] | None = None,
        device_tracker_away_window: int | None = None,
        selected_rule_ids: list[str] | None = None,
        selected_rule_templates: tuple[FirewallaRuleTemplate, ...] | None = None,
        watched_devices: list[str] | None = None,
        watched_device_online_window: int | None = None,
        watched_users: list[str] | None = None,
        update_interval: int | None = None,
    ) -> dict[str, object]:
        """Build one complete options payload while preserving untouched settings."""
        stored_rule_ids, stored_rule_templates = self._get_stored_rule_selection()
        return {
            CONF_SELECTED_RULE_IDS: (
                stored_rule_ids if selected_rule_ids is None else selected_rule_ids
            ),
            CONF_SELECTED_RULE_TEMPLATES: [
                template.to_dict()
                for template in (
                    stored_rule_templates
                    if selected_rule_templates is None
                    else selected_rule_templates
                )
            ],
            CONF_WATCHED_DEVICES: (
                self._get_stored_watched_devices()
                if watched_devices is None
                else watched_devices
            ),
            CONF_DEVICE_TRACKERS: (
                self._get_stored_device_trackers()
                if device_trackers is None
                else device_trackers
            ),
            CONF_DEVICE_TRACKER_AWAY_WINDOW: (
                self._get_stored_device_tracker_away_window()
                if device_tracker_away_window is None
                else device_tracker_away_window
            ),
            CONF_WATCHED_USERS: (
                self._get_stored_watched_users()
                if watched_users is None
                else watched_users
            ),
            CONF_WATCHED_DEVICE_ONLINE_WINDOW: (
                self._get_stored_watched_device_online_window()
                if watched_device_online_window is None
                else watched_device_online_window
            ),
            CONF_UPDATE_INTERVAL: (
                self._get_stored_update_interval()
                if update_interval is None
                else update_interval
            ),
        }

    def _update_entry_options(self, options: dict[str, object]) -> None:
        """Persist options while keeping the options flow open."""
        async_update_entry_options(self.hass, self._config_entry, options)

    async def async_step_init(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Show the top-level options menu."""
        del user_input
        return self.async_show_menu(
            step_id=_STEP_ID_INIT,
            menu_options=[
                _STEP_ID_RULE_SELECTION,
                _STEP_ID_EDIT_WATCHED_DEVICES,
                _STEP_ID_EDIT_DEVICE_TRACKERS,
                _STEP_ID_EDIT_WATCHED_USERS,
                _STEP_ID_GENERAL_OPTIONS,
            ],
        )

    async def async_step_rule_selection(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Show the rule-selection submenu."""
        del user_input
        return self.async_show_menu(
            step_id=_STEP_ID_RULE_SELECTION,
            menu_options=[_STEP_ID_EDIT_RULE_SELECTION, _STEP_ID_INIT],
        )

    async def async_step_edit_rule_selection(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Manage rule-selection options."""
        live_rule_choices = self._get_rule_choices()
        option_labels = await self._async_get_option_labels()
        missing_rule_choices = self._get_missing_rule_choices(
            live_rule_choices,
            unavailable_rule_label=option_labels[
                TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE
            ],
            unavailable_rule_suffix=option_labels[
                TRANS_KEY_OPTION_LABEL_UNAVAILABLE_RULE_SUFFIX
            ],
        )
        rule_choices = {**live_rule_choices, **missing_rule_choices}
        rule_templates = self._get_rule_templates()

        if user_input is not None:
            typed_user_input = RuleSelectionOptionsInput(
                selected_rule_ids=cast(
                    list[str], user_input.get(CONF_SELECTED_RULE_IDS, [])
                ),
                return_to_main_menu=cast(
                    bool, user_input.get(_OPTION_RETURN_TO_MAIN_MENU, False)
                ),
            )
            if typed_user_input.get(_OPTION_RETURN_TO_MAIN_MENU, False):
                return await self.async_step_init()

            selected_rule_ids = sorted(
                rule_id
                for rule_id in typed_user_input.get(CONF_SELECTED_RULE_IDS, [])
                if rule_id in rule_templates
            )
            self._update_entry_options(
                self._build_options_payload(
                    selected_rule_ids=selected_rule_ids,
                    selected_rule_templates=tuple(
                        rule_templates[rule_id] for rule_id in selected_rule_ids
                    ),
                )
            )
            return await self.async_step_init()

        stored_selected_rule_ids, _stored_templates = self._get_stored_rule_selection()
        selected_rule_ids = [
            rule_id for rule_id in stored_selected_rule_ids if rule_id in rule_choices
        ]
        return self.async_show_form(
            step_id=_STEP_ID_EDIT_RULE_SELECTION,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SELECTED_RULE_IDS,
                        default=selected_rule_ids,
                    ): cv.multi_select(rule_choices),
                    vol.Optional(
                        _OPTION_RETURN_TO_MAIN_MENU,
                        default=False,
                    ): bool,
                }
            ),
        )

    async def async_step_edit_watched_devices(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Manage watched-device selection options."""
        live_watched_device_choices = self._get_watched_device_choices()
        option_labels = await self._async_get_option_labels()
        missing_watched_device_choices = self._get_missing_watched_device_choices(
            live_watched_device_choices,
            unavailable_watched_device_label=option_labels[
                TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE
            ],
        )
        watched_device_choices = {
            **live_watched_device_choices,
            **missing_watched_device_choices,
        }

        if user_input is not None:
            typed_user_input = WatchedDevicesOptionsInput(
                watched_devices=cast(
                    list[str], user_input.get(CONF_WATCHED_DEVICES, [])
                ),
                return_to_main_menu=cast(
                    bool, user_input.get(_OPTION_RETURN_TO_MAIN_MENU, False)
                ),
            )
            if typed_user_input.get(_OPTION_RETURN_TO_MAIN_MENU, False):
                return await self.async_step_init()

            watched_devices = sorted(
                mac
                for mac in typed_user_input.get(CONF_WATCHED_DEVICES, [])
                if mac in watched_device_choices
            )
            self._update_entry_options(
                self._build_options_payload(watched_devices=watched_devices)
            )
            return await self.async_step_init()

        selected_watched_devices = [
            mac
            for mac in self._get_stored_watched_devices()
            if mac in watched_device_choices
        ]
        return self.async_show_form(
            step_id=_STEP_ID_EDIT_WATCHED_DEVICES,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_WATCHED_DEVICES,
                        default=selected_watched_devices,
                    ): cv.multi_select(watched_device_choices),
                    vol.Optional(
                        _OPTION_RETURN_TO_MAIN_MENU,
                        default=False,
                    ): bool,
                }
            ),
        )

    async def async_step_edit_watched_users(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Manage watched-user selection options."""
        live_watched_user_choices = self._get_watched_user_choices()
        option_labels = await self._async_get_option_labels()
        missing_watched_user_choices = self._get_missing_watched_user_choices(
            live_watched_user_choices,
            unavailable_watched_user_label=option_labels[
                TRANS_KEY_OPTION_LABEL_UNAVAILABLE_USER
            ],
        )
        watched_user_choices = {
            **live_watched_user_choices,
            **missing_watched_user_choices,
        }

        if user_input is not None:
            typed_user_input = WatchedUsersOptionsInput(
                watched_users=cast(list[str], user_input.get(CONF_WATCHED_USERS, [])),
                return_to_main_menu=cast(
                    bool, user_input.get(_OPTION_RETURN_TO_MAIN_MENU, False)
                ),
            )
            if typed_user_input.get(_OPTION_RETURN_TO_MAIN_MENU, False):
                return await self.async_step_init()

            watched_users = sorted(
                user_id
                for user_id in typed_user_input.get(CONF_WATCHED_USERS, [])
                if user_id in watched_user_choices
            )
            self._update_entry_options(
                self._build_options_payload(watched_users=watched_users)
            )
            return await self.async_step_init()

        selected_watched_users = [
            user_id
            for user_id in self._get_stored_watched_users()
            if user_id in watched_user_choices
        ]
        return self.async_show_form(
            step_id=_STEP_ID_EDIT_WATCHED_USERS,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_WATCHED_USERS,
                        default=selected_watched_users,
                    ): cv.multi_select(watched_user_choices),
                    vol.Optional(
                        _OPTION_RETURN_TO_MAIN_MENU,
                        default=False,
                    ): bool,
                }
            ),
        )

    async def async_step_edit_device_trackers(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Manage device-tracker selection options."""
        live_device_tracker_choices = self._get_device_tracker_choices()
        option_labels = await self._async_get_option_labels()
        missing_device_tracker_choices = self._get_missing_device_tracker_choices(
            live_device_tracker_choices,
            unavailable_device_tracker_label=option_labels[
                TRANS_KEY_OPTION_LABEL_UNAVAILABLE_DEVICE_TRACKER
            ],
        )
        device_tracker_choices = {
            **live_device_tracker_choices,
            **missing_device_tracker_choices,
        }

        if user_input is not None:
            typed_user_input = DeviceTrackersOptionsInput(
                device_trackers=cast(
                    list[str], user_input.get(CONF_DEVICE_TRACKERS, [])
                ),
                return_to_main_menu=cast(
                    bool, user_input.get(_OPTION_RETURN_TO_MAIN_MENU, False)
                ),
            )
            if typed_user_input.get(_OPTION_RETURN_TO_MAIN_MENU, False):
                return await self.async_step_init()

            device_trackers = sorted(
                mac
                for mac in typed_user_input.get(CONF_DEVICE_TRACKERS, [])
                if mac in device_tracker_choices
            )
            self._update_entry_options(
                self._build_options_payload(device_trackers=device_trackers)
            )
            return await self.async_step_init()

        selected_device_trackers = [
            mac
            for mac in self._get_stored_device_trackers()
            if mac in device_tracker_choices
        ]
        return self.async_show_form(
            step_id=_STEP_ID_EDIT_DEVICE_TRACKERS,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DEVICE_TRACKERS,
                        default=selected_device_trackers,
                    ): cv.multi_select(device_tracker_choices),
                    vol.Optional(
                        _OPTION_RETURN_TO_MAIN_MENU,
                        default=False,
                    ): bool,
                }
            ),
        )

    async def async_step_general_options(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Show the general-options menu."""
        del user_input
        return self.async_show_menu(
            step_id=_STEP_ID_GENERAL_OPTIONS,
            menu_options=[_STEP_ID_SYSTEM_SETTINGS, _STEP_ID_INIT],
        )

    async def async_step_system_settings(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Manage coordinator-owned mutable system settings."""
        stored_selected_rule_ids, stored_selected_rule_templates = (
            self._get_stored_rule_selection()
        )

        if user_input is not None:
            typed_user_input = SystemSettingsOptionsInput(
                device_tracker_away_window=cast(
                    int, user_input[CONF_DEVICE_TRACKER_AWAY_WINDOW]
                ),
                update_interval=cast(int, user_input[CONF_UPDATE_INTERVAL]),
                return_to_main_menu=cast(
                    bool, user_input.get(_OPTION_RETURN_TO_MAIN_MENU, False)
                ),
                watched_device_online_window=cast(
                    int, user_input[CONF_WATCHED_DEVICE_ONLINE_WINDOW]
                ),
            )
            if typed_user_input.get(_OPTION_RETURN_TO_MAIN_MENU, False):
                return await self.async_step_init()

            self._update_entry_options(
                self._build_options_payload(
                    selected_rule_ids=stored_selected_rule_ids,
                    selected_rule_templates=stored_selected_rule_templates,
                    device_tracker_away_window=typed_user_input[
                        CONF_DEVICE_TRACKER_AWAY_WINDOW
                    ],
                    update_interval=typed_user_input[CONF_UPDATE_INTERVAL],
                    watched_device_online_window=typed_user_input[
                        CONF_WATCHED_DEVICE_ONLINE_WINDOW
                    ],
                )
            )
            return await self.async_step_init()

        return self.async_show_form(
            step_id=_STEP_ID_SYSTEM_SETTINGS,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_WATCHED_DEVICE_ONLINE_WINDOW,
                        default=self._get_stored_watched_device_online_window(),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_WATCHED_DEVICE_ONLINE_WINDOW_MINUTES),
                    ),
                    vol.Required(
                        CONF_DEVICE_TRACKER_AWAY_WINDOW,
                        default=self._get_stored_device_tracker_away_window(),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_DEVICE_TRACKER_AWAY_WINDOW_MINUTES),
                    ),
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=self._get_stored_update_interval(),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_UPDATE_INTERVAL_MINUTES,
                            max=MAX_UPDATE_INTERVAL_MINUTES,
                        ),
                    ),
                    vol.Optional(
                        _OPTION_RETURN_TO_MAIN_MENU,
                        default=False,
                    ): bool,
                }
            ),
        )
