"""Generate a deterministic CycloneDX inventory from ``requirements.lock``.

The production lock already contains the fully resolved runtime dependency
set. This command intentionally does not contact package indexes or a
vulnerability service; CI performs that separate, time-sensitive audit.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = PROJECT_ROOT / "requirements.lock"
DEFAULT_OUTPUT = PROJECT_ROOT / "sbom.cdx.json"
RELEASE_VERSION = "2026.07.29-rc1"
_EXACT_REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s;]+)$"
)


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def locked_components(lock_path: Path) -> list[dict[str, str]]:
    """Return one sorted CycloneDX component per exact lock entry."""

    components: dict[str, dict[str, str]] = {}
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _EXACT_REQUIREMENT.fullmatch(line)
        if not match:
            raise ValueError(f"non_exact_lock_entry:{line}")

        name = _canonical_name(match.group("name"))
        version = match.group("version")
        if name in components:
            raise ValueError(f"duplicate_lock_entry:{name}")
        encoded_name = quote(name, safe="-._~")
        encoded_version = quote(version, safe="-._~+")
        purl = f"pkg:pypi/{encoded_name}@{encoded_version}"
        components[name] = {
            "bom-ref": purl,
            "name": name,
            "purl": purl,
            "type": "library",
            "version": version,
        }
    if not components:
        raise ValueError("empty_lock")
    return [components[name] for name in sorted(components)]


def build_sbom(lock_path: Path = DEFAULT_LOCK) -> dict[str, object]:
    """Build a deterministic CycloneDX 1.5 component inventory."""

    components = locked_components(lock_path)
    app_ref = f"pkg:generic/nyaysetu-bot@{RELEASE_VERSION}"
    return {
        "$schema": "https://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "bom-ref": app_ref,
                "name": "nyaysetu-bot",
                "type": "application",
                "version": RELEASE_VERSION,
            },
            "properties": [
                {
                    "name": "nyaysetu:dependency-source",
                    "value": "requirements.lock",
                }
            ],
        },
        "components": components,
        "dependencies": [
            {
                "ref": app_ref,
                "dependsOn": [
                    component["bom-ref"] for component in components
                ],
            },
            *[
                {"ref": component["bom-ref"], "dependsOn": []}
                for component in components
            ],
        ],
    }


def rendered_sbom(lock_path: Path = DEFAULT_LOCK) -> str:
    return json.dumps(
        build_sbom(lock_path),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or verify the offline production SBOM."
    )
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero instead of rewriting a stale or missing SBOM.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    expected = rendered_sbom(args.lock)
    if args.check:
        try:
            actual = args.output.read_text(encoding="utf-8")
        except OSError:
            return 1
        return 0 if actual == expected else 1

    args.output.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
