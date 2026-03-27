# Firewalla Local release checklist

## Purpose

Use this checklist before publishing a tagged release or promoting the next
release candidate.

## 1) Version and metadata consistency

- [ ] `custom_components/firewalla_local/manifest.json` has the intended release version.
- [ ] `pyproject.toml` matches the same version.
- [ ] `hacs.json` still matches the supported Home Assistant and HACS contract.
- [ ] `manifest.json` still includes the correct documentation and issue tracker URLs.

## 2) Quality gates

Run and pass:

```bash
bash ./utils/quick_lint.sh
python -m mypy custom_components/firewalla_local
python -m pytest tests/ -v
```

Checklist:

- [ ] No unresolved lint or formatting drift remains.
- [ ] No unresolved type errors remain in `custom_components/firewalla_local`.
- [ ] No failing tests remain in `tests/`.
- [ ] No debug-only artifacts or temporary development changes remain.

## 3) GitHub validation surfaces

- [ ] `.github/workflows/lint-validation.yaml` still reflects the repository-standard Python validation commands.
- [ ] `.github/workflows/validate.yaml` still runs HACS validation and hassfest.
- [ ] The HACS workflow still ignores `brands` intentionally because Home Assistant 2026.3 no longer accepts custom integration branding, while this repository still keeps the brand assets staged correctly for repository and HACS guidance.

## 4) Documentation and public surfaces

- [ ] `README.md` still matches the shipped feature set and support posture.
- [ ] `docs/USER_GUIDE.md` still matches the actual setup, removal, and runtime behavior.
- [ ] `CONTRIBUTING.md`, `SUPPORT.md`, and `SECURITY.md` still reflect the real repository process.
- [ ] Any user-visible change has a short release summary prepared.

## 5) HACS and Home Assistant posture

- [ ] The repository still contains only one integration under `custom_components/`.
- [ ] The integration package still includes the files HACS expects.
- [ ] The repository still passes HACS structure expectations apart from the intentional `brands` bypass.
- [ ] The current release posture remains compatible with Home Assistant 2026.3 or newer.

## 6) Runtime smoke

- [ ] Install or upgrade through the documented HACS path.
- [ ] Confirm the config flow still completes successfully against a real Firewalla box.
- [ ] Confirm at least one runtime refresh succeeds after setup.
- [ ] Confirm at least one representative service action still works.

## 7) Release publication

- [ ] Use a plain SemVer Git tag matching `manifest.json`, such as `1.0.0`.
- [ ] Publish a short release summary in the GitHub release body.
- [ ] Do not rely on a separate generated changelog system for the first release line.

## 8) Rollback readiness

- [ ] Known risks and any deferred issues are documented before publishing.
- [ ] If the release exposes a blocking setup or packaging failure, prepare a patch release instead of silently rewriting the tag.