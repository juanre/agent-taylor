from __future__ import annotations

import argparse
import sys
from importlib import metadata
from pathlib import Path

from .ai_hours import (
    aggregate_daily_project_hours,
    aggregate_daily_sitting_hours,
    collect_interactions,
    detect_sessions,
    detect_sittings,
    print_summary as print_ai_hours_summary,
    write_sessions_csv,
    write_sittings_csv,
)
from .beads_metrics import gather_beads_metrics, human_bytes, write_beads_csv
from .batch import (
    aggregate_daily_metrics,
    analyze_repos,
    print_batch_summary,
    write_aggregated_csv,
)
from .combined import (
    aggregate_git_dailies,
    combine_metrics,
    compute_summary,
    load_ai_sessions,
    load_ai_sittings,
    load_git_daily,
    print_combined_summary,
    write_combined_csv,
)
from .git_metrics import (
    AnalyzeOptions,
    collect_commit_metrics,
    commit_rows,
    daily_rows,
    print_summary,
    write_csv,
)
from .plotting import (
    load_progression_from_daily_csv,
    load_rates_from_daily_csv,
    plot_delta_progression_png,
    plot_rates_png,
)


def _version() -> str:
    try:
        return metadata.version("agent-taylor")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def _cmd_analyze(ns: argparse.Namespace) -> int:
    options = AnalyzeOptions(
        by=ns.by,
        include_merges=ns.include_merges,
        author=ns.author,
        since=ns.since,
        until=ns.until,
        outlier_method=ns.outlier_method,
        outlier_z=ns.outlier_z,
    )
    repo = Path(ns.repo)
    output_dir = Path(ns.output_dir).expanduser()
    commits = collect_commit_metrics(repo, options)
    daily = daily_rows(commits)

    commit_csv = output_dir / "commit_metrics.csv"
    daily_csv = output_dir / "daily_metrics.csv"

    write_csv(
        commit_csv,
        commit_rows(commits),
        [
            "day",
            "commit",
            "timestamp",
            "files",
            "binary_files",
            "added",
            "deleted",
            "delta",
            "is_outlier",
            "robust_z",
        ],
    )
    write_csv(
        daily_csv,
        daily,
        [
            "day",
            "commits",
            "first_ts",
            "last_ts",
            "span_hours",
            "avg_seconds_between_commits",
            "prep_seconds",
            "estimated_hours",
            "estimated_hours_strict",
            "files",
            "binary_files",
            "added",
            "deleted",
            "delta",
            "outlier_commits",
            "delta_ex_outliers",
            "commits_per_span_hour",
            "delta_per_span_hour",
            "commits_per_estimated_hour",
            "delta_per_estimated_hour",
            "delta_per_estimated_hour_ex_outliers",
            "commits_per_estimated_hour_strict",
            "delta_per_estimated_hour_strict",
            "delta_per_estimated_hour_strict_ex_outliers",
            "avg_delta_per_commit",
            "median_delta_per_commit",
            "p90_delta_per_commit",
            "max_delta_per_commit",
        ],
    )

    print_summary(repo.expanduser().resolve(), options, commits, daily)
    print(f"csv_daily: {daily_csv}")
    print(f"csv_commit: {commit_csv}")
    return 0


def _cmd_plot_rates(ns: argparse.Namespace) -> int:
    daily_csv = Path(ns.daily_csv).expanduser().resolve()
    output_png = (
        Path(ns.output_png).expanduser()
        if ns.output_png
        else daily_csv.parent / "rates_over_time.png"
    )
    rates = load_rates_from_daily_csv(daily_csv, hours=ns.hours)
    title = ns.title or f"rates over time ({ns.hours} hours)"
    plot_rates_png(
        rates=rates,
        output_png=output_png,
        title=title,
        rolling_window=ns.rolling_window,
        dpi=ns.dpi,
    )
    print(f"wrote: {output_png}")
    return 0


