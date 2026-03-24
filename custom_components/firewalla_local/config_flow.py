"""Config flow for Firewalla Local."""

from __future__ import annotations

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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    FirewallaApiClient,
    FirewallaApiError,
    FirewallaValidationError,
    async_provision_firewalla_credentials,
    generate_firewalla_keys,
    load_qr_json,
)
from .const import (
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_QR_JSON,
    CONF_SELECTED_RULE_IDS,
    CONF_SELECTED_RULE_TEMPLATES,
    CONF_SYMMETRIC_KEY,
    CONFIG_ERROR_CANNOT_CONNECT,
    CONFIG_ERROR_INVALID_HOST,
    CONFIG_ERROR_INVALID_QR,
    CONFIG_ERROR_WRONG_ACCOUNT,
    DEFAULT_BOX_NAME,
    DEFAULT_FIREWALLA_HOST,
    DEFAULT_PAIRING_DEVICE_NAME,
    DOMAIN,
)
from .managers import FirewallaRuleManager
from .models import (
    FirewallaPolicyRule,
    FirewallaRuleTemplate,
    format_policy_rule_label,
    supports_rule_switch,
)

_STEP_ID_INIT: Final = "init"
_STEP_ID_REAUTH_CONFIRM: Final = "reauth_confirm"
_STEP_ID_RECONFIGURE: Final = "reconfigure"
_STEP_ID_USER: Final = "user"
_UNAVAILABLE_RULE_LABEL: Final = "Unavailable rule"
_UNAVAILABLE_RULE_SUFFIX: Final = "(unavailable)"


class PairingUserInput(TypedDict):
    """Validated user input for pairing and reauth flows."""

    host: str
    qr_json: str


class RuleSelectionOptionsInput(TypedDict, total=False):
    """Validated user input for the options flow."""

    selected_rule_ids: list[str]


def _normalize_host(host: str) -> str:
    """Normalize a host or IP override used for the local runtime target."""
    normalized_host = host.strip().lower()
    if not normalized_host:
        raise ValueError("Host cannot be empty")
    return normalized_host


def _format_rule_option(rule: FirewallaPolicyRule) -> str:
    """Build a compact label for one selectable Firewalla rule."""
    return f"[{rule.rule_id}] {format_policy_rule_label(rule)}"


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

        self.license = qr_data.license
        self.host = host

        keys = await self.hass.async_add_executor_job(generate_firewalla_keys)
        credentials = await async_provision_firewalla_credentials(
            async_get_clientsession(self.hass),
            qr_data=qr_data,
            host=host,
            keys=keys,
        )
        client = FirewallaApiClient(
            session=async_get_clientsession(self.hass),
            host=credentials.host,
            gid=credentials.gid,
            eid=credentials.eid,
            aid=credentials.aid,
            symmetric_key=credentials.symmetric_key,
            device_name=DEFAULT_PAIRING_DEVICE_NAME,
        )
        await client.async_get_system_info()

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
                errors["base"] = CONFIG_ERROR_INVALID_HOST
            except FirewallaValidationError:
                errors["base"] = CONFIG_ERROR_INVALID_QR
            else:
                self.license = qr_data.license
                self.host = host
                await self.async_set_unique_id(qr_data.license)
                self._abort_if_unique_id_configured()

                try:
                    pairing_result = await self._async_pair_firewalla(typed_user_input)
                except FirewallaApiError:
                    errors["base"] = CONFIG_ERROR_CANNOT_CONNECT
                else:
                    assert pairing_result is not None
                    entry_data, title = pairing_result
                    return self.async_create_entry(title=title, data=entry_data)

        return self.async_show_form(
            step_id=_STEP_ID_USER,
            data_schema=self._build_pairing_schema(),
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
                errors["base"] = CONFIG_ERROR_INVALID_HOST
            except FirewallaValidationError:
                errors["base"] = CONFIG_ERROR_INVALID_QR
            except FirewallaApiError:
                errors["base"] = CONFIG_ERROR_CANNOT_CONNECT
            else:
                assert pairing_result is not None
                entry_data, _title = pairing_result
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
        if user_input is not None:
            host = _normalize_host(cast(str, user_input[CONF_HOST]))
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
        )


class FirewallaOptionsFlow(OptionsFlow):
    """Handle mutable Firewalla Local options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    def _get_rule_manager(self) -> FirewallaRuleManager | None:
        """Return the loaded rule manager when runtime data is available."""
        runtime_data = getattr(self._config_entry, "runtime_data", None)
        if runtime_data is None:
            return None
        rule_manager = getattr(runtime_data, "rule_manager", None)
        if isinstance(rule_manager, FirewallaRuleManager):
            return rule_manager
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

        return {
            rule.rule_id: _format_rule_option(rule)
            for rule in sorted(snapshot.policy_rules, key=lambda rule: rule.rule_id)
            if supports_rule_switch(rule)
        }

    def _get_stored_rule_templates(self) -> dict[str, FirewallaRuleTemplate]:
        """Return persisted rule templates keyed by source rule ID."""
        templates = FirewallaRuleManager.load_selected_templates(
            self._config_entry.options,
            None,
        )
        return {template.source_rule_id: template for template in templates}

    def _get_missing_rule_choices(
        self, live_rule_choices: dict[str, str]
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
                    f"[{rule_id}] {template.name} {_UNAVAILABLE_RULE_SUFFIX}"
                )
            else:
                missing_rule_choices[rule_id] = f"[{rule_id}] {_UNAVAILABLE_RULE_LABEL}"

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

        return {
            rule.rule_id: FirewallaRuleTemplate.from_rule(rule)
            for rule in snapshot.policy_rules
            if supports_rule_switch(rule)
        }

    async def async_step_init(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Manage rule-selection options."""
        live_rule_choices = self._get_rule_choices()
        missing_rule_choices = self._get_missing_rule_choices(live_rule_choices)
        rule_choices = {**live_rule_choices, **missing_rule_choices}
        rule_templates = self._get_rule_templates()

        if user_input is not None:
            typed_user_input = RuleSelectionOptionsInput(
                selected_rule_ids=cast(
                    list[str], user_input.get(CONF_SELECTED_RULE_IDS, [])
                )
            )
            selected_rule_ids = sorted(
                rule_id
                for rule_id in typed_user_input.get(CONF_SELECTED_RULE_IDS, [])
                if rule_id in rule_templates
            )
            return self.async_create_entry(
                title="",
                data={
                    CONF_SELECTED_RULE_IDS: selected_rule_ids,
                    CONF_SELECTED_RULE_TEMPLATES: [
                        rule_templates[rule_id].to_dict()
                        for rule_id in selected_rule_ids
                    ],
                },
            )

        stored_selected_rule_ids = self._config_entry.options.get(
            CONF_SELECTED_RULE_IDS, []
        )
        selected_rule_ids = [
            rule_id
            for rule_id in stored_selected_rule_ids
            if isinstance(rule_id, str) and rule_id in rule_choices
        ]
        return self.async_show_form(
            step_id=_STEP_ID_INIT,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SELECTED_RULE_IDS,
                        default=selected_rule_ids,
                    ): cv.multi_select(rule_choices)
                }
            ),
        )
