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


class TestMergeCoverageWindows:
    """Tests for merge_coverage_windows function."""

    def test_empty_list_returns_empty(self) -> None:
        """merge_coverage_windows returns empty list for empty input."""
        from agent_taylor.ai_hours import merge_coverage_windows

        result = merge_coverage_windows([])

        assert result == []

    def test_single_window_returned_unchanged(self) -> None:
        """merge_coverage_windows returns single window unchanged."""
        from agent_taylor.ai_hours import merge_coverage_windows

        result = merge_coverage_windows([("2025-01-01", "2025-01-31")])

        assert result == [("2025-01-01", "2025-01-31")]

    def test_non_overlapping_windows_preserved(self) -> None:
        """merge_coverage_windows preserves non-overlapping windows."""
        from agent_taylor.ai_hours import merge_coverage_windows

        result = merge_coverage_windows([
            ("2025-01-01", "2025-01-31"),
            ("2025-03-01", "2025-03-31"),
        ])

        assert result == [
            ("2025-01-01", "2025-01-31"),
            ("2025-03-01", "2025-03-31"),
        ]

    def test_overlapping_windows_merged(self) -> None:
        """merge_coverage_windows merges overlapping windows."""
        from agent_taylor.ai_hours import merge_coverage_windows

        result = merge_coverage_windows([
            ("2025-01-01", "2025-02-15"),
            ("2025-02-01", "2025-03-15"),
        ])

        assert result == [("2025-01-01", "2025-03-15")]

    def test_adjacent_windows_merged(self) -> None:
        """merge_coverage_windows merges adjacent windows (end meets start)."""
        from agent_taylor.ai_hours import merge_coverage_windows

        result = merge_coverage_windows([
            ("2025-01-01", "2025-01-31"),
            ("2025-02-01", "2025-02-28"),
        ])

        # Adjacent windows should be merged (no gap between them)
        assert result == [("2025-01-01", "2025-02-28")]

    def test_unsorted_input_produces_sorted_output(self) -> None:
        """merge_coverage_windows sorts input before merging."""
        from agent_taylor.ai_hours import merge_coverage_windows

        result = merge_coverage_windows([
            ("2025-06-01", "2025-06-30"),
            ("2025-01-01", "2025-01-31"),
            ("2025-03-01", "2025-03-31"),
        ])

        assert result == [
            ("2025-01-01", "2025-01-31"),
            ("2025-03-01", "2025-03-31"),
            ("2025-06-01", "2025-06-30"),
        ]

    def test_multiple_overlapping_windows(self) -> None:
        """merge_coverage_windows handles multiple overlapping windows."""
        from agent_taylor.ai_hours import merge_coverage_windows

        result = merge_coverage_windows([
            ("2025-01-01", "2025-02-15"),
            ("2025-02-10", "2025-03-20"),
            ("2025-03-15", "2025-04-30"),
        ])

        # All three overlap, should merge into one
        assert result == [("2025-01-01", "2025-04-30")]

    def test_mixed_overlapping_and_separate(self) -> None:
        """merge_coverage_windows handles mix of overlapping and separate windows."""
        from agent_taylor.ai_hours import merge_coverage_windows

        result = merge_coverage_windows([
            ("2025-01-01", "2025-02-15"),  # Group 1
            ("2025-02-10", "2025-03-15"),  # Group 1 (overlaps)
            ("2025-06-01", "2025-07-15"),  # Group 2 (separate)
            ("2025-07-01", "2025-08-15"),  # Group 2 (overlaps)
        ])

        assert result == [
            ("2025-01-01", "2025-03-15"),
            ("2025-06-01", "2025-08-15"),
        ]

    def test_contained_window_absorbed(self) -> None:
        """merge_coverage_windows absorbs window fully contained in another."""
        from agent_taylor.ai_hours import merge_coverage_windows

        result = merge_coverage_windows([
            ("2025-01-01", "2025-12-31"),
            ("2025-03-01", "2025-04-30"),  # Fully contained
        ])

        assert result == [("2025-01-01", "2025-12-31")]

    def test_one_day_gap_not_merged(self) -> None:
        """merge_coverage_windows does NOT merge windows with a 1-day gap."""
        from agent_taylor.ai_hours import merge_coverage_windows

        # Jan 31 to Feb 2 - Feb 1 is missing (1-day gap)
        result = merge_coverage_windows([
            ("2025-01-01", "2025-01-31"),
            ("2025-02-02", "2025-02-28"),
        ])

        # Should stay separate because Feb 1 is not covered
        assert result == [
            ("2025-01-01", "2025-01-31"),
            ("2025-02-02", "2025-02-28"),
        ]

    def test_single_day_windows(self) -> None:
        """merge_coverage_windows handles single-day windows."""
        from agent_taylor.ai_hours import merge_coverage_windows

        result = merge_coverage_windows([
            ("2025-01-01", "2025-01-01"),
            ("2025-01-02", "2025-01-02"),
            ("2025-01-03", "2025-01-03"),
        ])

        # All consecutive days should merge
        assert result == [("2025-01-01", "2025-01-03")]

    def test_single_day_with_gap(self) -> None:
        """merge_coverage_windows keeps single-day windows separate if gap exists."""
        from agent_taylor.ai_hours import merge_coverage_windows

        result = merge_coverage_windows([
            ("2025-01-01", "2025-01-01"),
            ("2025-01-03", "2025-01-03"),  # Jan 2 missing
        ])

        assert result == [
            ("2025-01-01", "2025-01-01"),
            ("2025-01-03", "2025-01-03"),
        ]


