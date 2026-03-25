"""Bundle Firewalla Local source and docs into upload-friendly text files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

CURRENT_DATE = date.today().isoformat()

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
EXPORT_DIR = SCRIPT_DIR / "exports"

SKIP_DIR_NAMES = {
    "__pycache__",
    "exports",
    "build",
    "dist",
}

SKIP_DIR_PREFIXES = (".",)


@dataclass(frozen=True, slots=True)
class BundleSpec:
    """Describe one output bundle."""

    output_filename: str
    sources: tuple[str, ...]
    allowed_extensions: tuple[str, ...]


def _should_skip_dir(directory_name: str) -> bool:
    """Return whether one directory should be skipped while walking."""
    return directory_name in SKIP_DIR_NAMES or directory_name.startswith(
        SKIP_DIR_PREFIXES
    )


def _iter_source_files(
    source_path: Path, allowed_extensions: tuple[str, ...]
) -> list[Path]:
    """Return sorted source files for one bundle input path."""
    if source_path.is_file():
        return [source_path] if source_path.suffix in allowed_extensions else []

    collected: list[Path] = []
    for root_str, dirs, files in os.walk(source_path):
        root = Path(root_str)
        dirs[:] = [directory for directory in dirs if not _should_skip_dir(directory)]

        for filename in sorted(files):
            file_path = root / filename
            if file_path.suffix not in allowed_extensions:
                continue
            collected.append(file_path)

    return sorted(collected)


def _write_file_contents(outfile: Path, source_files: list[Path]) -> None:
    """Write one bundle output file from a set of source files."""
    with outfile.open("w", encoding="utf-8") as handle:
        for file_path in source_files:
            rel_path = file_path.relative_to(REPO_ROOT)
            handle.write(f"\n\n{'=' * 80}\n")
            handle.write(f"FILE PATH: {rel_path}\n")
            handle.write(f"{'=' * 80}\n\n")
            try:
                handle.write(file_path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                handle.write("[Skipped: non-UTF-8 file]\n")


def bundle_repo(spec: BundleSpec) -> None:
    """Build one dated bundle output file."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    output_path = Path(spec.output_filename)
    dated_output = EXPORT_DIR / (
        f"{output_path.stem}_{CURRENT_DATE}{output_path.suffix}"
    )

    source_files: list[Path] = []
    for source in spec.sources:
        source_files.extend(
            _iter_source_files(REPO_ROOT / source, spec.allowed_extensions)
        )

    print(f"Bundling {dated_output.name}")
    _write_file_contents(dated_output, source_files)


if __name__ == "__main__":
    bundle_specs = (
        BundleSpec(
            output_filename="bundle_firewalla_runtime.txt",
            sources=(
                "custom_components/firewalla_local",
                "utils",
                "pyproject.toml",
                "hacs.json",
                "AGENTS.md",
            ),
            allowed_extensions=(".py", ".json", ".yaml", ".yml", ".toml", ".md"),
        ),
        BundleSpec(
            output_filename="bundle_firewalla_docs.txt",
            sources=(
                "README.md",
                "SECURITY.md",
                "docs",
                "plans",
            ),
            allowed_extensions=(".md", ".yaml", ".yml", ".json"),
        ),
        BundleSpec(
            output_filename="bundle_firewalla_tests.txt",
            sources=("tests",),
            allowed_extensions=(".py", ".json", ".yaml", ".yml", ".md"),
        ),
    )

    for bundle_spec in bundle_specs:
        bundle_repo(bundle_spec)

    print(f"Wrote bundles to {EXPORT_DIR.relative_to(REPO_ROOT)}")
