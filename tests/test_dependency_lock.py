"""Guards for reproducible production dependency installation."""

import json
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from jobs.generate_sbom import build_sbom, rendered_sbom


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _requirements(path: Path) -> list[Requirement]:
    values = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith(("#", "-r ")):
            values.append(Requirement(line))
    return values


def _exact_version(requirement: Requirement) -> str:
    specs = list(requirement.specifier)
    assert len(specs) == 1
    assert specs[0].operator == "=="
    assert "*" not in specs[0].version
    assert requirement.url is None
    assert requirement.marker is None
    return specs[0].version


def test_production_lock_is_exact_and_contains_every_direct_requirement():
    direct = _requirements(PROJECT_ROOT / "requirements.txt")
    locked = _requirements(PROJECT_ROOT / "requirements.lock")

    locked_versions = {}
    for requirement in locked:
        name = canonicalize_name(requirement.name)
        assert name not in locked_versions, f"duplicate locked package: {name}"
        locked_versions[name] = _exact_version(requirement)

    assert len(locked_versions) >= len(direct)
    for requirement in direct:
        name = canonicalize_name(requirement.name)
        assert locked_versions[name] == _exact_version(requirement)


def test_production_lock_contains_every_active_transitive_requirement():
    locked = _requirements(PROJECT_ROOT / "requirements.lock")
    locked_versions = {
        canonicalize_name(requirement.name): _exact_version(requirement)
        for requirement in locked
    }
    production_environment = default_environment()
    production_environment.update(
        {
            "os_name": "posix",
            "platform_system": "Linux",
            "python_full_version": "3.11.15",
            "python_version": "3.11",
            "sys_platform": "linux",
        }
    )

    for package_name in sorted(locked_versions):
        distribution = metadata.distribution(package_name)
        for raw_requirement in distribution.requires or ():
            requirement = Requirement(raw_requirement)
            if requirement.marker and not requirement.marker.evaluate(
                production_environment
            ):
                continue

            dependency_name = canonicalize_name(requirement.name)
            assert dependency_name in locked_versions, (
                f"{package_name} requires unlocked dependency "
                f"{dependency_name}"
            )
            assert requirement.specifier.contains(
                locked_versions[dependency_name],
                prereleases=True,
            ), (
                f"{package_name} requires {dependency_name}"
                f"{requirement.specifier}, lock has "
                f"{locked_versions[dependency_name]}"
            )


def test_production_and_ci_install_only_the_lock():
    blueprint = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert blueprint.count("-r requirements.lock") == 5
    assert "-r requirements.txt" not in blueprint
    assert "-r requirements.lock" in workflow
    assert "python -m jobs.generate_sbom --check" in workflow


def test_cyclonedx_sbom_exactly_matches_the_production_lock():
    lock_path = PROJECT_ROOT / "requirements.lock"
    sbom_path = PROJECT_ROOT / "sbom.cdx.json"
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    generated = build_sbom(lock_path)

    assert sbom == generated
    assert sbom_path.read_text(encoding="utf-8") == rendered_sbom(lock_path)
    assert len(sbom["components"]) == len(_requirements(lock_path))