class TestIsDateCovered:
    """Tests for is_date_covered function."""

    def test_empty_windows_returns_false(self) -> None:
        """is_date_covered returns False for empty windows."""
        from agent_taylor.ai_hours import is_date_covered

        result = is_date_covered("2025-01-15", [])

        assert result is False

    def test_date_within_window(self) -> None:
        """is_date_covered returns True for date within a window."""
        from agent_taylor.ai_hours import is_date_covered

        result = is_date_covered("2025-01-15", [("2025-01-01", "2025-01-31")])

        assert result is True

    def test_date_outside_window(self) -> None:
        """is_date_covered returns False for date outside all windows."""
        from agent_taylor.ai_hours import is_date_covered

        result = is_date_covered("2025-03-15", [("2025-01-01", "2025-01-31")])

        assert result is False

    def test_date_on_start_boundary(self) -> None:
        """is_date_covered returns True for date on window start boundary."""
        from agent_taylor.ai_hours import is_date_covered

        result = is_date_covered("2025-01-01", [("2025-01-01", "2025-01-31")])

        assert result is True

    def test_date_on_end_boundary(self) -> None:
        """is_date_covered returns True for date on window end boundary."""
        from agent_taylor.ai_hours import is_date_covered

        result = is_date_covered("2025-01-31", [("2025-01-01", "2025-01-31")])

        assert result is True

    def test_date_in_gap_between_windows(self) -> None:
        """is_date_covered returns False for date in gap between windows."""
        from agent_taylor.ai_hours import is_date_covered

        windows = [
            ("2025-01-01", "2025-01-31"),
            ("2025-03-01", "2025-03-31"),
        ]
        result = is_date_covered("2025-02-15", windows)

        assert result is False

    def test_date_before_all_windows(self) -> None:
        """is_date_covered returns False for date before all windows."""
        from agent_taylor.ai_hours import is_date_covered

        windows = [
            ("2025-06-01", "2025-06-30"),
            ("2025-08-01", "2025-08-31"),
        ]
        result = is_date_covered("2025-01-15", windows)

        assert result is False

    def test_date_after_all_windows(self) -> None:
        """is_date_covered returns False for date after all windows."""
        from agent_taylor.ai_hours import is_date_covered

        windows = [
            ("2025-01-01", "2025-01-31"),
            ("2025-03-01", "2025-03-31"),
        ]
        result = is_date_covered("2025-12-15", windows)

        assert result is False

    def test_date_in_second_window(self) -> None:
        """is_date_covered returns True for date in second of multiple windows."""
        from agent_taylor.ai_hours import is_date_covered

        windows = [
            ("2025-01-01", "2025-01-31"),
            ("2025-03-01", "2025-03-31"),
        ]
        result = is_date_covered("2025-03-15", windows)

        assert result is True


