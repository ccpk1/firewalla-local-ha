# Maintaining the fork

This fork keeps `ccpk1/firewalla-local-ha` as its upstream source and adds the
guarded local admin API used by Home Assistant and MCP clients.

## Sync an upstream release

```bash
git remote add upstream git@github.com:ccpk1/firewalla-local-ha.git
git fetch origin upstream --tags
git switch main
git pull --ff-only origin main
git switch -c change/sync-upstream-YYYYMMDD
git merge --no-ff upstream/main
```

Resolve conflicts by preserving:

- the fork owner and HACS URLs
- `FirewallaAdminManager` and the four admin services
- dry-run, confirmation, redaction, hash, impact, and rollback safeguards
- merge-patch handling that preserves redacted network configuration fields
- the explicit exclusion of shell, credential, firmware, migration, reboot,
  and shutdown commands

Do not add a newly discovered command to the allowlist until its live Firewalla
handler, message type, target, input shape, and effect are confirmed.

## Validate the merge

```bash
PATH="$PWD/.venv/bin:$PATH" bash ./utils/quick_lint.sh
.venv/bin/python -m mypy custom_components/firewalla_local
.venv/bin/python -m pytest tests/ -q
```

Also compare the live `getHandler`, `setHandler`, and `cmdHandler` cases in
`/home/pi/firewalla/controllers/netbot.js` with the allowlists in
`managers/admin_manager.py`. A Firewalla firmware update can change this private
local protocol independently of the Home Assistant repository.

## Release and deploy

1. Bump the version in `pyproject.toml` and `manifest.json`.
2. Push the branch, review it, and merge it into `main`.
3. Create a matching GitHub release tag.
4. In HACS, update `erabti/firewalla-local-ha` to that tag.
5. Run the Home Assistant configuration check, then restart Home Assistant.
6. Verify the config entry is loaded and run:
   - `get_admin_capabilities`
   - one small `admin_read`
   - one `admin_execute` dry run
7. Check Home Assistant logs for `firewalla_local` errors or new warnings.

If acceptance fails, reinstall the prior fork release through HACS and restart
Home Assistant. For a damaged component directory, restore the component-only
archive recorded by the Winterfell runbook.
