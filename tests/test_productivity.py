# ABOUTME: Tests for the productivity command.
# ABOUTME: Tests CLI argument parsing and command execution.

from __future__ import annotations

from pathlib import Path

import pytest


class TestProductivityArgParsing:
    """Tests for productivity command argument parsing."""

    def test_requires_author_flag(self) -> None:
        """productivity command requires --author flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()

        # Should raise SystemExit for missing required argument
        with pytest.raises(SystemExit):
            parser.parse_args(["productivity"])

    def test_accepts_author_flag(self) -> None:
        """productivity command accepts --author flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["productivity", "--author", "Juan"])

        assert ns.author == "Juan"
        assert ns.cmd == "productivity"

    def test_default_output_dir(self) -> None:
        """productivity command has default output dir."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["productivity", "--author", "Juan"])

        assert ns.output_dir == "out/productivity"

    def test_accepts_since_until(self) -> None:
        """productivity command accepts --since and --until flags."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args([
            "productivity",
            "--author", "Juan",
            "--since", "2025-01-01",
            "--until", "2025-12-31",
        ])

        assert ns.since == "2025-01-01"
        assert ns.until == "2025-12-31"

    def test_accepts_verbose_flag(self) -> None:
        """productivity command accepts --verbose flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["productivity", "--author", "Juan", "--verbose"])

        assert ns.verbose is True

    def test_accepts_config_path(self) -> None:
        """productivity command accepts --config flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args([
            "productivity",
            "--author", "Juan",
            "--config", "/path/to/config.toml",
        ])

        assert ns.config == "/path/to/config.toml"

    def test_accepts_outlier_options(self) -> None:
        """productivity command accepts outlier detection options."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args([
            "productivity",
            "--author", "Juan",
            "--outlier-method", "mad-log-delta",
            "--outlier-z", "3.0",
        ])

        assert ns.outlier_method == "mad-log-delta"
        assert ns.outlier_z == 3.0
