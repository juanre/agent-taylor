# ABOUTME: Tests for ai_hours module.
# ABOUTME: Tests source date range detection for AI assistant logs.

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest


class TestDetectSourceDateRanges:
    """Tests for detect_source_date_ranges function."""

    def test_empty_dirs_return_none(self, tmp_path: Path) -> None:
        """detect_source_date_ranges returns None for both when dirs are empty."""
        from agent_taylor.ai_hours import detect_source_date_ranges

        claude_dir = tmp_path / ".claude"
        codex_dir = tmp_path / ".codex"
        claude_dir.mkdir()
        codex_dir.mkdir()

        result = detect_source_date_ranges(claude_dir=claude_dir, codex_dir=codex_dir)

        assert result["claude"] is None
        assert result["codex"] is None

    def test_detects_claude_earliest_date(self, tmp_path: Path) -> None:
        """detect_source_date_ranges finds earliest date from Claude logs."""
        from agent_taylor.ai_hours import detect_source_date_ranges

        claude_dir = tmp_path / ".claude"
        projects_dir = claude_dir / "projects" / "-Users-test-prj-foo"
        projects_dir.mkdir(parents=True)

        # Write a session file with messages
        session_file = projects_dir / "session1.jsonl"
        session_file.write_text(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2025-06-15T10:00:00.000Z",
                    "cwd": "/Users/test/prj/foo",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "assistant",
                    "timestamp": "2025-06-15T10:01:00.000Z",
                    "cwd": "/Users/test/prj/foo",
                }
            )
            + "\n"
        )

        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()

        result = detect_source_date_ranges(claude_dir=claude_dir, codex_dir=codex_dir)

        assert result["claude"] == "2025-06-15"
        assert result["codex"] is None

    def test_detects_codex_earliest_date(self, tmp_path: Path) -> None:
        """detect_source_date_ranges finds earliest date from Codex logs."""
        from agent_taylor.ai_hours import detect_source_date_ranges

        codex_dir = tmp_path / ".codex"
        sessions_dir = codex_dir / "sessions" / "2025" / "03" / "01"
        sessions_dir.mkdir(parents=True)

        # Write session file
        session_file = sessions_dir / "session1.jsonl"
        session_file.write_text(
            json.dumps({"type": "session_meta", "payload": {"cwd": "/Users/test/prj/bar"}})
            + "\n"
            + json.dumps(
                {
                    "type": "response_item",
                    "timestamp": "2025-03-01T14:00:00.000Z",
                    "payload": {"type": "message", "role": "user"},
                }
            )
            + "\n"
        )

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        result = detect_source_date_ranges(claude_dir=claude_dir, codex_dir=codex_dir)

        assert result["claude"] is None
        assert result["codex"] == "2025-03-01"

    def test_returns_both_sources_earliest_dates(self, tmp_path: Path) -> None:
        """detect_source_date_ranges returns earliest date from both sources."""
        from agent_taylor.ai_hours import detect_source_date_ranges

        # Create Claude logs starting 2025-01-01
        claude_dir = tmp_path / ".claude"
        projects_dir = claude_dir / "projects" / "-Users-test-prj-foo"
        projects_dir.mkdir(parents=True)
        session_file = projects_dir / "session1.jsonl"
        session_file.write_text(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2025-01-01T09:00:00.000Z",
                    "cwd": "/Users/test/prj/foo",
                }
            )
            + "\n"
        )

        # Create Codex logs starting 2025-06-01
        codex_dir = tmp_path / ".codex"
        sessions_dir = codex_dir / "sessions" / "2025" / "06" / "01"
        sessions_dir.mkdir(parents=True)
        codex_file = sessions_dir / "session1.jsonl"
        codex_file.write_text(
            json.dumps({"type": "session_meta", "payload": {"cwd": "/Users/test/prj/bar"}})
            + "\n"
            + json.dumps(
                {
                    "type": "response_item",
                    "timestamp": "2025-06-01T10:00:00.000Z",
                    "payload": {"type": "message", "role": "user"},
                }
            )
            + "\n"
        )

        result = detect_source_date_ranges(claude_dir=claude_dir, codex_dir=codex_dir)

        assert result["claude"] == "2025-01-01"
        assert result["codex"] == "2025-06-01"


class TestEffectiveStartDate:
    """Tests for effective_start_date function."""

    def test_returns_none_when_no_sources(self) -> None:
        """effective_start_date returns None when neither source has data."""
        from agent_taylor.ai_hours import effective_start_date

        result = effective_start_date({"claude": None, "codex": None})

        assert result is None

    def test_returns_claude_when_only_claude(self) -> None:
        """effective_start_date returns Claude date when Codex is None."""
        from agent_taylor.ai_hours import effective_start_date

        result = effective_start_date({"claude": "2025-01-01", "codex": None})

        assert result == "2025-01-01"

    def test_returns_codex_when_only_codex(self) -> None:
        """effective_start_date returns Codex date when Claude is None."""
        from agent_taylor.ai_hours import effective_start_date

        result = effective_start_date({"claude": None, "codex": "2025-06-01"})

        assert result == "2025-06-01"

    def test_returns_later_date_when_both_present(self) -> None:
        """effective_start_date returns the later of the two dates."""
        from agent_taylor.ai_hours import effective_start_date

        # Claude starts earlier
        result = effective_start_date({"claude": "2025-01-01", "codex": "2025-06-01"})
        assert result == "2025-06-01"

        # Codex starts earlier
        result = effective_start_date({"claude": "2025-09-01", "codex": "2025-03-01"})
        assert result == "2025-09-01"

    def test_returns_same_date_when_equal(self) -> None:
        """effective_start_date returns the date when both are the same."""
        from agent_taylor.ai_hours import effective_start_date

        result = effective_start_date({"claude": "2025-05-15", "codex": "2025-05-15"})

        assert result == "2025-05-15"