class TestIntersectCoverageWindows:
    """Tests for intersect_coverage_windows function."""

    def test_empty_first_list_returns_empty(self) -> None:
        """intersect_coverage_windows returns empty for empty first list."""
        from agent_taylor.ai_hours import intersect_coverage_windows

        result = intersect_coverage_windows([], [("2025-01-01", "2025-01-31")])

        assert result == []

    def test_empty_second_list_returns_empty(self) -> None:
        """intersect_coverage_windows returns empty for empty second list."""
        from agent_taylor.ai_hours import intersect_coverage_windows

        result = intersect_coverage_windows([("2025-01-01", "2025-01-31")], [])

        assert result == []

    def test_no_overlap_returns_empty(self) -> None:
        """intersect_coverage_windows returns empty when windows don't overlap."""
        from agent_taylor.ai_hours import intersect_coverage_windows

        result = intersect_coverage_windows(
            [("2025-01-01", "2025-01-31")],
            [("2025-03-01", "2025-03-31")],
        )

        assert result == []

    def test_partial_overlap(self) -> None:
        """intersect_coverage_windows returns overlapping portion."""
        from agent_taylor.ai_hours import intersect_coverage_windows

        result = intersect_coverage_windows(
            [("2025-01-01", "2025-02-15")],
            [("2025-02-01", "2025-03-15")],
        )

        # Overlap is Feb 1 - Feb 15
        assert result == [("2025-02-01", "2025-02-15")]

    def test_one_contained_in_other(self) -> None:
        """intersect_coverage_windows returns contained window."""
        from agent_taylor.ai_hours import intersect_coverage_windows

        result = intersect_coverage_windows(
            [("2025-01-01", "2025-12-31")],
            [("2025-03-01", "2025-04-30")],
        )

        assert result == [("2025-03-01", "2025-04-30")]

    def test_identical_windows(self) -> None:
        """intersect_coverage_windows returns same window for identical inputs."""
        from agent_taylor.ai_hours import intersect_coverage_windows

        result = intersect_coverage_windows(
            [("2025-01-01", "2025-01-31")],
            [("2025-01-01", "2025-01-31")],
        )

        assert result == [("2025-01-01", "2025-01-31")]

    def test_multiple_windows_with_gap(self) -> None:
        """intersect_coverage_windows handles gap in one list."""
        from agent_taylor.ai_hours import intersect_coverage_windows

        # First list has continuous coverage
        # Second list has a gap in February
        result = intersect_coverage_windows(
            [("2025-01-01", "2025-03-31")],
            [("2025-01-01", "2025-01-31"), ("2025-03-01", "2025-03-31")],
        )

        # Result should have the gap preserved
        assert result == [
            ("2025-01-01", "2025-01-31"),
            ("2025-03-01", "2025-03-31"),
        ]

    def test_multiple_overlapping_intersections(self) -> None:
        """intersect_coverage_windows handles multiple overlapping results."""
        from agent_taylor.ai_hours import intersect_coverage_windows

        result = intersect_coverage_windows(
            [("2025-01-01", "2025-02-28"), ("2025-04-01", "2025-05-31")],
            [("2025-02-01", "2025-04-30")],
        )

        # Should get two intersections:
        # Jan-Feb with Feb-Apr = Feb 1 - Feb 28
        # Apr-May with Feb-Apr = Apr 1 - Apr 30
        assert result == [
            ("2025-02-01", "2025-02-28"),
            ("2025-04-01", "2025-04-30"),
        ]

    def test_real_world_scenario_with_gap(self) -> None:
        """intersect_coverage_windows handles Juan's scenario: Claude gap, Codex continuous."""
        from agent_taylor.ai_hours import intersect_coverage_windows

        # Claude has: old computer [A, B] and altair/antares [C, D] with gap [B, C]
        claude_windows = [
            ("2025-09-01", "2025-10-15"),  # Old computer
            ("2025-12-01", "2026-01-15"),  # Altair/Antares
        ]
        # Codex has continuous coverage
        codex_windows = [
            ("2025-09-01", "2026-01-15"),
        ]

        result = intersect_coverage_windows(claude_windows, codex_windows)

        # Should preserve the gap
        assert result == [
            ("2025-09-01", "2025-10-15"),
            ("2025-12-01", "2026-01-15"),
        ]


