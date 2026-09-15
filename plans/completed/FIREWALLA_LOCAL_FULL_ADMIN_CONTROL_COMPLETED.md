# Initiative: Full Local Admin Control

## Outcome

Firewalla Local 2.1.1 exposes the confirmed local configuration surface through
Home Assistant, so an MCP client can inspect and manage devices, groups, rules,
WAN, VLAN, VPN, wireless, routing, DNS, and other supported settings without the
paid cloud API.

## Delivered

- Added generic local `get`, `set`, and `cmd` transport methods.
- Added `FirewallaAdminManager` with strict allowlists and response redaction.
- Added `get_admin_capabilities`, `admin_read`, `admin_execute`, and
  `admin_rollback_network_config` services.
- Writes default to dry run and require both `dry_run: false` and
  `confirm: true` to execute.
- Full `networkConfig` writes require a fresh hash and Firewalla's native impact
  check; five raw rollback snapshots remain in memory for the loaded HA process.
- Device and group policy writes, tag lifecycle, rule CRUD, full network config,
  interface actions, VPN clients, virtual WAN groups, DNS, data plans,
  categories, exceptions, and other confirmed handlers are supported.
- Shell, credential, firmware, migration, reboot, and shutdown commands remain
  excluded.
- Added the full command catalog and a durable upstream sync/release workflow.

## Verification

- Quick lint and formatting: passed.
- Mypy: passed for 34 source files.
- Pytest: 305 passed.
- Home Assistant config check: valid.
- HACS: only `erabti/firewalla-local-ha` is installed, version 2.1.1.
- Firewalla config entry: loaded after restart.
- MCP: 26 reads, 18 set items, and 55 command items discovered.
- Live read: timezone returned `Africa/Tripoli`; WAN interface read succeeded.
- Live dry run: `tag:create` returned `executed: false`; runtime inventory showed
  no `Codex Dry Run` group.
- Post-restart logs: no Firewalla error, duplicate YAML warning, or deprecated
  device-registry warning.

No live WAN, VLAN, VPN, route, rule, group, or device configuration was changed
during acceptance.
