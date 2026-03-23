# Supporting note: Phase 1 cutover map

## Purpose

This note executes Phase 1 of the Firewalla Local runtime buildout initiative.

It defines the concrete file map, package cutover strategy, manifest and translation impacts, test migration plan, and deletion criteria required before runtime implementation begins.

## Clean cutover decision

The runtime buildout will use a clean rename and replacement strategy.

Rules:

- do not preserve `custom_components/firewalla/` as a runtime compatibility package
- do not add import-forwarding wrappers between `firewalla` and `firewalla_local`
- do not keep duplicate test trees for both domains
- complete the package rename as a single implementation track, with removal of legacy paths in the same initiative

## Integration file map

Current scaffold to target mapping:

- `custom_components/firewalla/__init__.py` -> `custom_components/firewalla_local/__init__.py`
- `custom_components/firewalla/config_flow.py` -> `custom_components/firewalla_local/config_flow.py`
- `custom_components/firewalla/coordinator.py` -> `custom_components/firewalla_local/coordinator.py`
- `custom_components/firewalla/const.py` -> `custom_components/firewalla_local/const.py`
- `custom_components/firewalla/models.py` -> `custom_components/firewalla_local/models.py`
- `custom_components/firewalla/diagnostics.py` -> `custom_components/firewalla_local/diagnostics.py`
- `custom_components/firewalla/manifest.json` -> `custom_components/firewalla_local/manifest.json`
- `custom_components/firewalla/translations/en.json` -> `custom_components/firewalla_local/translations/en.json`

Legacy single-file API replacement:

- `custom_components/firewalla/api.py` -> replaced by `custom_components/firewalla_local/api/`

Required initial files under the new API boundary:

- `custom_components/firewalla_local/api/__init__.py`
- `custom_components/firewalla_local/api/client.py`
- `custom_components/firewalla_local/api/auth.py`
- `custom_components/firewalla_local/api/crypto.py`
- `custom_components/firewalla_local/api/exceptions.py`
- `custom_components/firewalla_local/api/models.py` when protocol-only structures justify it

Additional required file:

- `custom_components/firewalla_local/services.yaml`

## Service surface required by the cutover

The new package must include `custom_components/firewalla_local/services.yaml` from the first implementation pass.

Required initial service surface:

- `firewalla_local.pause_rule`

Expected service fields:

- rule target identifier
- duration string

## Manifest impact

The manifest update is part of the same cutover.

Required manifest changes:

- `domain` changes from `firewalla` to `firewalla_local`
- `name` changes to `Firewalla Local`
- `documentation` path should match the new repository identity
- `loggers` path must move to `custom_components.firewalla_local`
- dependency declarations must reflect `cryptography` when implementation lands

## Translation impact

Translation files move with the new domain.

Required translation changes:

- move `translations/en.json` to the `firewalla_local` package
- update config flow titles, descriptions, and service text to use `Firewalla Local`
- add service descriptions for timed pause behavior when service implementation begins

## Test migration impact

The test package layout must move in the same initiative.

Current to target mapping:

- `tests/components/firewalla/test_init.py` -> `tests/components/firewalla_local/test_init.py`
- `tests/components/firewalla/test_config_flow.py` -> `tests/components/firewalla_local/test_config_flow.py`

Additional target test files are expected during implementation:

- `tests/components/firewalla_local/test_options_flow.py`
- `tests/components/firewalla_local/test_diagnostics.py`
- `tests/components/firewalla_local/test_services.py`
- pure API tests if the repo chooses a separate test location for protocol-only modules

## Legacy path deletion criteria

The builder should remove legacy `firewalla` paths once these conditions are met:

- all imports in production code target `firewalla_local`
- manifest domain is `firewalla_local`
- config flow and test imports no longer reference `firewalla`
- translation and documentation paths reference the new domain and product name
- the old `api.py` file is fully replaced by the `api/` package

Delete at end of cutover:

- `custom_components/firewalla/`
- `tests/components/firewalla/`

This deletion is part of the accepted pristine-buildout rule, not optional cleanup.

## Builder implications

The first implementation pass should start from a single-path target:

- `custom_components/firewalla_local/`
- `tests/components/firewalla_local/`

All runtime work after the cutover should assume the legacy scaffold is gone.