from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CombinedDailyMetrics:
    """Combined git metrics and AI hours for a single day."""

    day: str
    commits: int
    delta: int
    delta_ex_outliers: int
    ai_hours: float
    delta_per_ai_hour: float
    delta_per_ai_hour_ex_outliers: float


@dataclass(frozen=True)
class CombinedSummary:
    """Summary statistics for combined analysis."""

    date_range: tuple[str, str]
    days_analyzed: int
    total_commits: int
    total_delta: int
    total_delta_ex_outliers: int
    total_ai_hours: float
    delta_per_ai_hour: float
    delta_per_ai_hour_ex_outliers: float
    commits_per_ai_hour: float


def _parse_float(value: str) -> float:
    """Parse float, returning 0.0 for empty strings."""
    v = str(value).strip()
    if v == "":
        return 0.0
    return float(v)


def _parse_int(value: str) -> int:
    """Parse int, returning 0 for empty strings."""
    v = str(value).strip()
    if v == "":
        return 0
    return int(float(v))


def load_git_daily(csv_path: Path) -> dict[str, dict[str, object]]:
    """Load git daily metrics CSV into dict keyed by day."""
    csv_path = csv_path.expanduser().resolve()
    result: dict[str, dict[str, object]] = {}
    with csv_path.open("r", newline="") as f:
        for row in csv.DictReader(f):
            day = str(row.get("day", ""))
            if day:
                result[day] = dict(row)
    return result


def _project_matches(project_name: str, filter_spec: str) -> bool:
    """Check if project_name matches the filter specification.

    Filter can be:
    - Exact match: "beadhub" matches only "beadhub"
    - Prefix match: "beadhub*" matches "beadhub", "beadhub-be", etc.
    - Multiple (comma-separated): "llmring,pgdbm" matches either
    """
    if "," in filter_spec:
        # Multiple filters
        return any(_project_matches(project_name, f.strip()) for f in filter_spec.split(","))
    if filter_spec.endswith("*"):
        # Prefix match
        return project_name.startswith(filter_spec[:-1])
    # Exact match
    return project_name == filter_spec


def load_ai_sessions(csv_path: Path, project: Optional[str] = None) -> dict[str, float]:
    """Load AI sessions CSV into dict of day -> hours.

    If project is specified, only include rows matching that project.
    Supports exact match, prefix match (ending with *), and comma-separated list.
    """
    csv_path = csv_path.expanduser().resolve()
    result: dict[str, float] = {}
    with csv_path.open("r", newline="") as f:
        for row in csv.DictReader(f):
            row_project = row.get("project", "")
            if project and not _project_matches(row_project, project):
                continue
            day = str(row.get("day", ""))
            hours = _parse_float(str(row.get("session_hours", "0")))
            if day:
                result[day] = result.get(day, 0.0) + hours
    return result


def load_ai_sittings(csv_path: Path) -> dict[str, float]:
    """Load AI sittings CSV into dict of day -> hours."""
    csv_path = csv_path.expanduser().resolve()
    result: dict[str, float] = {}
    with csv_path.open("r", newline="") as f:
        for row in csv.DictReader(f):
            day = str(row.get("day", ""))
            hours = _parse_float(str(row.get("sitting_hours", "0")))
            if day:
                result[day] = hours
    return result


