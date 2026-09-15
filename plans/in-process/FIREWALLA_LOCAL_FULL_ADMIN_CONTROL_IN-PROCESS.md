# Initiative: Full Local Admin Control

## Goal

Expose the local Firewalla configuration surface through Home Assistant so an
MCP client can inspect and manage devices, groups, rules, WAN, VLAN, VPN,
wireless, routing, and other confirmed settings without the paid cloud API.

## Done means

- Home Assistant exposes a discoverable command catalog.
- Confirmed read commands are available through one structured service.
- Confirmed write commands are available through one guarded service.
- Every write supports dry run and requires explicit confirmation to execute.
- Full `networkConfig` writes require a fresh config hash and run Firewalla's
  native impact check before the write.
- Sensitive response keys are redacted.
- The service documents which commands are supported and which dangerous
  operating-system or credential commands are intentionally excluded.
- Unit, type, lint, formatting, and Home Assistant integration tests pass.
- The fork is committed and pushed with an upstream remote retained.

## Scope

### Must

1. Add public API transport methods for local `get`, `set`, and `cmd` items.
2. Add an admin manager that owns allowlists, dry-run plans, confirmation,
   network optimistic locking, impact checks, response redaction, and refresh.
3. Add `get_admin_capabilities`, `admin_read`, and `admin_execute` services.
4. Cover device/group policy writes, tag/group lifecycle, rule CRUD, complete
   network config, network-interface actions, VPN client lifecycle, virtual WAN
   groups, data-plan settings, DNS settings, and other confirmed config commands.
5. Add tests and user documentation.

### Should

- Verify the read-only services against the paired Winterfell Firewalla.
- Package a fork release and install it through HACS after static validation.

### Later

- First-class forms for every raw command payload.
- Credential, firmware, shell, migration, reboot, and shutdown commands. These
  are not router configuration and remain excluded from the generic surface.

## Risk controls

- No arbitrary command strings.
- No shell or credential-management commands.
- `dry_run` defaults to true.
- `confirm: true` and `dry_run: false` are both required for mutation.
- Network config execution also requires `expected_current_hash` from a fresh
  `admin_read` and refuses stale writes.
- Firewalla's `networkConfigImpact` runs before every network config execution.
- Live acceptance is read-only unless a reversible test object is created and
  removed with readback.

## Verification

1. Focused client, manager, and service tests.
2. `python -m ruff check .`
3. `python -m ruff format --check .`
4. `python -m mypy custom_components/firewalla_local`
5. `python -m pytest tests/ -v`
6. Home Assistant config check after deployment.
7. MCP capability and read-only command calls against Winterfell.
