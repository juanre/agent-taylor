# ABOUTME: CLI entry point for agent-taylor productivity analysis tool.
# ABOUTME: Provides compare command for beads/beadhub configuration comparison.

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Optional, TypedDict

from .ai_hours import (
    collect_interactions,
    detect_coverage_windows,
    detect_sessions,
    intersect_coverage_windows,
    is_date_covered,
    merge_coverage_windows,
)
from .beads_metrics import gather_beads_metrics, human_bytes, write_beads_csv
from .compare import (
    SessionMetrics,
    aggregate_by_configuration,
    aggregate_by_date,
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


def _output_graph(daily: list, output_path: Path) -> None:
    """Generate productivity graph from daily metrics.

    Args:
        daily: List of DateMetrics dicts (already filtered to days with commits).
        output_path: Path to save the PNG file.
    """
    import matplotlib.pyplot as plt

    dates = [d["date"] for d in daily]
    delta_per_hour = [d["delta_per_hour"] for d in daily]
    commits_per_hour = [d["commits_per_hour"] for d in daily]

    fig, ax1 = plt.subplots(figsize=(12, 6))

    # X-axis: sequential index (no gaps)
    x = range(len(dates))

    # Primary y-axis: delta/hr
    color1 = "#2563eb"
    ax1.set_xlabel("Date")
    ax1.set_ylabel("delta/hr", color=color1)
    ax1.bar(x, delta_per_hour, color=color1, alpha=0.7, label="delta/hr")
    ax1.tick_params(axis="y", labelcolor=color1)

    # Secondary y-axis: commits/hr
    ax2 = ax1.twinx()
    color2 = "#dc2626"
    ax2.set_ylabel("commits/hr", color=color2)
    ax2.plot(x, commits_per_hour, color=color2, marker="o", linewidth=2, label="commits/hr")
    ax2.tick_params(axis="y", labelcolor=color2)

    # X-axis labels (dates)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(dates, rotation=45, ha="right", fontsize=8)

    # Title
    plt.title("Productivity Over Time")

    fig.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


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

    # Resolve log bundle (CLI flag > env var > config > None)
    log_bundle = _resolve_log_bundle(ns.log_bundle)
    if log_bundle is None and config.log_bundle is not None:
        log_bundle = config.log_bundle

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
        raw_coverage = detect_coverage_windows(log_bundle=log_bundle)
    else:
        # Default mode: use single directories
        claude_dir = Path(ns.claude_dir).expanduser() if ns.claude_dir else None
        codex_dir = Path(ns.codex_dir).expanduser() if ns.codex_dir else None
        interactions = collect_interactions(claude_dir=claude_dir, codex_dir=codex_dir)
        raw_coverage = detect_coverage_windows(claude_dir=claude_dir, codex_dir=codex_dir)

    if not interactions:
        print("No interactions found in AI assistant logs.", file=sys.stderr)
        return 1

    # Compute effective coverage windows
    # 1. Merge windows within each source (UNION across machines)
    claude_coverage = merge_coverage_windows(raw_coverage["claude"])
    codex_coverage = merge_coverage_windows(raw_coverage["codex"])

    # 2. Intersect Claude and Codex coverage to find periods with complete data
    if claude_coverage and codex_coverage:
        coverage_windows = intersect_coverage_windows(claude_coverage, codex_coverage)
        if not coverage_windows:
            print(
                "Warning: No overlapping coverage between Claude and Codex logs. "
                "Analyzing all sessions without coverage filtering.",
                file=sys.stderr,
            )
    elif claude_coverage:
        coverage_windows = claude_coverage
    elif codex_coverage:
        coverage_windows = codex_coverage
    else:
        coverage_windows = []

    if ns.verbose:
        if claude_coverage:
            print(f"claude_coverage: {claude_coverage}")
        if codex_coverage:
            print(f"codex_coverage: {codex_coverage}")
        if coverage_windows:
            print(f"effective_coverage: {coverage_windows}")

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
    skipped_no_coverage = 0

    # Track project data for --projects-csv
    project_sessions: dict[str, int] = {}
    project_paths: dict[str, str] = {}

    for session in sessions:
        # Skip ignored projects
        if session.project in config.ignore_projects:
            continue

        # Apply project remapping (parent-specific takes priority)
        parent_dir = Path(session.project_full).parent.name if session.project_full else ""
        parent_key = f"{parent_dir}/{session.project}"
        if parent_key in config.parent_project_remap:
            project = config.parent_project_remap[parent_key]
        else:
            project = config.project_remap.get(session.project, session.project)

        # Track project session count
        project_sessions[project] = project_sessions.get(project, 0) + 1

        # Find the repo root for this session's project
        if project in repo_by_name:
            repo_root = repo_by_name[project]
            project_paths[project] = repo_root
        elif project.startswith("beadhub-") and "beadhub" in repo_by_name:
            # Worktrees of beadhub - map to main repo for time tracking
            # (commits are already in the main repo)
            repo_root = repo_by_name["beadhub"]
            project_paths[project] = repo_root
        else:
            skipped_no_repo += 1
            continue

        # Get configuration for this session
        if repo_root not in repo_configs:
            skipped_no_repo += 1
            continue
        repo_config = repo_configs[repo_root]

        session_date = datetime.fromtimestamp(session.start_ts).strftime("%Y-%m-%d")

        # Skip sessions outside coverage windows
        if coverage_windows and not is_date_covered(session_date, coverage_windows):
            skipped_no_coverage += 1
            continue

        # Skip sessions before --since date
        if ns.since and session_date < ns.since:
            continue

        # Skip beadhub sessions before --beadhub-since date
        if ns.beadhub_since and repo_config["is_beadhub"] and session_date < ns.beadhub_since:
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

    if ns.verbose and (skipped_no_repo > 0 or skipped_no_coverage > 0):
        print(f"sessions_skipped_no_repo: {skipped_no_repo}")
        print(f"sessions_skipped_no_coverage: {skipped_no_coverage}")

    if not session_metrics:
        print("No sessions matched the criteria.", file=sys.stderr)
        return 1

    # Handle --graph (implies --history --combined)
    if ns.graph:
        daily = aggregate_by_date(session_metrics)
        # Filter out days with no commits (no progress)
        daily = [d for d in daily if d["commits"] > 0]
        if not daily:
            print("No days with commits to graph.", file=sys.stderr)
            return 1
        _output_graph(daily, Path(ns.graph).expanduser())
        print(f"Graph saved to {ns.graph}")
        return 0

    # Print results
    print()

    if ns.history:
        if ns.combined:
            # Daily breakdown, all configurations combined
            daily = aggregate_by_date(session_metrics)
            print(f"{'date':<12} {'sessions':>8} {'hours':>8} {'commits':>8} {'delta':>10} {'delta/hr':>10} {'commits/hr':>10}")
            print("-" * 84)
            for day in daily:
                print(
                    f"{day['date']:<12} {day['sessions']:>8} {day['hours']:>8.1f} "
                    f"{day['commits']:>8} {day['delta']:>10} "
                    f"{day['delta_per_hour']:>10.1f} {day['commits_per_hour']:>10.2f}"
                )
        else:
            # Daily breakdown by configuration
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

    # Output projects CSV if requested
    if ns.projects_csv:
        rows = []
        for project, count in sorted(project_sessions.items(), key=lambda x: -x[1]):
            path = project_paths.get(project, "")
            if path and path in repo_configs:
                cfg = repo_configs[path]
                beads_date = cfg["beads_date"] or ""
                is_beadhub = cfg["is_beadhub"]
                if is_beadhub:
                    bucket = "beads+beadhub"
                elif beads_date:
                    bucket = "beads"
                else:
                    bucket = "none"
            else:
                bucket = "unmatched"
                beads_date = ""
                is_beadhub = False
            rows.append({
                "project": project,
                "sessions": count,
                "bucket": bucket,
                "beads_date": beads_date,
                "is_beadhub": is_beadhub,
                "path": path,
            })
        with open(ns.projects_csv, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["project", "sessions", "bucket", "beads_date", "is_beadhub", "path"]
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {len(rows)} projects to {ns.projects_csv}")

    return 0


def _cmd_sync(ns: argparse.Namespace) -> int:
    """Sync local AI logs to a bundle directory."""
    import shutil
    import socket

    # Load config for log_bundle setting
    config_path = Path(ns.config).expanduser() if ns.config else None
    config = load_path_config(config_path)

    # Resolve bundle location (CLI > env > config)
    bundle = _resolve_log_bundle(ns.bundle)
    if bundle is None and config.log_bundle is not None:
        bundle = config.log_bundle

    if bundle is None:
        print(
            "Error: No bundle location specified. "
            "Use --bundle, set AGENT_TAYLOR_LOG_BUNDLE, "
            "or configure log_bundle in ~/.config/agent-taylor/paths.toml",
            file=sys.stderr,
        )
        return 1

    # Validate bundle exists and is a directory
    if not bundle.exists():
        print(f"Error: Bundle directory does not exist: {bundle}", file=sys.stderr)
        return 1
    if not bundle.is_dir():
        print(f"Error: Bundle path is not a directory: {bundle}", file=sys.stderr)
        return 1

    # Determine machine name
    machine_name = ns.machine_name if ns.machine_name else socket.gethostname()

    # Create machine directory
    machine_dir = bundle / machine_name
    machine_dir.mkdir(exist_ok=True)

    # Find source directories
    home = Path.home()
    claude_src = home / ".claude"
    codex_src = home / ".codex"

    synced_any = False

    # Sync claude logs
    if claude_src.exists() and claude_src.is_dir():
        claude_dst = machine_dir / "claude"
        shutil.copytree(claude_src, claude_dst, dirs_exist_ok=True)
        print(f"Synced {claude_src} -> {claude_dst}")
        synced_any = True

    # Sync codex logs
    if codex_src.exists() and codex_src.is_dir():
        codex_dst = machine_dir / "codex"
        shutil.copytree(codex_src, codex_dst, dirs_exist_ok=True)
        print(f"Synced {codex_src} -> {codex_dst}")
        synced_any = True

    if not synced_any:
        print("Nothing to sync - no ~/.claude or ~/.codex directories found.")

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
    compare.add_argument(
        "--since",
        default=None,
        help="Only include sessions on or after this date (YYYY-MM-DD).",
    )
    compare.add_argument(
        "--beadhub-since",
        default=None,
        help="Only include beadhub sessions on or after this date (YYYY-MM-DD). "
             "Use to filter to mature beadhub period while keeping all other data.",
    )
    compare.add_argument(
        "--combined",
        action="store_true",
        help="With --history, combine all configurations into single daily totals.",
    )
    compare.add_argument(
        "--graph",
        default=None,
        help="Output productivity graph to file (PNG). Implies --history --combined.",
    )
    compare.add_argument(
        "--projects-csv",
        default=None,
        help="Output project classification data to CSV file.",
    )
    compare.set_defaults(func=_cmd_compare)

    sync = sub.add_parser(
        "sync",
        help="Sync local AI logs to a bundle directory.",
    )
    sync.add_argument(
        "--config",
        default=None,
        help="Path config file for log_bundle setting.",
    )
    sync.add_argument(
        "--bundle",
        default=None,
        help="Bundle directory (default: from env/config).",
    )
    sync.add_argument(
        "--machine-name",
        default=None,
        help="Machine name subdirectory (default: hostname).",
    )
    sync.set_defaults(func=_cmd_sync)

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
