# ABOUTME: CLI entry point for agent-taylor productivity analysis tool.
# ABOUTME: Provides compare command for beads/beadhub configuration comparison.

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Optional, TypedDict

from .ai_hours import (
    collect_interactions,
    detect_sessions,
    detect_source_date_ranges,
    effective_start_date,
)
from .beads_metrics import gather_beads_metrics, human_bytes, write_beads_csv
from .compare import (
    SessionMetrics,
    aggregate_by_configuration,
    aggregate_by_date_and_configuration,
    classify_session,
    get_commits_in_window,
)
from .config_detection import (
    detect_beads_date,
    is_beadhub_repo,
)
from .repo_detection import (
    collect_repos_from_interactions,
    load_path_config,
)


class RepoConfig(TypedDict):
    """Configuration state for a repository."""

    beads_date: Optional[str]
    is_beadhub: bool


def _version() -> str:
    try:
        return metadata.version("agent-taylor")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def _resolve_log_bundle(cli_bundle: Optional[str]) -> Optional[Path]:
    """Resolve log bundle path from CLI flag or environment variable.

    Priority:
    1. CLI --log-bundle flag (if provided)
    2. AGENT_TAYLOR_LOG_BUNDLE environment variable
    3. None (use default single-directory mode)

    Args:
        cli_bundle: Value from --log-bundle CLI flag, or None

    Returns:
        Resolved Path with ~ expanded, or None for default mode
    """
    if cli_bundle is not None:
        return Path(cli_bundle).expanduser()

    env_bundle = os.environ.get("AGENT_TAYLOR_LOG_BUNDLE", "").strip()
    if env_bundle:
        return Path(env_bundle).expanduser()

    return None


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


