"""Tests for the release packaging contract.

`hacs.json` sets `zip_release` with a `filename`, which makes HACS download a
named asset from the release instead of the tag's source archive. Two things can
then go wrong silently, and neither is caught by any runtime test because
neither involves the integration's code:

- the filename in `hacs.json` and the archive the workflow uploads disagree, so
  every install fails with "not completed";
- the archive is built with a wrapping directory, so HACS extracts the
  integration one level too deep and Home Assistant cannot load it.

Both are cheap to assert here and expensive to discover from a user report.
"""

from __future__ import annotations

import json
import re
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
INTEGRATION_DIR = REPO_ROOT / "custom_components" / "firewalla_local"
HACS_JSON_PATH = REPO_ROOT / "hacs.json"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release.yaml"

# Files HACS and Home Assistant need at the archive root for an integration to
# install and load. The rest of the package can move; these cannot.
REQUIRED_ARCHIVE_MEMBERS = ("manifest.json", "__init__.py", "translations/en.json")


def _hacs_manifest() -> dict[str, object]:
    """Return `hacs.json` parsed."""
    return json.loads(HACS_JSON_PATH.read_text(encoding="utf-8"))


def _manifest_version() -> str:
    """Return the integration version Home Assistant reports."""
    manifest = json.loads(
        (INTEGRATION_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    return manifest["version"]


def test_hacs_zip_release_declares_a_filename() -> None:
    """`zip_release` is meaningless to HACS without `filename`."""
    manifest = _hacs_manifest()

    assert manifest.get("zip_release") is True, (
        "zip_release must be enabled for HACS to count release asset downloads"
    )
    filename = manifest.get("filename")
    assert isinstance(filename, str) and filename.endswith(".zip"), (
        "zip_release requires a `filename` ending in .zip"
    )


def test_the_release_workflow_uploads_the_declared_filename() -> None:
    """A mismatch here breaks every install, not just the download counter."""
    filename = _hacs_manifest()["filename"]
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert workflow.count(str(filename)) >= 2, (
        f"{filename} must be both built and uploaded by the release workflow"
    )


def test_the_release_workflow_runs_on_a_published_release() -> None:
    """Drafting must not be enough; the asset is attached on publish."""
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "release:" in workflow
    assert "published" in workflow, "the workflow must trigger on release published"


def test_the_release_workflow_zips_from_inside_the_integration() -> None:
    """HACS extracts the archive into `custom_components/`, so it must not nest.

    Asserted against the workflow because the mistake is invisible in the built
    archive until someone installs it.
    """
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert re.search(r"cd custom_components/firewalla_local\b", workflow), (
        "the zip step must run inside the integration directory"
    )


def test_manifest_version_is_a_plain_semver_tag() -> None:
    """HACS compares the release tag to this value, so it must be tag-shaped."""
    version = _manifest_version()

    assert re.fullmatch(r"\d+\.\d+\.\d+", version), (
        f"manifest version {version!r} is not a plain SemVer tag"
    )


def test_pyproject_version_matches_the_manifest() -> None:
    """Two version sources that disagree produce two different releases."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)

    assert match is not None
    assert match.group(1) == _manifest_version()


@pytest.fixture(scope="module")
def packaged_archive(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the archive the way the release workflow does."""
    target = tmp_path_factory.mktemp("release") / "firewalla_local.zip"
    subprocess.run(
        [
            "zip",
            "-qr",
            str(target),
            ".",
            "-x",
            "*/__pycache__/*",
            "*.pyc",
        ],
        cwd=INTEGRATION_DIR,
        check=True,
    )
    return target


def test_the_archive_holds_the_integration_at_its_root(
    packaged_archive: Path,
) -> None:
    """The packaged layout must be what HACS extracts into `custom_components/`."""
    with zipfile.ZipFile(packaged_archive) as archive:
        names = archive.namelist()

    for required in REQUIRED_ARCHIVE_MEMBERS:
        assert required in names, f"{required} is missing from the archive root"

    assert not any(name.startswith("custom_components/") for name in names), (
        "the archive must not contain a custom_components/ wrapper directory"
    )


def test_the_archive_carries_the_shipped_version(packaged_archive: Path) -> None:
    """A stale archive would install a version the release does not advertise."""
    with zipfile.ZipFile(packaged_archive) as archive:
        manifest = json.loads(archive.read("manifest.json"))

    assert manifest["version"] == _manifest_version()
