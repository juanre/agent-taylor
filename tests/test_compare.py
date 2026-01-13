# ABOUTME: Tests for the compare command functionality.
# ABOUTME: Tests commit lookup, session classification, and aggregation.

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest


class TestGetCommitsInWindow:
    """Tests for get_commits_in_window function."""

    def test_returns_empty_for_window_before_commits(self, git_repo: Path) -> None:
        """get_commits_in_window returns empty list when window is before commits."""
        from agent_taylor.compare import get_commits_in_window

        # Use a window far in the past
        result = get_commits_in_window(
            repo=git_repo,
            start_ts=0,
            end_ts=1000,
            author=None,
        )

        assert result == []

    def test_returns_commits_in_window(self, git_repo: Path) -> None:
        """get_commits_in_window returns commits within the time window."""
        from agent_taylor.compare import get_commits_in_window

        # Create a file and commit
        (git_repo / "file.txt").write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        now = time.time()
        result = get_commits_in_window(
            repo=git_repo,
            start_ts=now - 60,
            end_ts=now + 60,
            author=None,
        )

        # Should have 2 commits: initial + file.txt
        assert len(result) == 2
        assert all(r["delta"] > 0 for r in result)

    def test_filters_by_author(self, git_repo: Path) -> None:
        """get_commits_in_window filters commits by author regex."""
        from agent_taylor.compare import get_commits_in_window

        # Create a file and commit
        (git_repo / "file.txt").write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        now = time.time()
        # Filter by non-matching author
        result = get_commits_in_window(
            repo=git_repo,
            start_ts=now - 60,
            end_ts=now + 60,
            author="NonExistentAuthor",
        )

        assert result == []

    def test_excludes_commits_outside_window(self, git_repo: Path) -> None:
        """get_commits_in_window excludes commits outside the time window."""
        from agent_taylor.compare import get_commits_in_window

        # Create a file and commit
        (git_repo / "file.txt").write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        now = time.time()
        # Window in the past
        result = get_commits_in_window(
            repo=git_repo,
            start_ts=now - 7200,
            end_ts=now - 3600,
            author=None,
        )

        assert result == []


class TestClassifySession:
    """Tests for classify_session function."""

    def test_classifies_session_by_configuration(self) -> None:
        """classify_session returns correct configuration for session."""
        from agent_taylor.compare import classify_session

        # Session in June, beads adopted in May, no beadhub
        result = classify_session(
            session_start_date="2025-06-15",
            beads_date="2025-05-01",
            beadhub_date=None,
        )

        assert result == "beads"

    def test_classifies_session_before_any_adoption(self) -> None:
        """classify_session returns 'none' for session before adoption."""
        from agent_taylor.compare import classify_session

        result = classify_session(
            session_start_date="2025-04-15",
            beads_date="2025-05-01",
            beadhub_date=None,
        )

        assert result == "none"

    def test_classifies_session_with_beadhub(self) -> None:
        """classify_session returns 'beads+beadhub' after beadhub adoption."""
        from agent_taylor.compare import classify_session

        result = classify_session(
            session_start_date="2025-10-15",
            beads_date="2025-05-01",
            beadhub_date="2025-06-01",
        )

        assert result == "beads+beadhub"


class TestAggregateByConfiguration:
    """Tests for aggregate_by_configuration function."""

    def test_aggregates_metrics_by_configuration(self) -> None:
        """aggregate_by_configuration sums metrics per configuration."""
        from agent_taylor.compare import aggregate_by_configuration

        session_metrics = [
            {"configuration": "none", "hours": 1.0, "commits": 2, "delta": 100},
            {"configuration": "none", "hours": 0.5, "commits": 1, "delta": 50},
            {"configuration": "beads", "hours": 2.0, "commits": 5, "delta": 300},
        ]

        result = aggregate_by_configuration(session_metrics)

        assert result["none"]["hours"] == 1.5
        assert result["none"]["commits"] == 3
        assert result["none"]["delta"] == 150
        assert result["beads"]["hours"] == 2.0
        assert result["beads"]["commits"] == 5
        assert result["beads"]["delta"] == 300

    def test_computes_rates(self) -> None:
        """aggregate_by_configuration computes delta/hour and commits/hour."""
        from agent_taylor.compare import aggregate_by_configuration

        session_metrics = [
            {"configuration": "beads", "hours": 2.0, "commits": 4, "delta": 200},
        ]

        result = aggregate_by_configuration(session_metrics)

        assert result["beads"]["delta_per_hour"] == 100.0
        assert result["beads"]["commits_per_hour"] == 2.0

    def test_handles_zero_hours(self) -> None:
        """aggregate_by_configuration handles zero hours gracefully."""
        from agent_taylor.compare import aggregate_by_configuration

        session_metrics = [
            {"configuration": "beads", "hours": 0.0, "commits": 0, "delta": 0},
        ]

        result = aggregate_by_configuration(session_metrics)

        assert result["beads"]["delta_per_hour"] == 0.0
        assert result["beads"]["commits_per_hour"] == 0.0

    def test_initializes_all_configurations(self) -> None:
        """aggregate_by_configuration includes all three configurations."""
        from agent_taylor.compare import aggregate_by_configuration

        session_metrics = [
            {"configuration": "beads", "hours": 1.0, "commits": 1, "delta": 100},
        ]

        result = aggregate_by_configuration(session_metrics)

        assert "none" in result
        assert "beads" in result
        assert "beads+beadhub" in result