def _cmd_plot_progression(ns: argparse.Namespace) -> int:
    daily_csv = Path(ns.daily_csv).expanduser().resolve()
    output_png = (
        Path(ns.output_png).expanduser()
        if ns.output_png
        else daily_csv.parent / "delta_progression.png"
    )
    series = load_progression_from_daily_csv(
        daily_csv=daily_csv,
        hours=ns.hours,
        window_hours=ns.window_hours,
    )
    title = ns.title or f"delta/hour progression ({ns.hours} hours, {ns.window_hours}h window)"
    plot_delta_progression_png(
        series=series,
        output_png=output_png,
        title=title,
        dpi=ns.dpi,
        log_y=ns.log_y,
    )
    print(f"wrote: {output_png}")
    return 0


def _cmd_beads(ns: argparse.Namespace) -> int:
    repos = [Path(r) for r in ns.repos]
    metrics = [gather_beads_metrics(r) for r in repos]

    if ns.output_csv:
        out_csv = Path(ns.output_csv).expanduser()
        write_beads_csv(out_csv, metrics)
        print(f"csv: {out_csv}")

    for m in metrics:
        db_total = m.beads_db_bytes + m.beads_db_wal_bytes + m.beads_db_shm_bytes
        print(f"repo: {m.repo}")
        print(f"  beads.db_total: {human_bytes(db_total)} ({db_total} bytes)")
        print(f"  .beads_total: {human_bytes(m.beads_total_bytes)} ({m.beads_total_bytes} bytes)")
        print(f"  issues.jsonl_lines: {m.issues_jsonl_lines}")
        print(
            f"  issues.jsonl_size: {human_bytes(m.issues_jsonl_bytes)} ({m.issues_jsonl_bytes} bytes)"
        )
    return 0


def _cmd_ai_hours(ns: argparse.Namespace) -> int:
    claude_dir = Path(ns.claude_dir).expanduser() if ns.claude_dir else None
    codex_dir = Path(ns.codex_dir).expanduser() if ns.codex_dir else None
    output_dir = Path(ns.output_dir).expanduser()

    interactions = collect_interactions(claude_dir=claude_dir, codex_dir=codex_dir)
    if not interactions:
        print("No interactions found in AI assistant logs.", file=sys.stderr)
        return 1

    sessions = detect_sessions(interactions, project_filter=ns.project)
    sittings = detect_sittings(interactions)

    daily_project = aggregate_daily_project_hours(sessions)
    daily_sitting = aggregate_daily_sitting_hours(sittings)

    # Filter sittings to date range of sessions if project filter is set
    if ns.project and daily_project:
        days = set(h.day for h in daily_project)
        daily_sitting = [h for h in daily_sitting if h.day in days]

    sessions_csv = output_dir / "ai_sessions.csv"
    sittings_csv = output_dir / "ai_sittings.csv"

    write_sessions_csv(sessions_csv, daily_project)
    write_sittings_csv(sittings_csv, daily_sitting)

    print_ai_hours_summary(daily_project, daily_sitting, project_filter=ns.project)
    print(f"csv_sessions: {sessions_csv}")
    print(f"csv_sittings: {sittings_csv}")
    return 0


def _cmd_batch_analyze(ns: argparse.Namespace) -> int:
    repos = [Path(r).expanduser().resolve() for r in ns.repos]
    output_dir = Path(ns.output_dir).expanduser()

    options = AnalyzeOptions(
        by=ns.by,
        include_merges=ns.include_merges,
        author=ns.author,
        since=ns.since,
        until=ns.until,
        outlier_method=ns.outlier_method,
        outlier_z=ns.outlier_z,
    )

    all_daily = analyze_repos(repos, options)
    if not all_daily:
        print("No commits found in any repo", file=sys.stderr)
        return 1

    aggregated = aggregate_daily_metrics(all_daily)

    # Filter by date range for output
    if ns.since:
        aggregated = [r for r in aggregated if str(r["day"]) >= ns.since]
    if ns.until:
        aggregated = [r for r in aggregated if str(r["day"]) <= ns.until]

    output_csv = output_dir / "aggregated_daily.csv"
    write_aggregated_csv(output_csv, aggregated)

    print_batch_summary(all_daily, aggregated, since=ns.since, until=ns.until)
    print(f"csv: {output_csv}")
    return 0


