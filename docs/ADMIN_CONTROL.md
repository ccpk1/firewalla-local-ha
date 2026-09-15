# Firewalla Local admin control

## Purpose

This document is the static contract for the guarded expert administration
services. The runtime source of truth is
`firewalla_local.get_admin_capabilities`, which reports the exact allowlists
installed in Home Assistant.

The command catalog below was checked against the `setHandler`, `getHandler`,
and `cmdHandler` cases in the Firewalla box runtime. The observed build was the
Winterfell Firewalla Gold Plus beta 6.0 source on 2026-09-15. A later Firewalla
firmware may change the object required by an item.

## Home Assistant services

| Service | Purpose |
| --- | --- |
| `get_admin_capabilities` | Return the current read, set, command, exclusion, and safeguard catalog |
| `admin_read` | Run one allowlisted local `get` item and redact sensitive response fields |
| `admin_execute` | Dry-run or execute one allowlisted local `set` or `cmd` item |
| `admin_rollback_network_config` | Dry-run or restore a raw in-memory network snapshot by hash |

## Read items

`admin_read` supports these live `getHandler` items:

| Area | Items |
| --- | --- |
| Network | `assetsConfig`, `availableWlans`, `dhcpLease`, `networkConfig`, `networkConfigHistory`, `networkProfiles`, `networkState`, `networkStatus`, `upstreamDns`, `wanConnectivity`, `wanInterfaces`, `wlanChannels` |
| Policy and identity | `customizedCategories`, `eptGroup`, `exceptions`, `excludedDomains`, `includedDomains`, `policies`, `userConfig` |
| VPN | `ovpnProfiles`, `vpnProfiles` |
| System and usage | `auditLogs`, `dataPlan`, `publicIp`, `sysInfo`, `timezone` |

The `networkConfig` response also includes `config_hash`. VPN and other
responses keep their structure but redact keys that look like passwords,
tokens, private material, credentials, secrets, or certificates.

## Set items

`admin_execute` sends these through the live `setHandler`:

| Area | Items |
| --- | --- |
| Device and group | `policy`, `tag` |
| Network | `autoSpoof`, `dhcp`, `dhcpSpoof`, `manualSpoof`, `mode`, `networkConfig`, `router`, `spoof`, `userConfig` |
| Appliance | `autoUpgrade`, `cpuProfile`, `dataPlan`, `eptGroupName`, `forceNotificationLocalization`, `includeNameInNotification`, `timezone` |

## Command items

`admin_execute` sends these through the live `cmdHandler`:

| Area | Items |
| --- | --- |
| Device | `host:pin`, `host:unpin`, `user` |
| Groups and categories | `tag:create`, `tag:remove`, `createOrUpdateRuleGroup`, `removeRuleGroup`, `createOrUpdateCustomizedCategory`, `removeCustomizedCategory`, `deleteCategory`, `updateIncludedElements` |
| Rules and exceptions | `policy:batch`, `policy:create`, `policy:delete`, `policy:disable`, `policy:enable`, `policy:resetStats`, `policy:setDisableAll`, `policy:toggle`, `policy:update`, `exception:create`, `exception:delete`, `exception:update` |
| Network and DNS | `addExcludeDomain`, `addIncludeDomain`, `removeExcludeDomain`, `removeIncludeDomain`, `ddnsUpdate`, `dnsmasq`, `networkInterface:reset`, `networkInterface:revert`, `networkInterface:update`, `renewDHCPLease`, `removeUPnP` |
| Spoofing and binding | `disableBinding`, `enableBinding`, `manualSpoofUpdate`, `setManualSpoof` |
| VPN and routing | `createOrUpdateVirtWanGroup`, `removeVirtWanGroup`, `saveVpnProfile`, `saveOvpnProfile`, `startVpnClient`, `stopVpnClient`, `deleteVpnProfile`, `deleteOvpnProfile`, `vpnProfile:delete`, `vpnProfile:grant` |
| Wireless | `staBssSteer`, `wifi:switch` |
| Intelligence and features | `customIntel:update`, `disableFeature`, `enableFeature`, `vipProfile:create`, `vipProfile:delete` |

## Core payload examples

The service does not invent missing fields. Pass the exact object required by
the running Firewalla firmware.

### Device group lifecycle

```yaml
# Create
item: tag:create
value:
  name: Guests

# Rename: target is the current tag UID
item: tag
target: "17"
value:
  name: Visitors

# Remove
item: tag:remove
value:
  uid: "17"
```

Device group membership is stored as a device-scoped policy. Use `item: policy`
with the device MAC as `target` and a policy value based on a fresh host record.
Preserve unrelated policy keys when changing membership.

### Rule lifecycle

```yaml
# Delete
item: policy:delete
value:
  policyID: "744"

# Update
item: policy:update
value:
  pid: "744"
  disabled: 1
```

Create and full update payloads vary by rule type. Start from an existing rule
of the same type returned by `get_runtime_inventory` or `admin_read` with
`item: policies`, then change only the intended fields.

### VPN client lifecycle

```yaml
item: startVpnClient
value:
  type: wireguard
  profileId: homevpn
```

`saveVpnProfile` requires `profileId` and accepts `type`, profile data, and a
`settings` object. The live firmware restricts `profileId` to ten or fewer
letters, numbers, or underscores. Stop a running profile before deleting it.

### Complete network configuration

1. Call `admin_read` with `item: networkConfig`.
2. Keep the returned `config_hash`; the manager stores the raw snapshot in
   memory without returning its sensitive fields.
3. Edit a copy of the complete object.
4. Call `admin_execute` in dry-run mode and review `impact`.
5. Execute with `dry_run: false`, `confirm: true`, and
   `expected_current_hash` from step 1.
6. Read back the configuration and connectivity state.

`networkConfig` is the full FireRouter object. It contains the WAN, LAN, VLAN,
route, DHCP, DNS, wireless, and related configuration supported by that box.
The manager sends it as `value.config`, matching the live `setHandler`.

Rollback uses the same guarded write path: read the new current hash and call
`admin_rollback_network_config` with the original snapshot hash. Raw snapshots
are bounded to five and are lost on integration reload or Home Assistant
restart. `admin_read` can still retrieve Firewalla's native
`networkConfigHistory` for external recovery.

## Safeguards

- Unknown item names are rejected.
- `dry_run` defaults to `true`.
- Execution requires `dry_run: false` and `confirm: true`.
- Network config execution requires a fresh matching hash.
- Every network config plan or execution runs `networkConfigImpact` first.
- Sensitive response keys are redacted.
- Five raw network snapshots are kept only in manager memory for rollback.
- A successful write refreshes the coordinator unless `refresh: false` is set.

## Excluded commands

The generic admin surface intentionally excludes arbitrary shell execution,
package installation, SSH key or password operations, migration archives,
debug controls, reboot or shutdown, and firmware branch or upgrade operations.
Those commands can expose credentials, run operating-system code, or remove the
management path needed for rollback. `get_admin_capabilities` returns the exact
excluded item names and reasons.
