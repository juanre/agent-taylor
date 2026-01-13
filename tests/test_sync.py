# ABOUTME: Tests for the sync command functionality.
# ABOUTME: Tests log syncing from local dirs to bundle directory.

from __future__ import annotations

import socket
from pathlib import Path

import pytest


class TestSyncArgParsing:
    """Tests for sync command argument parsing."""

    def test_sync_command_exists(self) -> None:
        """sync command is available."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["sync"])

        assert ns.cmd == "sync"

    def test_accepts_bundle_flag(self) -> None:
        """sync command accepts --bundle flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["sync", "--bundle", "~/Documents/agent-logs"])

        assert ns.bundle == "~/Documents/agent-logs"

    def test_accepts_machine_name_flag(self) -> None:
        """sync command accepts --machine-name flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["sync", "--machine-name", "laptop"])

        assert ns.machine_name == "laptop"

    def test_bundle_defaults_to_none(self) -> None:
        """--bundle defaults to None when not specified."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["sync"])

        assert ns.bundle is None

    def test_machine_name_defaults_to_none(self) -> None:
        """--machine-name defaults to None when not specified."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["sync"])

        assert ns.machine_name is None


class TestSyncCommand:
    """Tests for _cmd_sync function."""

    def test_requires_bundle_location(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """_cmd_sync returns error when no bundle location available."""
        import argparse
        from agent_taylor.cli import _cmd_sync

        monkeypatch.delenv("AGENT_TAYLOR_LOG_BUNDLE", raising=False)

        ns = argparse.Namespace(
            config=None,
            bundle=None,
            machine_name=None,
        )

        result = _cmd_sync(ns)

        assert result == 1
        captured = capsys.readouterr()
        assert "bundle" in captured.err.lower()

    def test_uses_hostname_as_default_machine_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_cmd_sync uses hostname when --machine-name not specified."""
        import argparse
        from agent_taylor.cli import _cmd_sync

        bundle = tmp_path / "bundle"
        bundle.mkdir()

        # Create source dirs
        claude_dir = tmp_path / "claude"
        claude_dir.mkdir()
        (claude_dir / "test.txt").write_text("test")

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr("agent_taylor.cli.Path.home", lambda: tmp_path)

        ns = argparse.Namespace(
            config=None,
            bundle=str(bundle),
            machine_name=None,
        )

        _cmd_sync(ns)

        # Should create directory named after hostname
        hostname = socket.gethostname()
        assert (bundle / hostname).is_dir()

    def test_creates_machine_dir_if_needed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_cmd_sync creates machine subdirectory if it doesn't exist."""
        import argparse
        from agent_taylor.cli import _cmd_sync

        bundle = tmp_path / "bundle"
        bundle.mkdir()

        # Create source .claude dir
        claude_src = tmp_path / ".claude"
        claude_src.mkdir()
        (claude_src / "test.txt").write_text("test")

        monkeypatch.setattr("agent_taylor.cli.Path.home", lambda: tmp_path)

        ns = argparse.Namespace(
            config=None,
            bundle=str(bundle),
            machine_name="testmachine",
        )

        _cmd_sync(ns)

        assert (bundle / "testmachine").is_dir()

    def test_copies_claude_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_cmd_sync copies ~/.claude to bundle."""
        import argparse
        from agent_taylor.cli import _cmd_sync

        bundle = tmp_path / "bundle"
        bundle.mkdir()

        # Create source .claude dir with content
        claude_src = tmp_path / ".claude"
        claude_src.mkdir()
        (claude_src / "projects").mkdir()
        (claude_src / "projects" / "session.jsonl").write_text('{"test": true}')

        monkeypatch.setattr("agent_taylor.cli.Path.home", lambda: tmp_path)

        ns = argparse.Namespace(
            config=None,
            bundle=str(bundle),
            machine_name="testmachine",
        )

        _cmd_sync(ns)

        assert (bundle / "testmachine" / "claude" / "projects" / "session.jsonl").exists()
        assert (bundle / "testmachine" / "claude" / "projects" / "session.jsonl").read_text() == '{"test": true}'

    def test_copies_codex_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_cmd_sync copies ~/.codex to bundle."""
        import argparse
        from agent_taylor.cli import _cmd_sync

        bundle = tmp_path / "bundle"
        bundle.mkdir()

        # Create source .codex dir with content
        codex_src = tmp_path / ".codex"
        codex_src.mkdir()
        (codex_src / "sessions").mkdir()
        (codex_src / "sessions" / "session.jsonl").write_text('{"codex": true}')

        monkeypatch.setattr("agent_taylor.cli.Path.home", lambda: tmp_path)

        ns = argparse.Namespace(
            config=None,
            bundle=str(bundle),
            machine_name="testmachine",
        )

        _cmd_sync(ns)

        assert (bundle / "testmachine" / "codex" / "sessions" / "session.jsonl").exists()

    def test_handles_missing_source_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """_cmd_sync handles case where source dirs don't exist."""
        import argparse
        from agent_taylor.cli import _cmd_sync

        bundle = tmp_path / "bundle"
        bundle.mkdir()

        # No .claude or .codex dirs exist
        monkeypatch.setattr("agent_taylor.cli.Path.home", lambda: tmp_path)

        ns = argparse.Namespace(
            config=None,
            bundle=str(bundle),
            machine_name="testmachine",
        )

        result = _cmd_sync(ns)

        # Should succeed but note nothing to sync
        assert result == 0
        captured = capsys.readouterr()
        assert "nothing to sync" in captured.out.lower() or "no sources" in captured.out.lower()

    def test_uses_env_var_for_bundle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_cmd_sync uses AGENT_TAYLOR_LOG_BUNDLE env var."""
        import argparse
        from agent_taylor.cli import _cmd_sync

        bundle = tmp_path / "bundle"
        bundle.mkdir()

        claude_src = tmp_path / ".claude"
        claude_src.mkdir()
        (claude_src / "test.txt").write_text("test")

        monkeypatch.setenv("AGENT_TAYLOR_LOG_BUNDLE", str(bundle))
        monkeypatch.setattr("agent_taylor.cli.Path.home", lambda: tmp_path)

        ns = argparse.Namespace(
            config=None,
            bundle=None,  # Not specified, should use env var
            machine_name="testmachine",
        )

        result = _cmd_sync(ns)

        assert result == 0
        assert (bundle / "testmachine" / "claude").exists()

    def test_cli_bundle_overrides_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLI --bundle flag takes priority over env var."""
        import argparse
        from agent_taylor.cli import _cmd_sync

        env_bundle = tmp_path / "env-bundle"
        env_bundle.mkdir()
        cli_bundle = tmp_path / "cli-bundle"
        cli_bundle.mkdir()

        claude_src = tmp_path / ".claude"
        claude_src.mkdir()
        (claude_src / "test.txt").write_text("test")

        monkeypatch.setenv("AGENT_TAYLOR_LOG_BUNDLE", str(env_bundle))
        monkeypatch.setattr("agent_taylor.cli.Path.home", lambda: tmp_path)

        ns = argparse.Namespace(
            config=None,
            bundle=str(cli_bundle),  # CLI flag set
            machine_name="testmachine",
        )

        _cmd_sync(ns)

        # Should use cli_bundle, not env_bundle
        assert (cli_bundle / "testmachine" / "claude").exists()
        assert not (env_bundle / "testmachine").exists()

    def test_uses_config_log_bundle_when_no_cli_or_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_cmd_sync uses config.log_bundle when CLI and env var not set."""
        import argparse
        from agent_taylor.cli import _cmd_sync

        monkeypatch.delenv("AGENT_TAYLOR_LOG_BUNDLE", raising=False)

        bundle = tmp_path / "bundle"
        bundle.mkdir()
        config_file = tmp_path / "config.toml"
        config_file.write_text(f'log_bundle = "{bundle}"')

        claude_src = tmp_path / ".claude"
        claude_src.mkdir()
        (claude_src / "test.txt").write_text("test")

        monkeypatch.setattr("agent_taylor.cli.Path.home", lambda: tmp_path)

        ns = argparse.Namespace(
            config=str(config_file),
            bundle=None,
            machine_name="testmachine",
        )

        result = _cmd_sync(ns)

        assert result == 0
        assert (bundle / "testmachine" / "claude").exists()

    def test_cli_overrides_config_log_bundle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLI --bundle takes priority over config file."""
        import argparse
        from agent_taylor.cli import _cmd_sync

        monkeypatch.delenv("AGENT_TAYLOR_LOG_BUNDLE", raising=False)

        cli_bundle = tmp_path / "cli-bundle"
        cli_bundle.mkdir()
        config_bundle = tmp_path / "config-bundle"
        config_bundle.mkdir()

        config_file = tmp_path / "config.toml"
        config_file.write_text(f'log_bundle = "{config_bundle}"')

        claude_src = tmp_path / ".claude"
        claude_src.mkdir()
        (claude_src / "test.txt").write_text("test")

        monkeypatch.setattr("agent_taylor.cli.Path.home", lambda: tmp_path)

        ns = argparse.Namespace(
            config=str(config_file),
            bundle=str(cli_bundle),
            machine_name="testmachine",
        )

        _cmd_sync(ns)

        assert (cli_bundle / "testmachine" / "claude").exists()
        assert not (config_bundle / "testmachine").exists()

    def test_env_var_overrides_config_log_bundle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment variable takes priority over config file."""
        import argparse
        from agent_taylor.cli import _cmd_sync

        env_bundle = tmp_path / "env-bundle"
        env_bundle.mkdir()
        config_bundle = tmp_path / "config-bundle"
        config_bundle.mkdir()

        monkeypatch.setenv("AGENT_TAYLOR_LOG_BUNDLE", str(env_bundle))

        config_file = tmp_path / "config.toml"
        config_file.write_text(f'log_bundle = "{config_bundle}"')

        claude_src = tmp_path / ".claude"
        claude_src.mkdir()
        (claude_src / "test.txt").write_text("test")

        monkeypatch.setattr("agent_taylor.cli.Path.home", lambda: tmp_path)

        ns = argparse.Namespace(
            config=str(config_file),
            bundle=None,
            machine_name="testmachine",
        )

        _cmd_sync(ns)

        assert (env_bundle / "testmachine" / "claude").exists()
        assert not (config_bundle / "testmachine").exists()