class TestLatestClaudeTimestamp:
    """Tests for _latest_claude_timestamp function."""

    def test_empty_dir_returns_none(self, tmp_path: Path) -> None:
        """_latest_claude_timestamp returns None for empty directory."""
        from agent_taylor.ai_hours import _latest_claude_timestamp

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        result = _latest_claude_timestamp(claude_dir)

        assert result is None

    def test_finds_latest_timestamp(self, tmp_path: Path) -> None:
        """_latest_claude_timestamp finds the latest timestamp from logs."""
        from agent_taylor.ai_hours import _latest_claude_timestamp

        claude_dir = tmp_path / ".claude"
        projects_dir = claude_dir / "projects" / "-Users-test-prj"
        projects_dir.mkdir(parents=True)

        # Session with multiple messages
        session_file = projects_dir / "session1.jsonl"
        session_file.write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2025-01-01T10:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n" +
            json.dumps({
                "type": "assistant",
                "timestamp": "2025-06-15T14:30:00.000Z",  # Latest
                "cwd": "/Users/test/prj",
            }) + "\n" +
            json.dumps({
                "type": "user",
                "timestamp": "2025-03-20T09:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )

        result = _latest_claude_timestamp(claude_dir)

        # Should find June 15, 2025 14:30 UTC
        assert result is not None
        result_date = datetime.fromtimestamp(result).strftime("%Y-%m-%d")
        assert result_date == "2025-06-15"

    def test_finds_latest_across_sessions(self, tmp_path: Path) -> None:
        """_latest_claude_timestamp finds latest across multiple session files."""
        from agent_taylor.ai_hours import _latest_claude_timestamp

        claude_dir = tmp_path / ".claude"
        projects_dir = claude_dir / "projects" / "-Users-test-prj"
        projects_dir.mkdir(parents=True)

        # First session - older
        (projects_dir / "session1.jsonl").write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2025-01-01T10:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )

        # Second session - newer (use midday to avoid timezone edge cases)
        (projects_dir / "session2.jsonl").write_text(
            json.dumps({
                "type": "assistant",
                "timestamp": "2025-12-31T12:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )

        result = _latest_claude_timestamp(claude_dir)

        assert result is not None
        # Use UTC to avoid timezone issues
        from datetime import timezone
        result_date = datetime.fromtimestamp(result, timezone.utc).strftime("%Y-%m-%d")
        assert result_date == "2025-12-31"


class TestLatestCodexTimestamp:
    """Tests for _latest_codex_timestamp function."""

    def test_empty_dir_returns_none(self, tmp_path: Path) -> None:
        """_latest_codex_timestamp returns None for empty directory."""
        from agent_taylor.ai_hours import _latest_codex_timestamp

        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()

        result = _latest_codex_timestamp(codex_dir)

        assert result is None

    def test_finds_latest_timestamp(self, tmp_path: Path) -> None:
        """_latest_codex_timestamp finds the latest timestamp from logs."""
        from agent_taylor.ai_hours import _latest_codex_timestamp

        codex_dir = tmp_path / ".codex"
        sessions_dir = codex_dir / "sessions" / "2025" / "06" / "15"
        sessions_dir.mkdir(parents=True)

        session_file = sessions_dir / "session1.jsonl"
        session_file.write_text(
            json.dumps({"type": "session_meta", "payload": {"cwd": "/Users/test/prj"}})
            + "\n" +
            json.dumps({
                "type": "response_item",
                "timestamp": "2025-06-15T14:30:00.000Z",
                "payload": {"type": "message", "role": "user"},
            })
            + "\n"
        )

        result = _latest_codex_timestamp(codex_dir)

        assert result is not None
        result_date = datetime.fromtimestamp(result).strftime("%Y-%m-%d")
        assert result_date == "2025-06-15"


class TestDetectCoverageWindows:
    """Tests for detect_coverage_windows function."""

    def test_empty_dirs_return_empty_windows(self, tmp_path: Path) -> None:
        """detect_coverage_windows returns empty windows for empty dirs."""
        from agent_taylor.ai_hours import detect_coverage_windows

        claude_dir = tmp_path / ".claude"
        codex_dir = tmp_path / ".codex"
        claude_dir.mkdir()
        codex_dir.mkdir()

        result = detect_coverage_windows(claude_dir=claude_dir, codex_dir=codex_dir)

        assert result["claude"] == []
        assert result["codex"] == []

    def test_single_claude_dir_returns_window(self, tmp_path: Path) -> None:
        """detect_coverage_windows returns window for single Claude dir."""
        from agent_taylor.ai_hours import detect_coverage_windows

        claude_dir = tmp_path / ".claude"
        projects_dir = claude_dir / "projects" / "-Users-test-prj"
        projects_dir.mkdir(parents=True)

        # Write sessions spanning Jan to June
        (projects_dir / "session1.jsonl").write_text(
            json.dumps({
                "type": "user",
                "timestamp": "2025-01-15T10:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )
        (projects_dir / "session2.jsonl").write_text(
            json.dumps({
                "type": "assistant",
                "timestamp": "2025-06-20T14:00:00.000Z",
                "cwd": "/Users/test/prj",
            }) + "\n"
        )

        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()

        result = detect_coverage_windows(claude_dir=claude_dir, codex_dir=codex_dir)

        assert len(result["claude"]) == 1
        assert result["claude"][0] == ("2025-01-15", "2025-06-20")
        assert result["codex"] == []

    def test_bundle_mode_returns_windows_per_machine(self, tmp_path: Path) -> None:
        """detect_coverage_windows with bundle returns window per machine."""
        from agent_taylor.ai_hours import detect_coverage_windows

        bundle = tmp_path / "agent-logs"

        # Old machine: Jan-Mar
        old_claude = bundle / "old" / "claude" / "projects" / "-Users-test-prj"
        old_claude.mkdir(parents=True)
        (old_claude / "session.jsonl").write_text(
            json.dumps({"type": "user", "timestamp": "2025-01-01T10:00:00.000Z", "cwd": "/test"}) + "\n" +
            json.dumps({"type": "assistant", "timestamp": "2025-03-15T14:00:00.000Z", "cwd": "/test"}) + "\n"
        )

        # Altair: June-Dec (gap from Mar to June)
        altair_claude = bundle / "altair" / "claude" / "projects" / "-Users-test-prj"
        altair_claude.mkdir(parents=True)
        (altair_claude / "session.jsonl").write_text(
            json.dumps({"type": "user", "timestamp": "2025-06-01T10:00:00.000Z", "cwd": "/test"}) + "\n" +
            json.dumps({"type": "assistant", "timestamp": "2025-12-15T14:00:00.000Z", "cwd": "/test"}) + "\n"
        )

        result = detect_coverage_windows(log_bundle=bundle)

        # Should have two separate windows (the gap is preserved)
        assert len(result["claude"]) == 2
        windows_sorted = sorted(result["claude"])
        assert windows_sorted[0] == ("2025-01-01", "2025-03-15")
        assert windows_sorted[1] == ("2025-06-01", "2025-12-15")

    def test_bundle_mode_overlapping_machines_not_merged_yet(self, tmp_path: Path) -> None:
        """detect_coverage_windows returns raw windows without merging."""
        from agent_taylor.ai_hours import detect_coverage_windows

        bundle = tmp_path / "agent-logs"

        # Altair: Jan-June
        altair_claude = bundle / "altair" / "claude" / "projects" / "-Users-test-prj"
        altair_claude.mkdir(parents=True)
        (altair_claude / "session.jsonl").write_text(
            json.dumps({"type": "user", "timestamp": "2025-01-01T10:00:00.000Z", "cwd": "/test"}) + "\n" +
            json.dumps({"type": "assistant", "timestamp": "2025-06-30T14:00:00.000Z", "cwd": "/test"}) + "\n"
        )

        # Antares: May-Dec (overlaps with altair)
        antares_claude = bundle / "antares" / "claude" / "projects" / "-Users-test-prj"
        antares_claude.mkdir(parents=True)
        (antares_claude / "session.jsonl").write_text(
            json.dumps({"type": "user", "timestamp": "2025-05-01T10:00:00.000Z", "cwd": "/test"}) + "\n" +
            json.dumps({"type": "assistant", "timestamp": "2025-12-15T14:00:00.000Z", "cwd": "/test"}) + "\n"
        )

        result = detect_coverage_windows(log_bundle=bundle)

        # Should have two separate windows (not merged - that's done separately)
        assert len(result["claude"]) == 2

    def test_bundle_mode_with_codex(self, tmp_path: Path) -> None:
        """detect_coverage_windows handles both Claude and Codex in bundle."""
        from agent_taylor.ai_hours import detect_coverage_windows

        bundle = tmp_path / "agent-logs"

        # Altair with Claude
        altair_claude = bundle / "altair" / "claude" / "projects" / "-Users-test-prj"
        altair_claude.mkdir(parents=True)
        (altair_claude / "session.jsonl").write_text(
            json.dumps({"type": "user", "timestamp": "2025-01-01T10:00:00.000Z", "cwd": "/test"}) + "\n" +
            json.dumps({"type": "assistant", "timestamp": "2025-06-30T14:00:00.000Z", "cwd": "/test"}) + "\n"
        )

        # Altair with Codex
        altair_codex = bundle / "altair" / "codex" / "sessions" / "2025" / "01" / "01"
        altair_codex.mkdir(parents=True)
        (altair_codex / "session.jsonl").write_text(
            json.dumps({"type": "session_meta", "payload": {"cwd": "/test"}}) + "\n" +
            json.dumps({"type": "response_item", "timestamp": "2025-01-01T10:00:00.000Z", "payload": {"type": "message", "role": "user"}}) + "\n" +
            json.dumps({"type": "response_item", "timestamp": "2025-12-31T14:00:00.000Z", "payload": {"type": "message", "role": "assistant"}}) + "\n"
        )

        result = detect_coverage_windows(log_bundle=bundle)

        assert len(result["claude"]) == 1
        assert result["claude"][0] == ("2025-01-01", "2025-06-30")
        assert len(result["codex"]) == 1
        assert result["codex"][0] == ("2025-01-01", "2025-12-31")