def combine_metrics(
    git_daily: dict[str, dict[str, object]],
    ai_hours: dict[str, float],
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> list[CombinedDailyMetrics]:
    """Combine git metrics with AI hours.

    Only includes days present in BOTH datasets.
    """
    # Find common days
    common_days = set(git_daily.keys()) & set(ai_hours.keys())

    # Apply date filters
    if since:
        common_days = {d for d in common_days if d >= since}
    if until:
        common_days = {d for d in common_days if d <= until}

    results: list[CombinedDailyMetrics] = []
    for day in sorted(common_days):
        git = git_daily[day]
        hours = ai_hours[day]

        commits = _parse_int(str(git.get("commits", 0)))
        delta = _parse_int(str(git.get("delta", 0)))
        delta_ex = _parse_int(str(git.get("delta_ex_outliers", git.get("delta", 0))))

        if hours > 0:
            delta_per_hour = delta / hours
            delta_per_hour_ex = delta_ex / hours
        else:
            delta_per_hour = 0.0
            delta_per_hour_ex = 0.0

        results.append(
            CombinedDailyMetrics(
                day=day,
                commits=commits,
                delta=delta,
                delta_ex_outliers=delta_ex,
                ai_hours=round(hours, 2),
                delta_per_ai_hour=round(delta_per_hour, 1),
                delta_per_ai_hour_ex_outliers=round(delta_per_hour_ex, 1),
            )
        )

    return results


def compute_summary(metrics: list[CombinedDailyMetrics]) -> Optional[CombinedSummary]:
    """Compute summary statistics from combined metrics."""
    if not metrics:
        return None

    total_commits = sum(m.commits for m in metrics)
    total_delta = sum(m.delta for m in metrics)
    total_delta_ex = sum(m.delta_ex_outliers for m in metrics)
    total_hours = sum(m.ai_hours for m in metrics)

    return CombinedSummary(
        date_range=(metrics[0].day, metrics[-1].day),
        days_analyzed=len(metrics),
        total_commits=total_commits,
        total_delta=total_delta,
        total_delta_ex_outliers=total_delta_ex,
        total_ai_hours=round(total_hours, 1),
        delta_per_ai_hour=round(total_delta / total_hours, 1) if total_hours > 0 else 0.0,
        delta_per_ai_hour_ex_outliers=(
            round(total_delta_ex / total_hours, 1) if total_hours > 0 else 0.0
        ),
        commits_per_ai_hour=round(total_commits / total_hours, 2) if total_hours > 0 else 0.0,
    )


def write_combined_csv(path: Path, metrics: list[CombinedDailyMetrics]) -> None:
    """Write combined metrics to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "day",
                "commits",
                "delta",
                "delta_ex_outliers",
                "ai_hours",
                "delta_per_ai_hour",
                "delta_per_ai_hour_ex_outliers",
            ],
        )
        writer.writeheader()
        for m in metrics:
            writer.writerow(
                {
                    "day": m.day,
                    "commits": m.commits,
                    "delta": m.delta,
                    "delta_ex_outliers": m.delta_ex_outliers,
                    "ai_hours": m.ai_hours,
                    "delta_per_ai_hour": m.delta_per_ai_hour,
                    "delta_per_ai_hour_ex_outliers": m.delta_per_ai_hour_ex_outliers,
                }
            )


def print_combined_summary(summary: CombinedSummary) -> None:
    """Print combined analysis summary."""
    print(f"date_range: {summary.date_range[0]}..{summary.date_range[1]}")
    print(f"days_analyzed: {summary.days_analyzed}")
    print(f"total_commits: {summary.total_commits}")
    print(f"total_delta: {summary.total_delta}")
    print(f"total_delta_ex_outliers: {summary.total_delta_ex_outliers}")
    print(f"total_ai_hours: {summary.total_ai_hours}")
    print(f"commits_per_ai_hour: {summary.commits_per_ai_hour}")
    print(f"delta_per_ai_hour: {summary.delta_per_ai_hour}")
    print(f"delta_per_ai_hour_ex_outliers: {summary.delta_per_ai_hour_ex_outliers}")


def aggregate_git_dailies(csv_paths: list[Path]) -> dict[str, dict[str, object]]:
    """Aggregate multiple git daily CSVs into one.

    Sums commits, delta, etc. per day across all repos.
    """
    aggregated: dict[str, dict[str, int]] = {}

    for csv_path in csv_paths:
        git_daily = load_git_daily(csv_path)
        for day, row in git_daily.items():
            if day not in aggregated:
                aggregated[day] = {
                    "commits": 0,
                    "delta": 0,
                    "delta_ex_outliers": 0,
                    "files": 0,
                    "added": 0,
                    "deleted": 0,
                }
            aggregated[day]["commits"] += _parse_int(str(row.get("commits", 0)))
            aggregated[day]["delta"] += _parse_int(str(row.get("delta", 0)))
            aggregated[day]["delta_ex_outliers"] += _parse_int(
                str(row.get("delta_ex_outliers", row.get("delta", 0)))
            )
            aggregated[day]["files"] += _parse_int(str(row.get("files", 0)))
            aggregated[day]["added"] += _parse_int(str(row.get("added", 0)))
            aggregated[day]["deleted"] += _parse_int(str(row.get("deleted", 0)))

    # Convert to expected format
    result: dict[str, dict[str, object]] = {}
    for day, data in aggregated.items():
        result[day] = {
            "day": day,
            "commits": data["commits"],
            "delta": data["delta"],
            "delta_ex_outliers": data["delta_ex_outliers"],
            "files": data["files"],
            "added": data["added"],
            "deleted": data["deleted"],
        }
    return result
