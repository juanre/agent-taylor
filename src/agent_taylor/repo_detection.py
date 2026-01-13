# ABOUTME: Git repository detection and path configuration.
# ABOUTME: Resolves cwd paths from AI logs to their git repo roots.

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .ai_hours import Interaction


@dataclass(frozen=True)
class PathConfig:
    """Configuration for path remapping and ignoring."""

    remap: dict[str, str] = field(default_factory=dict)
    ignore: set[str] = field(default_factory=set)
    ignore_projects: set[str] = field(default_factory=set)
    log_bundle: Optional[Path] = None


def _default_config_path() -> Path:
    """Return the default path config location."""
    return Path.home() / ".config" / "agent-taylor" / "paths.toml"


def load_path_config(config_path: Optional[Path] = None) -> PathConfig:
    """Load path remapping configuration from TOML file.

    Args:
        config_path: Path to config file. If None, uses default location
                     (~/.config/agent-taylor/paths.toml).

    Returns:
        PathConfig with remap dict and ignore set.
        Returns empty config if file doesn't exist.
    """
    if config_path is None:
        config_path = _default_config_path()

    if not config_path.exists():
        return PathConfig()

    try:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError:
        return PathConfig()

    remap = data.get("remap", {})
    ignore_list = data.get("ignore", {}).get("paths", [])
    ignore_projects_list = data.get("ignore", {}).get("projects", [])

    log_bundle_raw = data.get("log_bundle")
    if log_bundle_raw is not None and not isinstance(log_bundle_raw, str):
        return PathConfig()
    log_bundle = Path(log_bundle_raw).expanduser() if log_bundle_raw else None

    return PathConfig(
        remap=dict(remap),
        ignore=set(ignore_list),
        ignore_projects=set(ignore_projects_list),
        log_bundle=log_bundle,
    )


def detect_git_root(path: Path) -> Optional[Path]:
    """Detect the git repository root for a given path.

    Runs `git rev-parse --show-toplevel` to find the repo root.

    Args:
        path: A path that may be inside a git repository. Can be a
              directory or file path.

    Returns:
        Path to the git repository root, or None if:
        - The path doesn't exist
        - The path is not inside a git repository
    """
    if not path.exists():
        return None

    # If path is a file, use its parent directory
    work_dir = path if path.is_dir() else path.parent

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None

        repo_root = result.stdout.strip()
        if repo_root:
            return Path(repo_root)
        return None

    except (OSError, subprocess.SubprocessError):
        return None


def _is_ignored(cwd: str, ignore: set[str]) -> bool:
    """Check if a cwd path should be ignored.

    Returns True if cwd exactly matches or starts with any ignored path.
    """
    for ignored in ignore:
        if cwd == ignored or cwd.startswith(ignored + "/"):
            return True
    return False


def resolve_cwd_to_repo(
    cwd: str,
    config: PathConfig,
    cache: dict[str, str | None],
) -> str | None:
    """Resolve a cwd path to its git repository root.

    Applies path remapping and ignore rules from config, uses caching.

    Args:
        cwd: The working directory path from an AI log interaction.
        config: PathConfig with remap and ignore rules.
        cache: Dict to cache lookup results (mutated by this function).

    Returns:
        The git repository root path as a string, or None if:
        - The cwd is in the ignore list
        - The cwd (after remapping) is not inside a git repo
    """
    # Check ignore list first
    if _is_ignored(cwd, config.ignore):
        return None

    # Apply remapping if present
    resolved_cwd = config.remap.get(cwd, cwd)

    # Check cache
    if resolved_cwd in cache:
        return cache[resolved_cwd]

    # Detect git root
    repo_root = detect_git_root(Path(resolved_cwd))

    # Cache and return
    result = str(repo_root) if repo_root else None
    cache[resolved_cwd] = result
    return result


def collect_repos_from_interactions(
    interactions: list["Interaction"],
    config: PathConfig,
) -> dict[str, list[str]]:
    """Collect unique git repositories from AI log interactions.

    Groups interactions by their git repository root.

    Args:
        interactions: List of Interaction objects from AI logs.
        config: PathConfig with remap and ignore rules.

    Returns:
        Dict mapping repo_root -> list of unique cwds that map to that repo.
        Repos that couldn't be detected (non-git paths, ignored paths) are
        not included in the result.
    """
    cache: dict[str, str | None] = {}
    result: dict[str, set[str]] = {}

    for interaction in interactions:
        cwd = interaction.project
        repo_root = resolve_cwd_to_repo(cwd, config, cache)

        if repo_root is not None:
            if repo_root not in result:
                result[repo_root] = set()
            result[repo_root].add(cwd)

    # Convert sets to lists for the return type
    return {repo: list(cwds) for repo, cwds in result.items()}
