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


class TestDiscoverBundleSources:
    """Tests for _discover_bundle_sources function."""

    def test_discovers_claude_and_codex_dirs(self, tmp_path: Path) -> None:
        """_discover_bundle_sources finds claude/ and codex/ in machine dirs."""
        from agent_taylor.ai_hours import _discover_bundle_sources

        bundle = tmp_path / "agent-logs"
        (bundle / "altair" / "claude" / "projects").mkdir(parents=True)
        (bundle / "altair" / "codex" / "sessions").mkdir(parents=True)
        (bundle / "antares" / "claude" / "projects").mkdir(parents=True)
        (bundle / "antares" / "codex" / "sessions").mkdir(parents=True)

        claude_dirs, codex_dirs = _discover_bundle_sources(bundle)

        assert len(claude_dirs) == 2
        assert len(codex_dirs) == 2
        assert bundle / "altair" / "claude" in claude_dirs
        assert bundle / "antares" / "claude" in claude_dirs

    def test_handles_partial_machines(self, tmp_path: Path) -> None:
        """_discover_bundle_sources handles machines with only claude or codex."""
        from agent_taylor.ai_hours import _discover_bundle_sources

        bundle = tmp_path / "agent-logs"
        (bundle / "altair" / "claude" / "projects").mkdir(parents=True)
        (bundle / "altair" / "codex" / "sessions").mkdir(parents=True)
        (bundle / "old" / "claude" / "projects").mkdir(parents=True)
        # old has no codex

        claude_dirs, codex_dirs = _discover_bundle_sources(bundle)

        assert len(claude_dirs) == 2
        assert len(codex_dirs) == 1
        assert bundle / "old" / "claude" in claude_dirs

    def test_empty_bundle(self, tmp_path: Path) -> None:
        """_discover_bundle_sources returns empty lists for empty bundle."""
        from agent_taylor.ai_hours import _discover_bundle_sources

        bundle = tmp_path / "agent-logs"
        bundle.mkdir()

        claude_dirs, codex_dirs = _discover_bundle_sources(bundle)

        assert claude_dirs == []
        assert codex_dirs == []

    def test_ignores_files_in_bundle(self, tmp_path: Path) -> None:
        """_discover_bundle_sources ignores non-directory entries."""
        from agent_taylor.ai_hours import _discover_bundle_sources

        bundle = tmp_path / "agent-logs"
        (bundle / "altair" / "claude" / "projects").mkdir(parents=True)
        (bundle / "README.md").write_text("readme")

        claude_dirs, codex_dirs = _discover_bundle_sources(bundle)

        assert len(claude_dirs) == 1

    def test_ignores_machines_without_sources(self, tmp_path: Path) -> None:
        """_discover_bundle_sources ignores machine dirs without claude or codex."""
        from agent_taylor.ai_hours import _discover_bundle_sources

        bundle = tmp_path / "agent-logs"
        (bundle / "altair" / "claude" / "projects").mkdir(parents=True)
        (bundle / "empty-machine").mkdir(parents=True)  # No claude or codex

        claude_dirs, codex_dirs = _discover_bundle_sources(bundle)

        assert len(claude_dirs) == 1
        assert len(codex_dirs) == 0

    def test_nonexistent_bundle_returns_empty(self, tmp_path: Path) -> None:
        """_discover_bundle_sources returns empty for nonexistent bundle."""
        from agent_taylor.ai_hours import _discover_bundle_sources

        bundle = tmp_path / "nonexistent-bundle"

        claude_dirs, codex_dirs = _discover_bundle_sources(bundle)

        assert claude_dirs == []
        assert codex_dirs == []


class TestCollectInteractionsWithBundle:
    """Tests for collect_interactions with log_bundle parameter."""

    def test_collects_from_multiple_machines(self, tmp_path: Path) -> None:
        """collect_interactions with bundle collects from all machines."""
        from agent_taylor.ai_hours import collect_interactions

        bundle = tmp_path / "agent-logs"

        # Create altair with a session
        altair_proj = bundle / "altair" / "claude" / "projects" / "-Users-test-prj"
        altair_proj.mkdir(parents=True)
        (altair_proj / "session1.jsonl").write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2026-01-10T10:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )

        # Create antares with a session
        antares_proj = bundle / "antares" / "claude" / "projects" / "-Users-test-prj"
        antares_proj.mkdir(parents=True)
        (antares_proj / "session2.jsonl").write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2025-12-15T14:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )

        interactions = collect_interactions(log_bundle=bundle)

        assert len(interactions) == 2
        # Should be sorted by timestamp
        assert interactions[0].timestamp < interactions[1].timestamp

    def test_bundle_mode_ignores_single_dirs(self, tmp_path: Path) -> None:
        """collect_interactions with bundle ignores claude_dir and codex_dir."""
        from agent_taylor.ai_hours import collect_interactions

        bundle = tmp_path / "agent-logs"
        bundle_proj = bundle / "altair" / "claude" / "projects" / "-Users-test-prj"
        bundle_proj.mkdir(parents=True)
        (bundle_proj / "session1.jsonl").write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2026-01-10T10:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )

        # Create a separate claude_dir that should be ignored
        other_claude = tmp_path / ".claude" / "projects" / "-Users-other-prj"
        other_claude.mkdir(parents=True)
        (other_claude / "session2.jsonl").write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2026-01-11T10:00:00.000Z",
                "cwd": "/Users/other/prj",
            }) + "\n"
        )

        interactions = collect_interactions(
            log_bundle=bundle,
            claude_dir=tmp_path / ".claude",
        )

        # Should only have the bundle interaction, not the other one
        assert len(interactions) == 1
        assert interactions[0].project == "/Users/test/prj"


