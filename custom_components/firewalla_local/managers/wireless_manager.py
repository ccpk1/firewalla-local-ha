"""Wireless-domain orchestration for Firewalla Local AP7 access points."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Final

from homeassistant.util.json import JsonObjectType

from ..api import FirewallaApiClient
from ..coordinator import FirewallaConfigEntry, FirewallaDataUpdateCoordinator
from .base_manager import FirewallaBaseManager

_RAW_NETWORK_CONFIG_KEY: Final = "networkConfig"
_RAW_SWITCH_TOPOLOGY_KEY: Final = "switchTopology"
_RAW_APC_KEY: Final = "apc"
_RAW_PROFILE_KEY: Final = "profile"
_RAW_ASSETS_KEY: Final = "assets"
_RAW_ASSETS_TEMPLATE_KEY: Final = "assets_template"
_RAW_WIFI_NETWORKS_KEY: Final = "wifiNetworks"
_RAW_SSID_PROFILES_KEY: Final = "ssidProfiles"
_RAW_PAUSED_KEY: Final = "paused"
_RAW_SSID_KEY: Final = "ssid"
_RAW_BAND_KEY: Final = "band"
_RAW_ENCRYPTION_KEY: Final = "encryption"
_RAW_WPA3_KEY: Final = "wpa3"
_RAW_SYS_CONFIG_KEY: Final = "sysConfig"
_RAW_NAME_KEY: Final = "name"
_RAW_MODEL_KEY: Final = "model"
_RAW_INTF_KEY: Final = "intf"
_RAW_VLAN_KEY: Final = "vlan"
_RAW_TS_KEY: Final = "ts"


class FirewallaSsidProfile:
    """Normalized view of one AP7 SSID profile."""

    __slots__ = (
        "band",
        "encryption",
        "interface",
        "paused",
        "profile_uuid",
        "ssid",
        "vlan",
        "wpa3",
    )

    def __init__(
        self,
        *,
        profile_uuid: str,
        ssid: str | None,
        band: str | None,
        encryption: str | None,
        wpa3: bool | None,
        paused: bool,
        vlan: int | None,
        interface: str | None,
    ) -> None:
        """Initialize one SSID profile."""
        self.profile_uuid = profile_uuid
        self.ssid = ssid
        self.band = band
        self.encryption = encryption
        self.wpa3 = wpa3
        self.paused = paused
        self.vlan = vlan
        self.interface = interface

    @property
    def display_name(self) -> str:
        """Return a readable display name for the profile."""
        if self.ssid:
            return self.ssid
        return self.profile_uuid


class FirewallaAccessPoint:
    """Normalized view of one AP7 access point."""

    __slots__ = ("asset_id", "channel_2g", "channel_5g", "led", "model", "name")

    def __init__(
        self,
        *,
        asset_id: str,
        name: str | None,
        model: str | None,
        channel_5g: str | None,
        channel_2g: str | None,
        led: str | None,
    ) -> None:
        """Initialize one access point."""
        self.asset_id = asset_id
        self.name = name
        self.model = model
        self.channel_5g = channel_5g
        self.channel_2g = channel_2g
        self.led = led


class FirewallaWirelessConnection:
    """Normalized per-client wireless connection info from switchTopology."""

    __slots__ = ("ap_name", "band", "mac", "rssi", "ssid")

    def __init__(
        self,
        *,
        mac: str,
        ssid: str | None,
        band: str | None,
        rssi: int | None,
        ap_name: str | None,
    ) -> None:
        """Initialize one wireless connection."""
        self.mac = mac
        self.ssid = ssid
        self.band = band
        self.rssi = rssi
        self.ap_name = ap_name


class FirewallaWirelessManager(FirewallaBaseManager):
    """Own the AP7 wireless config surface from the raw init payload."""

    def __init__(
        self,
        coordinator: FirewallaDataUpdateCoordinator,
        entry: FirewallaConfigEntry,
        client: FirewallaApiClient,
    ) -> None:
        """Initialize the wireless manager."""
        super().__init__(coordinator, entry, client)
        self._last_payload: dict[str, object] = {}

    def handle_refresh(self, payload: Mapping[str, object]) -> None:
        """Store the latest raw init payload for wireless reads."""
        self._last_payload = dict(payload)

    def _get_apc(self) -> dict[str, Any]:
        """Return the current ``networkConfig.apc`` value or an empty dict."""
        raw_network_config = self._last_payload.get(_RAW_NETWORK_CONFIG_KEY)
        if not isinstance(raw_network_config, dict):
            return {}
        raw_apc = raw_network_config.get(_RAW_APC_KEY)
        if not isinstance(raw_apc, dict):
            return {}
        return raw_apc

    def _get_network_config(self) -> dict[str, Any]:
        """Return the current ``networkConfig`` value or an empty dict."""
        raw_network_config = self._last_payload.get(_RAW_NETWORK_CONFIG_KEY)
        if not isinstance(raw_network_config, dict):
            return {}
        return raw_network_config

    def get_ssid_profiles(self) -> tuple[FirewallaSsidProfile, ...]:
        """Return the current SSID profiles with their network mapping."""
        apc = self._get_apc()
        raw_profiles = apc.get(_RAW_PROFILE_KEY)
        if not isinstance(raw_profiles, dict):
            return ()

        # Build a profile-uuid -> (vlan, interface) mapping from wifiNetworks.
        network_map: dict[str, tuple[int | None, str | None]] = {}
        raw_template = apc.get(_RAW_ASSETS_TEMPLATE_KEY)
        if isinstance(raw_template, dict):
            # wifiNetworks lives under the default template (e.g. ap_default).
            for raw_template_value in raw_template.values():
                if not isinstance(raw_template_value, dict):
                    continue
                for raw_network in raw_template_value.get(_RAW_WIFI_NETWORKS_KEY, []):
                    if not isinstance(raw_network, dict):
                        continue
                    vlan = raw_network.get(_RAW_VLAN_KEY)
                    interface = raw_network.get(_RAW_INTF_KEY)
                    raw_ssid_profiles = raw_network.get(_RAW_SSID_PROFILES_KEY)
                    if not isinstance(raw_ssid_profiles, list):
                        continue
                    for profile_uuid in raw_ssid_profiles:
                        if not isinstance(profile_uuid, str):
                            continue
                        network_map[profile_uuid] = (
                            vlan if isinstance(vlan, int) else None,
                            interface if isinstance(interface, str) else None,
                        )

        profiles: list[FirewallaSsidProfile] = []
        for profile_uuid, raw_profile in raw_profiles.items():
            if not isinstance(profile_uuid, str) or not isinstance(raw_profile, dict):
                continue
            vlan, interface = network_map.get(profile_uuid, (None, None))
            profiles.append(
                FirewallaSsidProfile(
                    profile_uuid=profile_uuid,
                    ssid=(
                        raw_profile.get(_RAW_SSID_KEY)
                        if isinstance(raw_profile.get(_RAW_SSID_KEY), str)
                        else None
                    ),
                    band=(
                        raw_profile.get(_RAW_BAND_KEY)
                        if isinstance(raw_profile.get(_RAW_BAND_KEY), str)
                        else None
                    ),
                    encryption=(
                        raw_profile.get(_RAW_ENCRYPTION_KEY)
                        if isinstance(raw_profile.get(_RAW_ENCRYPTION_KEY), str)
                        else None
                    ),
                    wpa3=(
                        raw_profile.get(_RAW_WPA3_KEY)
                        if isinstance(raw_profile.get(_RAW_WPA3_KEY), bool)
                        else None
                    ),
                    paused=bool(raw_profile.get(_RAW_PAUSED_KEY, False)),
                    vlan=vlan,
                    interface=interface,
                )
            )
        return tuple(profiles)

    def get_access_points(self) -> tuple[FirewallaAccessPoint, ...]:
        """Return the current AP7 access points from the assets section."""
        apc = self._get_apc()
        raw_assets = apc.get(_RAW_ASSETS_KEY)
        if not isinstance(raw_assets, dict):
            return ()

        access_points: list[FirewallaAccessPoint] = []
        for asset_id, raw_asset in raw_assets.items():
            if not isinstance(asset_id, str) or not isinstance(raw_asset, dict):
                continue
            raw_sys_config = raw_asset.get(_RAW_SYS_CONFIG_KEY)
            sys_config = raw_sys_config if isinstance(raw_sys_config, dict) else {}
            raw_channel = sys_config.get("channel")
            channel = raw_channel if isinstance(raw_channel, dict) else {}
            access_points.append(
                FirewallaAccessPoint(
                    asset_id=asset_id,
                    name=(
                        sys_config.get(_RAW_NAME_KEY)
                        if isinstance(sys_config.get(_RAW_NAME_KEY), str)
                        else None
                    ),
                    model=(
                        raw_asset.get(_RAW_MODEL_KEY)
                        if isinstance(raw_asset.get(_RAW_MODEL_KEY), str)
                        else None
                    ),
                    channel_5g=(
                        channel.get("5g")
                        if isinstance(channel.get("5g"), str)
                        else None
                    ),
                    channel_2g=(
                        channel.get("2g")
                        if isinstance(channel.get("2g"), str)
                        else None
                    ),
                    led=(
                        sys_config.get("led")
                        if isinstance(sys_config.get("led"), str)
                        else None
                    ),
                )
            )
        return tuple(access_points)

    def get_wireless_connections(self) -> tuple[FirewallaWirelessConnection, ...]:
        """Return per-client wireless connection info from switchTopology.

        The ``switchTopology`` section of the init response is a tree rooted at
        the box, with ``type=ap`` nodes (the APs) whose children are
        ``type=device`` nodes. Each device node carries ``ssid``, ``band``,
        ``rssi``, and ``parent_port`` (the radio it is attached to). The AP
        name is resolved from the parent ``ap`` node.
        """
        raw_switch_topology = self._last_payload.get(_RAW_SWITCH_TOPOLOGY_KEY)
        if not isinstance(raw_switch_topology, dict):
            return ()
        raw_info = raw_switch_topology.get("info")
        if not isinstance(raw_info, dict):
            return ()
        raw_tree = raw_info.get("tree")
        if not isinstance(raw_tree, list):
            return ()

        connections: list[FirewallaWirelessConnection] = []

        def walk(node: object, ap_name: str | None) -> None:
            if not isinstance(node, dict):
                return
            node_type = node.get("type")
            if node_type == "ap":
                ap_name = (
                    node.get(_RAW_NAME_KEY)
                    if isinstance(node.get(_RAW_NAME_KEY), str)
                    else ap_name
                )
            elif node_type == "device" and node.get("connectionType") == "wireless":
                mac = node.get("mac")
                if isinstance(mac, str):
                    connections.append(
                        FirewallaWirelessConnection(
                            mac=mac,
                            ssid=(
                                node.get("ssid")
                                if isinstance(node.get("ssid"), str)
                                else None
                            ),
                            band=(
                                node.get("band")
                                if isinstance(node.get("band"), str)
                                else None
                            ),
                            rssi=(
                                node.get("rssi")
                                if isinstance(node.get("rssi"), int)
                                else None
                            ),
                            ap_name=ap_name,
                        )
                    )
            for child in node.get("children", []):
                walk(child, ap_name)

        for root in raw_tree:
            walk(root, None)
        return tuple(connections)

    def resolve_ssid_profile(
        self, profile_uuid_or_ssid: str
    ) -> FirewallaSsidProfile | None:
        """Resolve an SSID profile by UUID or by SSID name.

        Accepts either the profile UUID (stable identifier) or the human-facing
        SSID name (e.g. "Universe Guest"). Returns the matching profile or
        ``None`` if no profile matches.
        """
        for profile in self.get_ssid_profiles():
            if profile.profile_uuid == profile_uuid_or_ssid:
                return profile
            if profile.ssid == profile_uuid_or_ssid:
                return profile
        return None

    def _build_network_config_with_paused(
        self, profile_uuid: str, *, paused: bool
    ) -> dict[str, Any]:
        """Return a copy of the full networkConfig with the profile's paused set.

        The confirmed write contract sends the entire ``networkConfig`` object
        (not just ``apc``) wrapped in ``value.config``, with a fresh ``ts``.
        """
        network_config = self._get_network_config()
        raw_apc = network_config.get(_RAW_APC_KEY)
        if not isinstance(raw_apc, dict):
            raise ValueError("No AP controller config available in the runtime payload")
        raw_profiles = raw_apc.get(_RAW_PROFILE_KEY)
        if not isinstance(raw_profiles, dict):
            raise ValueError("No SSID profiles available in the runtime payload")

        updated_profiles = dict(raw_profiles)
        raw_profile = updated_profiles.get(profile_uuid)
        if not isinstance(raw_profile, dict):
            raise ValueError(f"SSID profile not found: {profile_uuid}")

        updated_profile = dict(raw_profile)
        if paused:
            updated_profile[_RAW_PAUSED_KEY] = True
        else:
            updated_profile.pop(_RAW_PAUSED_KEY, None)
        updated_profiles[profile_uuid] = updated_profile

        updated_apc = dict(raw_apc)
        updated_apc[_RAW_PROFILE_KEY] = updated_profiles

        updated_network_config = dict(network_config)
        updated_network_config[_RAW_APC_KEY] = updated_apc
        updated_network_config[_RAW_TS_KEY] = int(time.time() * 1000)
        return updated_network_config

    async def async_set_ssid_paused(
        self,
        profile_uuid: str,
        *,
        paused: bool,
    ) -> dict[str, object]:
        """Toggle the paused state of one SSID profile."""
        network_config_payload = self._build_network_config_with_paused(
            profile_uuid, paused=paused
        )
        return await self.client.async_set_ssid_paused(
            network_config_payload=network_config_payload,
        )

    def get_wireless_status(self) -> JsonObjectType:
        """Return a structured view of the current wireless config."""
        return {
            "ssid_profiles": [
                {
                    "profile_uuid": profile.profile_uuid,
                    "ssid": profile.ssid,
                    "band": profile.band,
                    "encryption": profile.encryption,
                    "wpa3": profile.wpa3,
                    "paused": profile.paused,
                    "vlan": profile.vlan,
                    "interface": profile.interface,
                }
                for profile in self.get_ssid_profiles()
            ],
            "access_points": [
                {
                    "asset_id": ap.asset_id,
                    "name": ap.name,
                    "model": ap.model,
                    "channel_5g": ap.channel_5g,
                    "channel_2g": ap.channel_2g,
                    "led": ap.led,
                }
                for ap in self.get_access_points()
            ],
        }