class TestCompareArgParsing:
    """Tests for compare command argument parsing."""

    def test_requires_author_flag(self) -> None:
        """compare command requires --author flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["compare"])

    def test_accepts_author_flag(self) -> None:
        """compare command accepts --author flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["compare", "--author", "Juan"])

        assert ns.author == "Juan"
        assert ns.cmd == "compare"

    def test_accepts_verbose_flag(self) -> None:
        """compare command accepts --verbose flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["compare", "--author", "Juan", "--verbose"])

        assert ns.verbose is True

    def test_accepts_history_flag(self) -> None:
        """compare command accepts --history flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["compare", "--author", "Juan", "--history"])

        assert ns.history is True

    def test_accepts_log_bundle_flag(self) -> None:
        """compare command accepts --log-bundle flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args([
            "compare", "--author", "Juan",
            "--log-bundle", "~/Documents/agent-logs"
        ])

        assert ns.log_bundle == "~/Documents/agent-logs"

    def test_log_bundle_defaults_to_none(self) -> None:
        """--log-bundle defaults to None when not specified."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["compare", "--author", "Juan"])

        assert ns.log_bundle is None


class TestLogBundleEnvVar:
    """Tests for AGENT_TAYLOR_LOG_BUNDLE environment variable."""

    def test_env_var_used_when_no_cli_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variable is used when --log-bundle not specified."""
        from agent_taylor.cli import _resolve_log_bundle

        bundle_path = str(tmp_path / "agent-logs")
        monkeypatch.setenv("AGENT_TAYLOR_LOG_BUNDLE", bundle_path)

        result = _resolve_log_bundle(cli_bundle=None)

        assert result == Path(bundle_path)

    def test_cli_flag_overrides_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI --log-bundle flag takes priority over environment variable."""
        from agent_taylor.cli import _resolve_log_bundle

        env_path = str(tmp_path / "env-logs")
        cli_path = str(tmp_path / "cli-logs")
        monkeypatch.setenv("AGENT_TAYLOR_LOG_BUNDLE", env_path)

        result = _resolve_log_bundle(cli_bundle=cli_path)

        assert result == Path(cli_path).expanduser()

    def test_returns_none_when_neither_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when neither CLI nor env var is set."""
        from agent_taylor.cli import _resolve_log_bundle

        monkeypatch.delenv("AGENT_TAYLOR_LOG_BUNDLE", raising=False)

        result = _resolve_log_bundle(cli_bundle=None)

        assert result is None

    def test_expands_tilde_in_paths(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Paths with ~ are expanded."""
        from agent_taylor.cli import _resolve_log_bundle

        monkeypatch.delenv("AGENT_TAYLOR_LOG_BUNDLE", raising=False)
        result = _resolve_log_bundle(cli_bundle="~/Documents/agent-logs")

        assert result == Path.home() / "Documents" / "agent-logs"

    def test_env_var_tilde_is_expanded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variable paths with ~ are expanded."""
        from agent_taylor.cli import _resolve_log_bundle

        monkeypatch.setenv("AGENT_TAYLOR_LOG_BUNDLE", "~/Documents/agent-logs")

        result = _resolve_log_bundle(cli_bundle=None)

        assert result == Path.home() / "Documents" / "agent-logs"

    def test_empty_string_env_var_treated_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty string env var is treated as if unset."""
        from agent_taylor.cli import _resolve_log_bundle

        monkeypatch.setenv("AGENT_TAYLOR_LOG_BUNDLE", "")

        result = _resolve_log_bundle(cli_bundle=None)

        assert result is None

    def test_whitespace_only_env_var_treated_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Whitespace-only env var is treated as if unset."""
        from agent_taylor.cli import _resolve_log_bundle

        monkeypatch.setenv("AGENT_TAYLOR_LOG_BUNDLE", "   ")

        result = _resolve_log_bundle(cli_bundle=None)

        assert result is None


class TestLogBundleFromConfig:
    """Tests for log_bundle from config file in _cmd_compare."""

    def test_uses_config_log_bundle_when_no_cli_or_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """_cmd_compare uses config.log_bundle when CLI and env var not set."""
        import argparse
        from agent_taylor.cli import _cmd_compare

        # Clear env var
        monkeypatch.delenv("AGENT_TAYLOR_LOG_BUNDLE", raising=False)

        # Create bundle and config
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        config_file = tmp_path / "config.toml"
        config_file.write_text(f'log_bundle = "{bundle}"')

        ns = argparse.Namespace(
            config=str(config_file),
            log_bundle=None,  # No CLI flag
            claude_dir=None,
            codex_dir=None,
            author="Test",
            verbose=False,
            history=False,
        )

        # Will fail with "No interactions" but that proves it used the bundle
        result = _cmd_compare(ns)

        assert result == 1
        captured = capsys.readouterr()
        assert "No interactions found" in captured.err

    def test_cli_overrides_config_log_bundle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """CLI --log-bundle takes priority over config file."""
        import argparse
        from agent_taylor.cli import _cmd_compare

        # Clear env var
        monkeypatch.delenv("AGENT_TAYLOR_LOG_BUNDLE", raising=False)

        # Create bundles
        cli_bundle = tmp_path / "cli-bundle"
        cli_bundle.mkdir()
        config_bundle = tmp_path / "config-bundle"
        config_bundle.mkdir()

        # Config points to config_bundle
        config_file = tmp_path / "config.toml"
        config_file.write_text(f'log_bundle = "{config_bundle}"')

        ns = argparse.Namespace(
            config=str(config_file),
            log_bundle=str(cli_bundle),  # CLI flag set
            claude_dir=None,
            codex_dir=None,
            author="Test",
            verbose=False,
            history=False,
        )

        _cmd_compare(ns)

        # It would error "does not exist" if it tried the wrong bundle
        # Both exist, so it proceeds to "No interactions found"
        captured = capsys.readouterr()
        assert "No interactions found" in captured.err

    def test_env_var_overrides_config_log_bundle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Environment variable takes priority over config file."""
        import argparse
        from agent_taylor.cli import _cmd_compare

        # Create bundles
        env_bundle = tmp_path / "env-bundle"
        env_bundle.mkdir()
        config_bundle = tmp_path / "config-bundle"
        config_bundle.mkdir()

        # Set env var to env_bundle
        monkeypatch.setenv("AGENT_TAYLOR_LOG_BUNDLE", str(env_bundle))

        # Config points to config_bundle
        config_file = tmp_path / "config.toml"
        config_file.write_text(f'log_bundle = "{config_bundle}"')

        ns = argparse.Namespace(
            config=str(config_file),
            log_bundle=None,  # No CLI flag
            claude_dir=None,
            codex_dir=None,
            author="Test",
            verbose=False,
            history=False,
        )

        _cmd_compare(ns)

        captured = capsys.readouterr()
        assert "No interactions found" in captured.err