class TestDetectSourceDateRangesWithBundle:
    """Tests for detect_source_date_ranges with log_bundle parameter."""

    def test_finds_earliest_across_machines(self, tmp_path: Path) -> None:
        """detect_source_date_ranges with bundle finds earliest date across machines."""
        from agent_taylor.ai_hours import detect_source_date_ranges

        bundle = tmp_path / "agent-logs"

        # altair: claude starts 2026-01-09
        altair_proj = bundle / "altair" / "claude" / "projects" / "-Users-test-prj"
        altair_proj.mkdir(parents=True)
        (altair_proj / "session1.jsonl").write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2026-01-09T10:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )

        # antares: claude starts 2025-12-13 (earlier)
        antares_proj = bundle / "antares" / "claude" / "projects" / "-Users-test-prj"
        antares_proj.mkdir(parents=True)
        (antares_proj / "session2.jsonl").write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2025-12-13T14:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )

        # old: claude starts 2025-09-27 (earliest)
        old_proj = bundle / "old" / "claude" / "projects" / "-Users-test-prj"
        old_proj.mkdir(parents=True)
        (old_proj / "session3.jsonl").write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2025-09-27T12:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )

        result = detect_source_date_ranges(log_bundle=bundle)

        assert result["claude"] == "2025-09-27"
        assert result["codex"] is None

    def test_finds_codex_dates_across_machines(self, tmp_path: Path) -> None:
        """detect_source_date_ranges with bundle finds codex dates."""
        from agent_taylor.ai_hours import detect_source_date_ranges

        bundle = tmp_path / "agent-logs"

        # altair: codex starts 2025-11-28
        altair_codex = bundle / "altair" / "codex" / "sessions" / "2025" / "11" / "28"
        altair_codex.mkdir(parents=True)
        (altair_codex / "session1.jsonl").write_text(
            json.dumps({"type": "session_meta", "payload": {"cwd": "/Users/test/prj"}})
            + "\n"
            + json.dumps({
                "type": "response_item",
                "timestamp": "2025-11-28T09:00:00.000Z",
                "payload": {"type": "message", "role": "user"},
            })
            + "\n"
        )

        # antares: codex starts 2025-11-03 (earlier)
        antares_codex = bundle / "antares" / "codex" / "sessions" / "2025" / "11" / "03"
        antares_codex.mkdir(parents=True)
        (antares_codex / "session2.jsonl").write_text(
            json.dumps({"type": "session_meta", "payload": {"cwd": "/Users/test/prj"}})
            + "\n"
            + json.dumps({
                "type": "response_item",
                "timestamp": "2025-11-03T16:00:00.000Z",
                "payload": {"type": "message", "role": "user"},
            })
            + "\n"
        )

        result = detect_source_date_ranges(log_bundle=bundle)

        assert result["claude"] is None
        assert result["codex"] == "2025-11-03"

    def test_bundle_mode_ignores_single_dirs(self, tmp_path: Path) -> None:
        """detect_source_date_ranges with bundle ignores claude_dir."""
        from agent_taylor.ai_hours import detect_source_date_ranges

        bundle = tmp_path / "agent-logs"
        bundle_proj = bundle / "altair" / "claude" / "projects" / "-Users-test-prj"
        bundle_proj.mkdir(parents=True)
        (bundle_proj / "session1.jsonl").write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2026-01-10T10:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )

        # Create a separate claude_dir with earlier date that should be ignored
        other_claude = tmp_path / ".claude" / "projects" / "-Users-other-prj"
        other_claude.mkdir(parents=True)
        (other_claude / "session2.jsonl").write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2025-01-01T10:00:00.000Z",
                "cwd": "/Users/other/prj",
            }) + "\n"
        )

        result = detect_source_date_ranges(
            log_bundle=bundle,
            claude_dir=tmp_path / ".claude",
        )

        # Should be bundle date (2026-01-10), not the ignored earlier date
        assert result["claude"] == "2026-01-10"
