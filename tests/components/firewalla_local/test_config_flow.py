"""Tests for the Firewalla Local config flow."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.firewalla_local.api import FirewallaApiError
from custom_components.firewalla_local.api.models import (
    FirewallaProvisionedCredentials,
    GeneratedKeys,
)
from custom_components.firewalla_local.config_flow import FirewallaOptionsFlow
from custom_components.firewalla_local.const import (
    CONF_AID,
    CONF_EID,
    CONF_GID,
    CONF_HOST,
    CONF_LICENSE,
    CONF_QR_JSON,
    CONF_SELECTED_RULE_IDS,
    CONF_SELECTED_RULE_TEMPLATES,
    CONF_SYMMETRIC_KEY,
    DEFAULT_FIREWALLA_HOST,
    DOMAIN,
)
from custom_components.firewalla_local.helpers.runtime_inventory import (
    build_runtime_inventory_report,
)
from custom_components.firewalla_local.managers import FirewallaRuleManager
from custom_components.firewalla_local.models import (
    FirewallaPolicyRule,
    FirewallaRuntimeSnapshot,
    FirewallaSystemInfo,
)

TEST_QR_JSON = (
    '{"ek":"test-ek","seed":"test-seed","license":"license-123",'
    '"gid":"gid-123","ipaddress":"192.168.200.1"}'
)
TEST_ALT_QR_JSON = (
    '{"ek":"test-ek","seed":"test-seed","license":"license-999",'
    '"gid":"gid-999","ipaddress":"192.168.200.9"}'
)


def _mock_keys() -> GeneratedKeys:
    return GeneratedKeys(private_pem="private", public_pem="public")


def _mock_credentials(
    *, license: str = "license-123"
) -> FirewallaProvisionedCredentials:
    return FirewallaProvisionedCredentials(
        license=license,
        host="192.168.200.1",
        gid="gid-123",
        eid="eid-123",
        aid="aid-123",
        symmetric_key="symmetric-key",
        box_name="Firewalla",
    )


async def test_user_flow_creates_entry(hass) -> None:
    """Test the user flow creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with (
        patch(
            "custom_components.firewalla_local.config_flow.generate_firewalla_keys",
            return_value=_mock_keys(),
        ),
        patch(
            "custom_components.firewalla_local.config_flow.async_provision_firewalla_credentials",
            new=AsyncMock(return_value=_mock_credentials()),
        ),
        patch(
            "custom_components.firewalla_local.config_flow.FirewallaApiClient.async_get_system_info",
            new=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: DEFAULT_FIREWALLA_HOST,
                CONF_QR_JSON: TEST_QR_JSON,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Firewalla (192.168.200.1)"
    assert result["data"] == {
        CONF_LICENSE: "license-123",
        CONF_HOST: "192.168.200.1",
        CONF_GID: "gid-123",
        CONF_EID: "eid-123",
        CONF_AID: "aid-123",
        CONF_SYMMETRIC_KEY: "symmetric-key",
    }


async def test_duplicate_license_aborts(hass) -> None:
    """Test duplicate Firewalla licenses are rejected."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.1",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    existing_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: DEFAULT_FIREWALLA_HOST,
            CONF_QR_JSON: TEST_QR_JSON,
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_invalid_qr_shows_form_error(hass) -> None:
    """Test an invalid host is rejected before provisioning starts."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "",
            CONF_QR_JSON: "not-json",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_host"}


async def test_invalid_qr_shows_qr_error(hass) -> None:
    """Test malformed QR JSON returns the QR validation error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: DEFAULT_FIREWALLA_HOST,
            CONF_QR_JSON: "not-json",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_qr"}


async def test_user_flow_cannot_connect_shows_form_error(hass) -> None:
    """Test a pairing connectivity failure returns the cannot_connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    with (
        patch(
            "custom_components.firewalla_local.config_flow.generate_firewalla_keys",
            return_value=_mock_keys(),
        ),
        patch(
            "custom_components.firewalla_local.config_flow.async_provision_firewalla_credentials",
            new=AsyncMock(side_effect=FirewallaApiError),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: DEFAULT_FIREWALLA_HOST,
                CONF_QR_JSON: TEST_QR_JSON,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_updates_existing_entry(hass) -> None:
    """Test reauth refreshes stored credentials for an existing entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.9",
            CONF_GID: "gid-123",
            CONF_EID: "eid-old",
            CONF_AID: "aid-old",
            CONF_SYMMETRIC_KEY: "old-key",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with (
        patch(
            "custom_components.firewalla_local.config_flow.generate_firewalla_keys",
            return_value=_mock_keys(),
        ),
        patch(
            "custom_components.firewalla_local.config_flow.async_provision_firewalla_credentials",
            new=AsyncMock(return_value=_mock_credentials()),
        ),
        patch(
            "custom_components.firewalla_local.config_flow.FirewallaApiClient.async_get_system_info",
            new=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: DEFAULT_FIREWALLA_HOST,
                CONF_QR_JSON: TEST_QR_JSON,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {
        CONF_LICENSE: "license-123",
        CONF_HOST: "192.168.200.1",
        CONF_GID: "gid-123",
        CONF_EID: "eid-123",
        CONF_AID: "aid-123",
        CONF_SYMMETRIC_KEY: "symmetric-key",
    }


async def test_reauth_invalid_host_shows_form_error(hass) -> None:
    """Test reauth rejects a blank host before reprovisioning starts."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.9",
            CONF_GID: "gid-123",
            CONF_EID: "eid-old",
            CONF_AID: "aid-old",
            CONF_SYMMETRIC_KEY: "old-key",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "   ",
            CONF_QR_JSON: TEST_QR_JSON,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_host"}


async def test_reauth_invalid_qr_shows_form_error(hass) -> None:
    """Test reauth rejects malformed QR JSON."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.9",
            CONF_GID: "gid-123",
            CONF_EID: "eid-old",
            CONF_AID: "aid-old",
            CONF_SYMMETRIC_KEY: "old-key",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: DEFAULT_FIREWALLA_HOST,
            CONF_QR_JSON: "not-json",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_qr"}


async def test_reauth_cannot_connect_shows_form_error(hass) -> None:
    """Test reauth returns cannot_connect when reprovisioning fails."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.9",
            CONF_GID: "gid-123",
            CONF_EID: "eid-old",
            CONF_AID: "aid-old",
            CONF_SYMMETRIC_KEY: "old-key",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )

    with (
        patch(
            "custom_components.firewalla_local.config_flow.generate_firewalla_keys",
            return_value=_mock_keys(),
        ),
        patch(
            "custom_components.firewalla_local.config_flow.async_provision_firewalla_credentials",
            new=AsyncMock(side_effect=FirewallaApiError),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: DEFAULT_FIREWALLA_HOST,
                CONF_QR_JSON: TEST_QR_JSON,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_wrong_account_aborts(hass) -> None:
    """Test reauth rejects credentials from a different Firewalla license."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.9",
            CONF_GID: "gid-123",
            CONF_EID: "eid-old",
            CONF_AID: "aid-old",
            CONF_SYMMETRIC_KEY: "old-key",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )

    with (
        patch(
            "custom_components.firewalla_local.config_flow.generate_firewalla_keys",
            return_value=_mock_keys(),
        ),
        patch(
            "custom_components.firewalla_local.config_flow.async_provision_firewalla_credentials",
            new=AsyncMock(return_value=_mock_credentials(license="license-999")),
        ),
        patch(
            "custom_components.firewalla_local.config_flow.FirewallaApiClient.async_get_system_info",
            new=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: DEFAULT_FIREWALLA_HOST,
                CONF_QR_JSON: TEST_ALT_QR_JSON,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


async def test_reconfigure_updates_existing_entry_host(hass) -> None:
    """Test reconfigure updates the stored host and reloads the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.9",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: " FIRE.WALLA "},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "fire.walla"


async def test_reconfigure_invalid_host_shows_form_error(hass) -> None:
    """Test reconfigure shows an invalid_host error instead of crashing."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (192.168.200.1)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "192.168.200.9",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: "   "},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_host"}


async def test_options_flow_handles_missing_runtime_data(hass) -> None:
    """Test the options flow stays stable when runtime data is unavailable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (fire.walla)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "fire.walla",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={CONF_SELECTED_RULE_IDS: ["736"]},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    field = result["data_schema"].schema[CONF_SELECTED_RULE_IDS]
    assert field.options == {"736": "[736] Unavailable rule"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_SELECTED_RULE_IDS: []},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SELECTED_RULE_IDS: [],
        CONF_SELECTED_RULE_TEMPLATES: [],
    }


async def test_options_flow_updates_selected_rule_ids(hass) -> None:
    """Test the options flow stores supported switch rule templates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (fire.walla)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "fire.walla",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={CONF_SELECTED_RULE_IDS: []},
    )
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            data=FirewallaRuntimeSnapshot(
                system_info=FirewallaSystemInfo(
                    host="fire.walla",
                    name="Firewalla",
                    model="gold",
                    serial_number="serial-123",
                    software_version="1.0.0",
                ),
                policy_rules=(
                    FirewallaPolicyRule(
                        rule_id="736",
                        action="block",
                        target="TAG",
                        target_type="mac",
                        direction="bidirection",
                        enabled=True,
                        purpose=None,
                        scope=(),
                        tag_refs=("tag:10",),
                        target_name="KADEN's Devices (KADEN)",
                    ),
                    FirewallaPolicyRule(
                        rule_id="735",
                        action="block",
                        target="games",
                        target_type="category",
                        direction="bidirection",
                        enabled=True,
                        purpose=None,
                        scope=(),
                        tag_refs=("tag:10",),
                        target_name="games",
                        applies_to=("KADEN's Devices (KADEN)",),
                        dnsmasq_only=True,
                    ),
                    FirewallaPolicyRule(
                        rule_id="734",
                        action="block",
                        target="doh",
                        target_type="category",
                        direction="bidirection",
                        enabled=True,
                        purpose="family",
                        scope=(),
                        tag_refs=("tag:10",),
                        target_name="doh",
                        applies_to=("KADEN's Devices (KADEN)",),
                        dnsmasq_only=True,
                    ),
                    FirewallaPolicyRule(
                        rule_id="739",
                        action="block",
                        target="00:08:9B:FB:01:D9",
                        target_type="mac",
                        direction="bidirection",
                        enabled=False,
                        purpose="dap",
                        scope=(),
                        tag_refs=(),
                        target_name="Living room speaker",
                    ),
                    FirewallaPolicyRule(
                        rule_id="738",
                        action="allow",
                        target="dap_00089bfb01d9",
                        target_type="category",
                        direction="outbound",
                        enabled=True,
                        purpose="dap",
                        scope=("00:08:9B:FB:01:D9",),
                        tag_refs=(),
                        target_name="Kitchen speaker",
                    ),
                    FirewallaPolicyRule(
                        rule_id="737",
                        action="allow",
                        target="spotify.com",
                        target_type="dns",
                        direction="outbound",
                        enabled=True,
                        purpose=None,
                        scope=(),
                        tag_refs=("tag:10",),
                        target_name=None,
                        applies_to=("KADEN's Devices (KADEN)",),
                    ),
                    FirewallaPolicyRule(
                        rule_id="741",
                        action="block",
                        target="social",
                        target_type="category",
                        direction="bidirection",
                        enabled=True,
                        purpose=None,
                        scope=(),
                        tag_refs=("tag:10",),
                        target_name="social",
                        applies_to=("KADEN's Devices (KADEN)",),
                        dnsmasq_only=True,
                        auto_delete_when_expires=True,
                    ),
                    FirewallaPolicyRule(
                        rule_id="740",
                        action="block",
                        target="social",
                        target_type="category",
                        direction="bidirection",
                        enabled=True,
                        purpose=None,
                        scope=(),
                        tag_refs=("tag:10",),
                        target_name="social",
                        applies_to=("KADEN's Devices (KADEN)",),
                        dnsmasq_only=True,
                    ),
                    FirewallaPolicyRule(
                        rule_id="743",
                        action="block",
                        target="5799d896-5e0f-40a5-a776-38a5d7746204",
                        target_type="network",
                        direction="bidirection",
                        enabled=True,
                        purpose=None,
                        scope=(),
                        tag_refs=("tag:10",),
                        target_name="VLAN10 CORE",
                        applies_to=("KADEN's Devices (KADEN)",),
                    ),
                    FirewallaPolicyRule(
                        rule_id="742",
                        action="allow",
                        target="TL-56d856bb-efdc-4894-8e5f-c483555e09f6",
                        target_type="category",
                        direction="outbound",
                        enabled=True,
                        purpose=None,
                        scope=(),
                        tag_refs=("tag:10",),
                        target_name=None,
                        applies_to=("KADEN's Devices (KADEN)",),
                    ),
                ),
                exception_rule_count=0,
            )
        )
    )
    entry.add_to_hass(hass)

    options_flow = FirewallaOptionsFlow(entry)
    preview_result = await options_flow.async_step_init()
    field = preview_result["data_schema"].schema[CONF_SELECTED_RULE_IDS]
    assert field.options == {
        "735": "[735] block category games for KADEN's Devices (KADEN) (enabled)",
        "736": "[736] block internet for KADEN's Devices (KADEN) (enabled)",
        "737": "[737] allow dns spotify.com for KADEN's Devices (KADEN) (enabled)",
        "741": "[741] block category social for KADEN's Devices (KADEN) (enabled)",
        "740": "[740] block category social for KADEN's Devices (KADEN) (enabled)",
        "742": (
            "[742] allow category TL-56d856bb-efdc-4894-8e5f-c483555e09f6 "
            "for KADEN's Devices (KADEN) (enabled)"
        ),
        "743": "[743] block network VLAN10 CORE for KADEN's Devices (KADEN) (enabled)",
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_SELECTED_RULE_IDS: ["736"]},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SELECTED_RULE_IDS: ["736"],
        CONF_SELECTED_RULE_TEMPLATES: [
            {
                "source_rule_id": "736",
                "name": "block internet for KADEN's Devices (KADEN)",
                "action": "block",
                "target": "TAG",
                "target_type": "mac",
                "scope": [],
                "tag_refs": ["tag:10"],
                "dnsmasq_only": None,
                "use_bf": True,
            }
        ],
    }


async def test_options_flow_refreshes_runtime_before_building_selector(hass) -> None:
    """Test opening the options flow refreshes the live runtime list first."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (fire.walla)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "fire.walla",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={CONF_SELECTED_RULE_IDS: []},
    )

    initial_snapshot = FirewallaRuntimeSnapshot(
        system_info=FirewallaSystemInfo(
            host="fire.walla",
            name="Firewalla",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        policy_rules=(),
        exception_rule_count=0,
    )
    refreshed_snapshot = FirewallaRuntimeSnapshot(
        system_info=initial_snapshot.system_info,
        policy_rules=(
            FirewallaPolicyRule(
                rule_id="737",
                action="allow",
                target="spotify.com",
                target_type="dns",
                direction="outbound",
                enabled=True,
                purpose=None,
                scope=(),
                tag_refs=("tag:10",),
                applies_to=("KADEN's Devices (KADEN)",),
            ),
        ),
        exception_rule_count=0,
    )

    coordinator = SimpleNamespace(data=initial_snapshot)

    async def _async_request_refresh() -> None:
        coordinator.data = refreshed_snapshot

    coordinator.async_request_refresh = AsyncMock(side_effect=_async_request_refresh)
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    entry.add_to_hass(hass)

    options_flow = FirewallaOptionsFlow(entry)
    result = await options_flow.async_step_init()

    field = result["data_schema"].schema[CONF_SELECTED_RULE_IDS]
    assert coordinator.async_request_refresh.await_count == 1
    assert field.options == {
        "737": "[737] allow dns spotify.com for KADEN's Devices (KADEN) (enabled)"
    }


async def test_options_flow_fallback_excludes_system_managed_rules(hass) -> None:
    """Test the snapshot fallback still excludes system-managed rules."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (fire.walla)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "fire.walla",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={CONF_SELECTED_RULE_IDS: []},
    )
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            data=FirewallaRuntimeSnapshot(
                system_info=FirewallaSystemInfo(
                    host="fire.walla",
                    name="Firewalla",
                    model="gold",
                    serial_number="serial-123",
                    software_version="1.0.0",
                ),
                policy_rules=(
                    FirewallaPolicyRule(
                        rule_id="639",
                        action="allow",
                        target="chrome.cloudflare-dns.com",
                        target_type="dns",
                        direction="outbound",
                        enabled=True,
                        purpose=None,
                        scope=(),
                        tag_refs=(),
                        target_name="chrome.cloudflare-dns.com",
                        raw_update_payload={
                            "pid": "639",
                            "action": "allow",
                            "target": "chrome.cloudflare-dns.com",
                            "target_name": "chrome.cloudflare-dns.com",
                            "type": "dns",
                            "direction": "outbound",
                            "disabled": 0,
                            "notes": (
                                "Device Kadens Chromebook (192.168.255.159) "
                                "accessed chrome.cloudflare-dns.com on ."
                            ),
                        },
                    ),
                    FirewallaPolicyRule(
                        rule_id="641",
                        action="block",
                        target="vin17.pbs.ovhnextmillmedia.com",
                        target_type="dns",
                        direction="bidirection",
                        enabled=True,
                        purpose=None,
                        scope=(),
                        tag_refs=(),
                        target_name="vin17.pbs.ovhnextmillmedia.com",
                        raw_update_payload={
                            "pid": "641",
                            "action": "block",
                            "target": "vin17.pbs.ovhnextmillmedia.com",
                            "target_name": "vin17.pbs.ovhnextmillmedia.com",
                            "type": "dns",
                            "direction": "bidirection",
                            "disabled": 0,
                            "method": "auto",
                            "alarm_type": "ALARM_INTEL",
                            "blockby": "fastdns",
                            "category": "intel",
                            "reason": "ALARM_INTEL",
                        },
                    ),
                ),
                exception_rule_count=0,
            )
        )
    )
    entry.add_to_hass(hass)

    options_flow = FirewallaOptionsFlow(entry)
    preview_result = await options_flow.async_step_init()
    field = preview_result["data_schema"].schema[CONF_SELECTED_RULE_IDS]

    assert field.options == {
        "639": "[639] allow dns chrome.cloudflare-dns.com (enabled)"
    }


async def test_options_flow_fallback_matches_runtime_inventory_candidates(
    hass,
) -> None:
    """Test the snapshot fallback matches runtime inventory candidate decisions."""
    payload = {
        "policyRules": [
            {
                "pid": "639",
                "action": "allow",
                "target": "chrome.cloudflare-dns.com",
                "target_name": "chrome.cloudflare-dns.com",
                "type": "dns",
                "direction": "outbound",
                "disabled": 0,
                "notes": (
                    "Device Kadens Chromebook (192.168.255.159) accessed "
                    "chrome.cloudflare-dns.com on ."
                ),
            },
            {
                "pid": "641",
                "action": "block",
                "target": "vin17.pbs.ovhnextmillmedia.com",
                "target_name": "vin17.pbs.ovhnextmillmedia.com",
                "type": "dns",
                "direction": "bidirection",
                "disabled": 0,
                "method": "auto",
                "alarm_type": "ALARM_INTEL",
                "blockby": "fastdns",
                "category": "intel",
                "reason": "ALARM_INTEL",
            },
        ]
    }
    snapshot = FirewallaRuntimeSnapshot(
        system_info=FirewallaSystemInfo(
            host="fire.walla",
            name="Firewalla",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        policy_rules=(
            FirewallaPolicyRule(
                rule_id="639",
                action="allow",
                target="chrome.cloudflare-dns.com",
                target_type="dns",
                direction="outbound",
                enabled=True,
                purpose=None,
                scope=(),
                tag_refs=(),
                target_name="chrome.cloudflare-dns.com",
                raw_update_payload=payload["policyRules"][0],
            ),
            FirewallaPolicyRule(
                rule_id="641",
                action="block",
                target="vin17.pbs.ovhnextmillmedia.com",
                target_type="dns",
                direction="bidirection",
                enabled=True,
                purpose=None,
                scope=(),
                tag_refs=(),
                target_name="vin17.pbs.ovhnextmillmedia.com",
                raw_update_payload=payload["policyRules"][1],
            ),
        ),
        exception_rule_count=0,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (fire.walla)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "fire.walla",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={CONF_SELECTED_RULE_IDS: []},
    )
    entry.runtime_data = SimpleNamespace(coordinator=SimpleNamespace(data=snapshot))
    entry.add_to_hass(hass)

    options_flow = FirewallaOptionsFlow(entry)
    option_ids = list(options_flow._get_rule_choices())
    report = build_runtime_inventory_report(payload, snapshot.policy_rules)
    report_ids = [
        candidate["rule_id"] for candidate in report["rule_switch_candidates"]
    ]

    assert option_ids == report_ids == ["639"]


async def test_options_flow_allows_removing_missing_selected_rule(hass) -> None:
    """Test the options flow can remove a stored rule after it disappears."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (fire.walla)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "fire.walla",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={
            CONF_SELECTED_RULE_IDS: ["999", "736"],
            CONF_SELECTED_RULE_TEMPLATES: [
                {
                    "source_rule_id": "999",
                    "name": "allow dns old.example for KADEN's Devices (KADEN)",
                    "action": "allow",
                    "target": "old.example",
                    "target_type": "dns",
                    "scope": [],
                    "tag_refs": ["tag:10"],
                    "dnsmasq_only": False,
                    "use_bf": True,
                },
                {
                    "source_rule_id": "736",
                    "name": "block internet for KADEN's Devices (KADEN)",
                    "action": "block",
                    "target": "TAG",
                    "target_type": "mac",
                    "scope": [],
                    "tag_refs": ["tag:10"],
                    "dnsmasq_only": None,
                    "use_bf": True,
                },
            ],
        },
    )
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            data=FirewallaRuntimeSnapshot(
                system_info=FirewallaSystemInfo(
                    host="fire.walla",
                    name="Firewalla",
                    model="gold",
                    serial_number="serial-123",
                    software_version="1.0.0",
                ),
                policy_rules=(
                    FirewallaPolicyRule(
                        rule_id="736",
                        action="block",
                        target="TAG",
                        target_type="mac",
                        direction="bidirection",
                        enabled=True,
                        purpose=None,
                        scope=(),
                        tag_refs=("tag:10",),
                        target_name="KADEN's Devices (KADEN)",
                    ),
                ),
                exception_rule_count=0,
            )
        )
    )
    entry.add_to_hass(hass)

    options_flow = FirewallaOptionsFlow(entry)
    preview_result = await options_flow.async_step_init()
    field = preview_result["data_schema"].schema[CONF_SELECTED_RULE_IDS]
    assert field.options == {
        "736": "[736] block internet for KADEN's Devices (KADEN) (enabled)",
        "999": "[999] allow dns old.example for KADEN's Devices (KADEN) (unavailable)",
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_SELECTED_RULE_IDS: ["736"]},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SELECTED_RULE_IDS: ["736"],
        CONF_SELECTED_RULE_TEMPLATES: [
            {
                "source_rule_id": "736",
                "name": "block internet for KADEN's Devices (KADEN)",
                "action": "block",
                "target": "TAG",
                "target_type": "mac",
                "scope": [],
                "tag_refs": ["tag:10"],
                "dnsmasq_only": None,
                "use_bf": True,
            }
        ],
    }