class TestLogBundleValidation:
    """Tests for log bundle path validation in _cmd_compare."""

    def test_rejects_nonexistent_bundle(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """_cmd_compare returns error for nonexistent bundle path."""
        import argparse
        from agent_taylor.cli import _cmd_compare

        ns = argparse.Namespace(
            config=None,
            log_bundle=str(tmp_path / "nonexistent"),
            claude_dir=None,
            codex_dir=None,
            author="Test",
            verbose=False,
            history=False,
        )

        result = _cmd_compare(ns)

        assert result == 1
        captured = capsys.readouterr()
        assert "does not exist" in captured.err

    def test_rejects_file_as_bundle(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """_cmd_compare returns error when bundle path is a file."""
        import argparse
        from agent_taylor.cli import _cmd_compare

        file_path = tmp_path / "not-a-dir.txt"
        file_path.write_text("content")

        ns = argparse.Namespace(
            config=None,
            log_bundle=str(file_path),
            claude_dir=None,
            codex_dir=None,
            author="Test",
            verbose=False,
            history=False,
        )

        result = _cmd_compare(ns)

        assert result == 1
        captured = capsys.readouterr()
        assert "not a directory" in captured.err

    def test_warns_when_conflicting_args(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """_cmd_compare warns when bundle and dir args both specified."""
        import argparse
        from agent_taylor.cli import _cmd_compare

        bundle = tmp_path / "bundle"
        bundle.mkdir()

        ns = argparse.Namespace(
            config=None,
            log_bundle=str(bundle),
            claude_dir="~/.claude",
            codex_dir=None,
            author="Test",
            verbose=False,
            history=False,
        )

        _cmd_compare(ns)

        captured = capsys.readouterr()
        assert "Warning" in captured.err
        assert "ignoring" in captured.err


class TestAggregateByDateAndConfiguration:
    """Tests for aggregate_by_date_and_configuration function."""

    def test_aggregates_by_date_and_config(self) -> None:
        """aggregate_by_date_and_configuration groups by date and configuration."""
        from agent_taylor.compare import aggregate_by_date_and_configuration

        session_metrics = [
            {"configuration": "none", "hours": 1.0, "commits": 2, "delta": 100, "date": "2025-12-01"},
            {"configuration": "beads", "hours": 0.5, "commits": 1, "delta": 50, "date": "2025-12-01"},
            {"configuration": "beads", "hours": 2.0, "commits": 5, "delta": 300, "date": "2025-12-03"},
        ]

        result = aggregate_by_date_and_configuration(session_metrics)

        # Should be sorted by date, then by config order
        assert len(result) == 3
        assert result[0] == {
            "date": "2025-12-01",
            "configuration": "none",
            "sessions": 1,
            "hours": 1.0,
            "commits": 2,
            "delta": 100,
            "delta_per_hour": 100.0,
            "commits_per_hour": 2.0,
        }
        assert result[1] == {
            "date": "2025-12-01",
            "configuration": "beads",
            "sessions": 1,
            "hours": 0.5,
            "commits": 1,
            "delta": 50,
            "delta_per_hour": 100.0,
            "commits_per_hour": 2.0,
        }
        assert result[2] == {
            "date": "2025-12-03",
            "configuration": "beads",
            "sessions": 1,
            "hours": 2.0,
            "commits": 5,
            "delta": 300,
            "delta_per_hour": 150.0,
            "commits_per_hour": 2.5,
        }

    def test_combines_multiple_sessions_same_date_config(self) -> None:
        """aggregate_by_date_and_configuration combines sessions on same date/config."""
        from agent_taylor.compare import aggregate_by_date_and_configuration

        session_metrics = [
            {"configuration": "beads", "hours": 1.0, "commits": 2, "delta": 100, "date": "2025-12-01"},
            {"configuration": "beads", "hours": 1.0, "commits": 3, "delta": 150, "date": "2025-12-01"},
        ]

        result = aggregate_by_date_and_configuration(session_metrics)

        assert len(result) == 1
        assert result[0]["sessions"] == 2
        assert result[0]["hours"] == 2.0
        assert result[0]["commits"] == 5
        assert result[0]["delta"] == 250
        assert result[0]["delta_per_hour"] == 125.0
        assert result[0]["commits_per_hour"] == 2.5

    def test_skips_days_with_no_sessions(self) -> None:
        """aggregate_by_date_and_configuration doesn't include empty days."""
        from agent_taylor.compare import aggregate_by_date_and_configuration

        session_metrics = [
            {"configuration": "beads", "hours": 1.0, "commits": 2, "delta": 100, "date": "2025-12-01"},
            {"configuration": "beads", "hours": 1.0, "commits": 2, "delta": 100, "date": "2025-12-05"},
        ]

        result = aggregate_by_date_and_configuration(session_metrics)

        # Only 2 entries, no entries for 12-02, 12-03, 12-04
        assert len(result) == 2
        dates = [r["date"] for r in result]
        assert dates == ["2025-12-01", "2025-12-05"]

    def test_returns_empty_list_for_no_sessions(self) -> None:
        """aggregate_by_date_and_configuration returns empty list for no sessions."""
        from agent_taylor.compare import aggregate_by_date_and_configuration

        result = aggregate_by_date_and_configuration([])

        assert result == []
