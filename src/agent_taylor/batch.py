from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from .git_metrics import AnalyzeOptions, collect_commit_metrics, daily_rows


def analyze_repos(
    repos: list[Path],
    options: AnalyzeOptions,
) -> dict[str, list[dict[str, object]]]:
    """Analyze multiple repos and return daily metrics keyed by repo name."""
    results: dict[str, list[dict[str, object]]] = {}
    for repo in repos:
        repo = repo.expanduser().resolve()
        if not repo.exists():
            continue
        try:
            commits = collect_commit_metrics(repo, options)
            if commits:
                daily = daily_rows(commits)
                results[repo.name] = daily
        except RuntimeError:
            continue
    return results


def aggregate_daily_metrics(
    all_daily: dict[str, list[dict[str, object]]]
) -> list[dict[str, object]]:
    """Aggregate daily metrics from multiple repos into combined daily totals."""
    by_day: dict[str, dict[str, int]] = {}

    for repo_name, daily in all_daily.items():
        for row in daily:
            day = str(row.get("day", ""))
            if not day:
                continue

            if day not in by_day:
                by_day[day] = {
                    "commits": 0,
                    "files": 0,
                    "added": 0,
                    "deleted": 0,
                    "delta": 0,
                    "delta_ex_outliers": 0,
                    "outlier_commits": 0,
                }

            by_day[day]["commits"] += int(str(row.get("commits", 0)))
            by_day[day]["files"] += int(str(row.get("files", 0)))
            by_day[day]["added"] += int(str(row.get("added", 0)))
            by_day[day]["deleted"] += int(str(row.get("deleted", 0)))
            by_day[day]["delta"] += int(str(row.get("delta", 0)))
            by_day[day]["delta_ex_outliers"] += int(
                str(row.get("delta_ex_outliers", row.get("delta", 0)))
            )
            by_day[day]["outlier_commits"] += int(str(row.get("outlier_commits", 0)))

    # Convert to list of dicts
    result: list[dict[str, object]] = []
    for day in sorted(by_day.keys()):
        data = by_day[day]
        result.append(
            {
                "day": day,
                "commits": data["commits"],
                "files": data["files"],
                "added": data["added"],
                "deleted": data["deleted"],
                "delta": data["delta"],
                "delta_ex_outliers": data["delta_ex_outliers"],
                "outlier_commits": data["outlier_commits"],
            }
        )

    return result


def write_aggregated_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write aggregated daily metrics to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "day",
        "commits",
        "files",
        "added",
        "deleted",
        "delta",
        "delta_ex_outliers",
        "outlier_commits",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_batch_summary(
    all_daily: dict[str, list[dict[str, object]]],
    aggregated: list[dict[str, object]],
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> None:
    """Print summary of batch analysis."""
    # Filter aggregated by date range
    filtered = aggregated
    if since:
        filtered = [r for r in filtered if str(r["day"]) >= since]
    if until:
        filtered = [r for r in filtered if str(r["day"]) <= until]

    if not filtered:
        print("No data in specified date range")
        return

    total_commits = sum(int(str(r["commits"])) for r in filtered)
    total_delta = sum(int(str(r["delta"])) for r in filtered)
    total_delta_ex = sum(int(str(r["delta_ex_outliers"])) for r in filtered)
    active_days = len(filtered)

    print(f"repos_analyzed: {len(all_daily)}")
    for repo_name in sorted(all_daily.keys()):
        print(f"  - {repo_name}")
    print(f"date_range: {filtered[0]['day']}..{filtered[-1]['day']}")
    print(f"active_days: {active_days}")
    print(f"total_commits: {total_commits}")
    print(f"total_delta: {total_delta}")
    print(f"total_delta_ex_outliers: {total_delta_ex}")