def _cmd_combine(ns: argparse.Namespace) -> int:
    output_dir = Path(ns.output_dir).expanduser()

    # Load git daily metrics (single file or multiple)
    git_daily_paths = [Path(p).expanduser().resolve() for p in ns.git_daily]
    if len(git_daily_paths) == 1:
        git_daily = load_git_daily(git_daily_paths[0])
    else:
        git_daily = aggregate_git_dailies(git_daily_paths)

    # Load AI hours (sessions or sittings)
    if ns.ai_sessions:
        ai_hours = load_ai_sessions(Path(ns.ai_sessions), project=ns.project)
        hours_type = "session"
    elif ns.ai_sittings:
        ai_hours = load_ai_sittings(Path(ns.ai_sittings))
        hours_type = "sitting"
    else:
        print("Must specify --ai-sessions or --ai-sittings", file=sys.stderr)
        return 1

    if not git_daily:
        print("No git daily metrics found", file=sys.stderr)
        return 1
    if not ai_hours:
        print("No AI hours found", file=sys.stderr)
        return 1

    # Combine and filter by date range
    combined = combine_metrics(
        git_daily=git_daily,
        ai_hours=ai_hours,
        since=ns.since,
        until=ns.until,
    )

    if not combined:
        print("No overlapping days between git and AI data", file=sys.stderr)
        return 1

    summary = compute_summary(combined)
    if summary is None:
        print("Could not compute summary", file=sys.stderr)
        return 1

    # Write output
    combined_csv = output_dir / f"combined_{hours_type}.csv"
    write_combined_csv(combined_csv, combined)

    print(f"hours_type: {hours_type}")
    if ns.project:
        print(f"project_filter: {ns.project}")
    print_combined_summary(summary)
    print(f"csv: {combined_csv}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-taylor", description="Git history analysis utilities."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")

    sub = parser.add_subparsers(dest="cmd", required=True)

    analyze = sub.add_parser(
        "analyze", help="Extract per-commit and per-day metrics from git history."
    )
    analyze.add_argument("--repo", default=".", help="Path to the git repo to analyze.")
    analyze.add_argument(
        "--output-dir", default="out/git-history", help="Directory to write CSV outputs."
    )
    analyze.add_argument(
        "--by", choices=["committer", "author"], default="committer", help="Which date to group by."
    )
    analyze.add_argument("--include-merges", action="store_true", help="Include merge commits.")
    analyze.add_argument(
        "--author", default=None, help="Filter commits by author regex (git log --author)."
    )
    analyze.add_argument(
        "--since", default=None, help="Only include commits since this date (git log --since)."
    )
    analyze.add_argument(
        "--until", default=None, help="Only include commits until this date (git log --until)."
    )
    analyze.add_argument(
        "--outlier-method",
        choices=["none", "mad-log-delta"],
        default="none",
        help="How to flag outlier commits by change size.",
    )
    analyze.add_argument(
        "--outlier-z", type=float, default=3.5, help="Robust z-score threshold (default: 3.5)."
    )
    analyze.set_defaults(func=_cmd_analyze)

    plot = sub.add_parser("plot-rates", help="Plot commits/hour and delta/hour over active days.")
    plot.add_argument("--daily-csv", required=True, help="Path to daily_metrics.csv.")
    plot.add_argument(
        "--output-png", default=None, help="Output PNG path (default: alongside daily CSV)."
    )
    plot.add_argument(
        "--hours",
        choices=["estimated", "strict"],
        default="estimated",
        help="Which hour estimate to use.",
    )
    plot.add_argument(
        "--rolling-window", type=int, default=7, help="Rolling mean window (default: 7)."
    )
    plot.add_argument("--dpi", type=int, default=160, help="PNG DPI (default: 160).")
    plot.add_argument("--title", default=None, help="Plot title.")
    plot.set_defaults(func=_cmd_plot_rates)

    progression = sub.add_parser(
        "plot-progression",
        help="Plot rolling mean delta/hour vs cumulative estimated hours (active days only).",
    )
    progression.add_argument("--daily-csv", required=True, help="Path to daily_metrics.csv.")
    progression.add_argument(
        "--output-png", default=None, help="Output PNG path (default: alongside daily CSV)."
    )
    progression.add_argument(
        "--hours",
        choices=["estimated", "strict"],
        default="estimated",
        help="Which hour estimate to use.",
    )
    progression.add_argument(
        "--window-hours",
        type=float,
        default=40.0,
        help="Rolling window size in hours (default: 40).",
    )
    progression.add_argument("--dpi", type=int, default=160, help="PNG DPI (default: 160).")
    progression.add_argument("--title", default=None, help="Plot title.")
    progression.add_argument("--log-y", action="store_true", help="Force log y-scale.")
    progression.set_defaults(func=_cmd_plot_progression)

    beads = sub.add_parser(
        "beads", help="Report beads database size and bead count from .beads/ in repos."
    )
    beads.add_argument("repos", nargs="+", help="Repo paths to analyze for .beads usage.")
    beads.add_argument("--output-csv", default=None, help="Write a summary CSV to this path.")
    beads.set_defaults(func=_cmd_beads)

    ai_hours = sub.add_parser(
        "ai-hours",
        help="Estimate work hours from AI assistant (Claude Code, Codex) conversation logs.",
    )
    ai_hours.add_argument(
        "--output-dir",
        default="out/ai-hours",
        help="Directory to write CSV outputs (default: out/ai-hours).",
    )
    ai_hours.add_argument(
        "--project",
        default=None,
        help="Filter to a specific project by name (last path element, e.g., 'beadhub').",
    )
    ai_hours.add_argument(
        "--claude-dir",
        default=None,
        help="Path to Claude Code config dir (default: ~/.claude).",
    )
    ai_hours.add_argument(
        "--codex-dir",
        default=None,
        help="Path to Codex config dir (default: ~/.codex).",
    )
    ai_hours.set_defaults(func=_cmd_ai_hours)

    combine = sub.add_parser(
        "combine",
        help="Combine git metrics with AI hours for accurate productivity rates.",
    )
    combine.add_argument(
        "--git-daily",
        nargs="+",
        required=True,
        help="Path(s) to daily_metrics.csv from git analysis. Multiple paths are aggregated.",
    )
    combine.add_argument(
        "--ai-sessions",
        default=None,
        help="Path to ai_sessions.csv (for per-project hours).",
    )
    combine.add_argument(
        "--ai-sittings",
        default=None,
        help="Path to ai_sittings.csv (for total active hours).",
    )
    combine.add_argument(
        "--project",
        default=None,
        help="Filter AI sessions to this project (required with --ai-sessions).",
    )
    combine.add_argument(
        "--since",
        default=None,
        help="Only include days on or after this date (YYYY-MM-DD).",
    )
    combine.add_argument(
        "--until",
        default=None,
        help="Only include days on or before this date (YYYY-MM-DD).",
    )
    combine.add_argument(
        "--output-dir",
        default="out/combined",
        help="Directory to write CSV outputs (default: out/combined).",
    )
    combine.set_defaults(func=_cmd_combine)

    batch = sub.add_parser(
        "batch-analyze",
        help="Analyze multiple git repos and aggregate daily metrics.",
    )
    batch.add_argument(
        "repos",
        nargs="+",
        help="Paths to git repos to analyze.",
    )
    batch.add_argument(
        "--output-dir",
        default="out/batch",
        help="Directory to write aggregated CSV (default: out/batch).",
    )
    batch.add_argument(
        "--by",
        choices=["committer", "author"],
        default="committer",
        help="Which date to group by.",
    )
    batch.add_argument(
        "--include-merges",
        action="store_true",
        help="Include merge commits.",
    )
    batch.add_argument(
        "--author",
        default=None,
        help="Filter commits by author regex.",
    )
    batch.add_argument(
        "--since",
        default=None,
        help="Only include commits since this date.",
    )
    batch.add_argument(
        "--until",
        default=None,
        help="Only include commits until this date.",
    )
    batch.add_argument(
        "--outlier-method",
        choices=["none", "mad-log-delta"],
        default="none",
        help="How to flag outlier commits.",
    )
    batch.add_argument(
        "--outlier-z",
        type=float,
        default=3.5,
        help="Robust z-score threshold.",
    )
    batch.set_defaults(func=_cmd_batch_analyze)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    ns = parser.parse_args(argv)
    try:
        rc = int(ns.func(ns))
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(2) from e
    raise SystemExit(rc)