def _cmd_compare(ns: argparse.Namespace) -> int:
    """Compare productivity across beads/beadhub configurations."""
    # Load path config
    config_path = Path(ns.config).expanduser() if ns.config else None
    config = load_path_config(config_path)

    # Resolve log bundle (CLI flag > env var > None)
    log_bundle = _resolve_log_bundle(ns.log_bundle)

    # Validate log bundle if provided
    if log_bundle is not None:
        if not log_bundle.exists():
            print(f"Error: Log bundle directory does not exist: {log_bundle}", file=sys.stderr)
            return 1
        if not log_bundle.is_dir():
            print(f"Error: Log bundle path is not a directory: {log_bundle}", file=sys.stderr)
            return 1
        if ns.claude_dir or ns.codex_dir:
            print(
                "Warning: --log-bundle specified, ignoring --claude-dir and --codex-dir",
                file=sys.stderr,
            )

    # Collect AI interactions
    if log_bundle is not None:
        # Bundle mode: discover sources from bundle structure
        interactions = collect_interactions(log_bundle=log_bundle)
        source_dates = detect_source_date_ranges(log_bundle=log_bundle)
    else:
        # Default mode: use single directories
        claude_dir = Path(ns.claude_dir).expanduser() if ns.claude_dir else None
        codex_dir = Path(ns.codex_dir).expanduser() if ns.codex_dir else None
        interactions = collect_interactions(claude_dir=claude_dir, codex_dir=codex_dir)
        source_dates = detect_source_date_ranges(claude_dir=claude_dir, codex_dir=codex_dir)

    if not interactions:
        print("No interactions found in AI assistant logs.", file=sys.stderr)
        return 1

    # Detect source date ranges
    auto_since = effective_start_date(source_dates)

    if ns.verbose:
        if source_dates["claude"]:
            print(f"claude_logs_start: {source_dates['claude']}")
        if source_dates["codex"]:
            print(f"codex_logs_start: {source_dates['codex']}")
        if auto_since:
            print(f"effective_start_date: {auto_since}")

    # Detect repos from interactions
    repos = collect_repos_from_interactions(interactions, config)

    if not repos:
        print("No git repositories detected from AI logs.", file=sys.stderr)
        return 1

    if ns.verbose:
        print(f"repos_detected: {len(repos)}")
        for repo_root in sorted(repos.keys()):
            repo_name = Path(repo_root).name
            print(f"  - {repo_name} ({repo_root})")

    # Get beads adoption date and beadhub status for each repo
    repo_configs: dict[str, RepoConfig] = {}
    for repo_root in repos:
        repo_path = Path(repo_root)
        beads_date = detect_beads_date(repo_path)
        is_beadhub = is_beadhub_repo(repo_path)
        repo_configs[repo_root] = RepoConfig(
            beads_date=beads_date,
            is_beadhub=is_beadhub,
        )
        if ns.verbose and (beads_date or is_beadhub):
            repo_name = repo_path.name
            info = []
            if beads_date:
                info.append(f"beads: {beads_date}")
            if is_beadhub:
                info.append("beadhub repo")
            print(f"  {repo_name}: {', '.join(info)}")

    # Detect sessions from interactions
    sessions = detect_sessions(interactions)

    if not sessions:
        print("No sessions detected.", file=sys.stderr)
        return 1

    # Build repo name -> repo root mapping
    repo_by_name: dict[str, str] = {}
    for repo_root in repos:
        repo_name = Path(repo_root).name
        repo_by_name[repo_name] = repo_root

    # Process each session
    session_metrics: list[SessionMetrics] = []
    skipped_no_repo = 0
    skipped_before_start = 0

    for session in sessions:
        # Find the repo root for this session's project
        if session.project not in repo_by_name:
            skipped_no_repo += 1
            continue
        repo_root = repo_by_name[session.project]

        # Get configuration for this session
        if repo_root not in repo_configs:
            skipped_no_repo += 1
            continue
        repo_config = repo_configs[repo_root]

        session_date = datetime.fromtimestamp(session.start_ts).strftime("%Y-%m-%d")

        # Skip sessions before effective start date
        if auto_since and session_date < auto_since:
            skipped_before_start += 1
            continue

        configuration = classify_session(
            session_start_date=session_date,
            beads_date=repo_config["beads_date"],
            is_beadhub=repo_config["is_beadhub"],
        )

        # Get commits during this session
        commits = get_commits_in_window(
            repo=Path(repo_root),
            start_ts=session.start_ts,
            end_ts=session.end_ts,
            author=ns.author,
        )

        total_delta = sum(c["delta"] for c in commits)
        hours = session.estimated_seconds / 3600

        session_metrics.append(SessionMetrics(
            configuration=configuration,
            hours=hours,
            commits=len(commits),
            delta=total_delta,
            date=session_date,
        ))

    if ns.verbose and (skipped_no_repo > 0 or skipped_before_start > 0):
        print(f"sessions_skipped_no_repo: {skipped_no_repo}")
        print(f"sessions_skipped_before_start: {skipped_before_start}")

    if not session_metrics:
        print("No sessions matched the criteria.", file=sys.stderr)
        return 1

    # Print results
    print()

    if ns.history:
        # Daily breakdown
        daily = aggregate_by_date_and_configuration(session_metrics)
        print(f"{'date':<12} {'configuration':<16} {'sessions':>8} {'hours':>8} {'commits':>8} {'delta':>10} {'delta/hr':>10} {'commits/hr':>10}")
        print("-" * 102)
        for day in daily:
            print(
                f"{day['date']:<12} {day['configuration']:<16} {day['sessions']:>8} {day['hours']:>8.1f} "
                f"{day['commits']:>8} {day['delta']:>10} "
                f"{day['delta_per_hour']:>10.1f} {day['commits_per_hour']:>10.2f}"
            )
    else:
        # Aggregate by configuration
        aggregated = aggregate_by_configuration(session_metrics)
        print(f"{'configuration':<16} {'sessions':>8} {'hours':>8} {'commits':>8} {'delta':>10} {'delta/hr':>10} {'commits/hr':>10}")
        print("-" * 82)
        for config_name in ["none", "beads", "beads+beadhub"]:
            cfg = aggregated[config_name]
            if cfg["hours"] > 0 or cfg["sessions"] > 0:
                print(
                    f"{config_name:<16} {cfg['sessions']:>8} {cfg['hours']:>8.1f} "
                    f"{cfg['commits']:>8} {cfg['delta']:>10} "
                    f"{cfg['delta_per_hour']:>10.1f} {cfg['commits_per_hour']:>10.2f}"
                )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-taylor", description="Git history analysis utilities."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")

    sub = parser.add_subparsers(dest="cmd", required=True)

    beads = sub.add_parser(
        "beads", help="Report beads database size and bead count from .beads/ in repos."
    )
    beads.add_argument("repos", nargs="+", help="Repo paths to analyze for .beads usage.")
    beads.add_argument("--output-csv", default=None, help="Write a summary CSV to this path.")
    beads.set_defaults(func=_cmd_beads)

    compare = sub.add_parser(
        "compare",
        help="Compare productivity across beads/beadhub configurations.",
    )
    compare.add_argument(
        "--author",
        required=True,
        help="Filter commits by author regex (required).",
    )
    compare.add_argument(
        "--config",
        default=None,
        help="Path config file for remapping/ignoring paths.",
    )
    compare.add_argument(
        "--claude-dir",
        default=None,
        help="Path to Claude Code config dir (default: ~/.claude).",
    )
    compare.add_argument(
        "--codex-dir",
        default=None,
        help="Path to Codex config dir (default: ~/.codex).",
    )
    compare.add_argument(
        "--log-bundle",
        default=None,
        help="Directory containing machine subdirs with claude/ and codex/ logs. "
             "Can also be set via AGENT_TAYLOR_LOG_BUNDLE env var.",
    )
    compare.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output.",
    )
    compare.add_argument(
        "--history",
        action="store_true",
        help="Show daily breakdown over time.",
    )
    compare.set_defaults(func=_cmd_compare)

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