async def test_options_flow_uses_manager_candidate_logic_for_rule_choices() -> None:
    """Test the options flow matches runtime inventory candidate eligibility."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="license-123",
        title="Firewalla (fire.walla)",
        data={
            CONF_LICENSE: "license-123",
            CONF_HOST: "fire.walla",
            CONF_GID: "gid-123",
            CONF_EID: "eid-123",
            CONF_AID: "aid-123",
            CONF_SYMMETRIC_KEY: "symmetric-key",
        },
        options={CONF_SELECTED_RULE_IDS: []},
    )
    snapshot = FirewallaRuntimeSnapshot(
        system_info=FirewallaSystemInfo(
            host="fire.walla",
            name="Firewalla",
            model="gold",
            serial_number="serial-123",
            software_version="1.0.0",
        ),
        policy_rules=(
            FirewallaPolicyRule(
                rule_id="736",
                action="block",
                target="TAG",
                target_type="mac",
                direction="bidirection",
                enabled=True,
                purpose=None,
                scope=(),
                tag_refs=("tag:10",),
                target_name="KADEN's Devices (KADEN)",
            ),
            FirewallaPolicyRule(
                rule_id="742",
                action="allow",
                target="TL-56d856bb-efdc-4894-8e5f-c483555e09f6",
                target_type="category",
                direction="outbound",
                enabled=True,
                purpose=None,
                scope=(),
                tag_refs=("tag:10",),
                target_name="Streaming allow list",
                applies_to=("KADEN's Devices (KADEN)",),
            ),
        ),
        exception_rule_count=0,
    )
    rule_manager = FirewallaRuleManager(
        coordinator=SimpleNamespace(data=snapshot),
        entry=entry,
        client=SimpleNamespace(),
    )
    rule_manager.handle_refresh(
        {
            "policyRules": [
                {
                    "pid": "736",
                    "action": "block",
                    "target": "TAG",
                    "type": "mac",
                    "tag": ["tag:10"],
                },
                {
                    "pid": "742",
                    "action": "allow",
                    "target": "TL-56d856bb-efdc-4894-8e5f-c483555e09f6",
                    "type": "category",
                    "tag": ["tag:10"],
                },
            ]
        },
        snapshot,
    )
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(data=snapshot),
        rule_manager=rule_manager,
    )

    options_flow = FirewallaOptionsFlow(entry)
    preview_result = await options_flow.async_step_init()
    field = preview_result["data_schema"].schema[CONF_SELECTED_RULE_IDS]

    assert field.options == {
        "736": "[736] block internet for KADEN's Devices (KADEN) (enabled)",
        "742": (
            "[742] allow category Streaming allow list "
            "[TL-56d856bb-efdc-4894-8e5f-c483555e09f6] "
            "for KADEN's Devices (KADEN) (enabled)"
        ),
    }
