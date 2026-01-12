# ABOUTME: Tests for repo_detection module.
# ABOUTME: Tests git repo detection, path config loading, and cwd resolution.

from __future__ import annotations

from pathlib import Path

import pytest


class TestLoadPathConfig:
    """Tests for load_path_config function."""

    def test_missing_file_returns_empty_config(self, tmp_path: Path) -> None:
        """load_path_config returns empty config when file doesn't exist."""
        from agent_taylor.repo_detection import load_path_config

        config = load_path_config(tmp_path / "nonexistent.toml")

        assert config.remap == {}
        assert config.ignore == set()

    def test_empty_file_returns_empty_config(self, tmp_path: Path) -> None:
        """load_path_config returns empty config for empty file."""
        from agent_taylor.repo_detection import load_path_config

        config_file = tmp_path / "empty.toml"
        config_file.write_text("")

        config = load_path_config(config_file)

        assert config.remap == {}
        assert config.ignore == set()

    def test_parses_remap_section(self, tmp_path: Path) -> None:
        """load_path_config correctly parses remap section."""
        from agent_taylor.repo_detection import load_path_config

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """\
[remap]
"/old/path/foo" = "/new/path/foo"
"/Users/juan/old" = "/Users/juan/new"
"""
        )

        config = load_path_config(config_file)

        assert config.remap == {
            "/old/path/foo": "/new/path/foo",
            "/Users/juan/old": "/Users/juan/new",
        }

    def test_parses_ignore_section(self, tmp_path: Path) -> None:
        """load_path_config correctly parses ignore section."""
        from agent_taylor.repo_detection import load_path_config

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """\
[ignore]
paths = ["/tmp", "/Users/juan/Downloads", "/var/folders"]
"""
        )

        config = load_path_config(config_file)

        assert config.ignore == {"/tmp", "/Users/juan/Downloads", "/var/folders"}

    def test_parses_both_sections(self, tmp_path: Path) -> None:
        """load_path_config parses both remap and ignore sections."""
        from agent_taylor.repo_detection import load_path_config

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """\
[remap]
"/old/repo" = "/new/repo"

[ignore]
paths = ["/tmp"]
"""
        )

        config = load_path_config(config_file)

        assert config.remap == {"/old/repo": "/new/repo"}
        assert config.ignore == {"/tmp"}

    def test_default_path_when_none_provided(self) -> None:
        """load_path_config uses default path when None provided."""
        from agent_taylor.repo_detection import load_path_config

        # Should not raise, just return empty config if default path doesn't exist
        config = load_path_config(None)

        assert config.remap == {}
        assert config.ignore == set()


class TestDetectGitRoot:
    """Tests for detect_git_root function."""

    def test_returns_repo_root_for_git_repo(self, git_repo: Path) -> None:
        """detect_git_root returns repo root for a git repo directory."""
        from agent_taylor.repo_detection import detect_git_root

        result = detect_git_root(git_repo)

        assert result == git_repo

    def test_returns_repo_root_from_subdirectory(self, git_repo: Path) -> None:
        """detect_git_root returns repo root when called from a subdirectory."""
        from agent_taylor.repo_detection import detect_git_root

        subdir = git_repo / "src" / "nested"
        subdir.mkdir(parents=True)

        result = detect_git_root(subdir)

        assert result == git_repo

    def test_returns_none_for_non_git_directory(self, non_git_dir: Path) -> None:
        """detect_git_root returns None for a non-git directory."""
        from agent_taylor.repo_detection import detect_git_root

        result = detect_git_root(non_git_dir)

        assert result is None

    def test_returns_none_for_nonexistent_path(self, tmp_path: Path) -> None:
        """detect_git_root returns None for a nonexistent path."""
        from agent_taylor.repo_detection import detect_git_root

        result = detect_git_root(tmp_path / "does_not_exist")

        assert result is None

    def test_handles_file_path_inside_repo(self, git_repo: Path) -> None:
        """detect_git_root works when given a file path inside a repo."""
        from agent_taylor.repo_detection import detect_git_root

        file_path = git_repo / "README.md"
        assert file_path.exists()

        result = detect_git_root(file_path)

        assert result == git_repo


class TestResolveCwdToRepo:
    """Tests for resolve_cwd_to_repo function."""

    def test_resolves_git_repo_path(self, git_repo: Path) -> None:
        """resolve_cwd_to_repo resolves a git repo path to its root."""
        from agent_taylor.repo_detection import PathConfig, resolve_cwd_to_repo

        config = PathConfig()
        cache: dict[str, str | None] = {}

        result = resolve_cwd_to_repo(str(git_repo), config, cache)

        assert result == str(git_repo)

    def test_returns_none_for_non_git_path(self, non_git_dir: Path) -> None:
        """resolve_cwd_to_repo returns None for non-git paths."""
        from agent_taylor.repo_detection import PathConfig, resolve_cwd_to_repo

        config = PathConfig()
        cache: dict[str, str | None] = {}

        result = resolve_cwd_to_repo(str(non_git_dir), config, cache)

        assert result is None

    def test_applies_remap_config(self, git_repo: Path) -> None:
        """resolve_cwd_to_repo applies path remapping from config."""
        from agent_taylor.repo_detection import PathConfig, resolve_cwd_to_repo

        old_path = "/old/nonexistent/path"
        config = PathConfig(remap={old_path: str(git_repo)}, ignore=set())
        cache: dict[str, str | None] = {}

        result = resolve_cwd_to_repo(old_path, config, cache)

        assert result == str(git_repo)

    def test_returns_none_for_ignored_path(self, git_repo: Path) -> None:
        """resolve_cwd_to_repo returns None for ignored paths."""
        from agent_taylor.repo_detection import PathConfig, resolve_cwd_to_repo

        config = PathConfig(remap={}, ignore={str(git_repo)})
        cache: dict[str, str | None] = {}

        result = resolve_cwd_to_repo(str(git_repo), config, cache)

        assert result is None

    def test_uses_cache_for_repeated_lookups(self, git_repo: Path) -> None:
        """resolve_cwd_to_repo uses cache and doesn't re-run git."""
        from agent_taylor.repo_detection import PathConfig, resolve_cwd_to_repo

        config = PathConfig()
        cache: dict[str, str | None] = {}

        # First call populates cache
        result1 = resolve_cwd_to_repo(str(git_repo), config, cache)
        assert str(git_repo) in cache

        # Modify cache to prove it's being used
        cache[str(git_repo)] = "/cached/value"

        result2 = resolve_cwd_to_repo(str(git_repo), config, cache)
        assert result2 == "/cached/value"

    def test_caches_none_results(self, non_git_dir: Path) -> None:
        """resolve_cwd_to_repo caches None results for non-git paths."""
        from agent_taylor.repo_detection import PathConfig, resolve_cwd_to_repo

        config = PathConfig()
        cache: dict[str, str | None] = {}

        result = resolve_cwd_to_repo(str(non_git_dir), config, cache)

        assert result is None
        assert str(non_git_dir) in cache
        assert cache[str(non_git_dir)] is None

    def test_ignore_with_prefix_match(self, git_repo: Path) -> None:
        """resolve_cwd_to_repo ignores paths that start with an ignored prefix."""
        from agent_taylor.repo_detection import PathConfig, resolve_cwd_to_repo

        # Ignore the parent directory
        parent = str(git_repo.parent)
        config = PathConfig(remap={}, ignore={parent})
        cache: dict[str, str | None] = {}

        result = resolve_cwd_to_repo(str(git_repo), config, cache)

        assert result is None


class TestCollectReposFromInteractions:
    """Tests for collect_repos_from_interactions function."""

    def test_collects_unique_repos(self, git_repo: Path) -> None:
        """collect_repos_from_interactions groups cwds by their repo root."""
        from agent_taylor.ai_hours import Interaction
        from agent_taylor.repo_detection import PathConfig, collect_repos_from_interactions

        subdir = git_repo / "src"
        subdir.mkdir()

        interactions = [
            Interaction(timestamp=1000.0, message_type="user", project=str(git_repo)),
            Interaction(timestamp=1001.0, message_type="assistant", project=str(git_repo)),
            Interaction(timestamp=1002.0, message_type="user", project=str(subdir)),
        ]
        config = PathConfig()

        result = collect_repos_from_interactions(interactions, config)

        # All three interactions should map to the same repo root
        assert len(result) == 1
        assert str(git_repo) in result
        assert set(result[str(git_repo)]) == {str(git_repo), str(subdir)}

    def test_handles_multiple_repos(self, tmp_path: Path) -> None:
        """collect_repos_from_interactions handles multiple distinct repos."""
        import subprocess
        from agent_taylor.ai_hours import Interaction
        from agent_taylor.repo_detection import PathConfig, collect_repos_from_interactions

        # Create two separate git repos
        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"
        for repo in [repo1, repo2]:
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=repo, check=True, capture_output=True
            )
            (repo / "file.txt").write_text("content")
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=repo, check=True, capture_output=True
            )

        interactions = [
            Interaction(timestamp=1000.0, message_type="user", project=str(repo1)),
            Interaction(timestamp=1001.0, message_type="user", project=str(repo2)),
        ]
        config = PathConfig()

        result = collect_repos_from_interactions(interactions, config)

        assert len(result) == 2
        assert str(repo1) in result
        assert str(repo2) in result

    def test_ignores_non_git_paths(self, git_repo: Path, non_git_dir: Path) -> None:
        """collect_repos_from_interactions ignores paths that aren't git repos."""
        from agent_taylor.ai_hours import Interaction
        from agent_taylor.repo_detection import PathConfig, collect_repos_from_interactions

        interactions = [
            Interaction(timestamp=1000.0, message_type="user", project=str(git_repo)),
            Interaction(timestamp=1001.0, message_type="user", project=str(non_git_dir)),
        ]
        config = PathConfig()

        result = collect_repos_from_interactions(interactions, config)

        assert len(result) == 1
        assert str(git_repo) in result

    def test_applies_config_ignore(self, git_repo: Path) -> None:
        """collect_repos_from_interactions respects ignore config."""
        from agent_taylor.ai_hours import Interaction
        from agent_taylor.repo_detection import PathConfig, collect_repos_from_interactions

        interactions = [
            Interaction(timestamp=1000.0, message_type="user", project=str(git_repo)),
        ]
        config = PathConfig(ignore={str(git_repo)})

        result = collect_repos_from_interactions(interactions, config)

        assert len(result) == 0

    def test_empty_interactions(self) -> None:
        """collect_repos_from_interactions handles empty input."""
        from agent_taylor.repo_detection import PathConfig, collect_repos_from_interactions

        interactions: list = []
        config = PathConfig()

        result = collect_repos_from_interactions(interactions, config)

        assert result == {}
