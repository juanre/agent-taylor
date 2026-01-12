from __future__ import annotations

import csv
import math
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class CommitMetrics:
    commit: str
    day: str
    timestamp: int
    added: int
    deleted: int
    files: int
    binary_files: int
    robust_z: float = 0.0
    is_outlier: bool = False

    @property
    def delta(self) -> int:
        return self.added + self.deleted


@dataclass(frozen=True)
class AnalyzeOptions:
    by: str = "committer"  # committer|author
    include_merges: bool = False
    author: Optional[str] = None
    since: Optional[str] = None
    until: Optional[str] = None
    outlier_method: str = "none"  # none|mad-log-delta
    outlier_z: float = 3.5


def _run_git(repo: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git failed: {' '.join(args)}")
    return proc.stdout


def _median_int(values: list[int]) -> int:
    if not values:
        return 0
    return int(statistics.median(values))


def _median_float(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.median(values))


def _percentile_int(values: list[int], p: float) -> int:
    if not values:
        return 0
    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * p
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)
    if f == c:
        return values_sorted[f]
    d0 = values_sorted[f] * (c - k)
    d1 = values_sorted[c] * (k - f)
    return int(round(d0 + d1))


def _mean_seconds(values: list[int]) -> int:
    if not values:
        return 0
    return int(round(sum(values) / len(values)))


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(float(value.strip()))
    raise TypeError(f"Expected int-like value, got {type(value).__name__}")


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value.strip())
    raise TypeError(f"Expected float-like value, got {type(value).__name__}")


def _robust_outliers_mad_log_delta(
    deltas: list[int], z_threshold: float
) -> tuple[list[bool], list[float]]:
    x = [math.log1p(max(0, d)) for d in deltas]
    med = _median_float(x)
    abs_dev = [abs(v - med) for v in x]
    mad = _median_float(abs_dev)
    if mad == 0.0:
        return ([False] * len(deltas), [0.0] * len(deltas))
    z = [(0.6745 * (v - med) / mad) for v in x]
    flags = [abs(v) > z_threshold for v in z]
    return (flags, z)


def _parse_numstat_log(lines: Iterable[str], marker: str) -> list[CommitMetrics]:
    commits: list[CommitMetrics] = []
    current_hash: Optional[str] = None
    current_day: Optional[str] = None
    current_ts: Optional[int] = None
    added = 0
    deleted = 0
    files = 0
    binary_files = 0

    def flush() -> None:
        nonlocal current_hash, current_day, current_ts, added, deleted, files, binary_files
        if current_hash is None or current_day is None or current_ts is None:
            return
        commits.append(
            CommitMetrics(
                commit=current_hash,
                day=current_day,
                timestamp=current_ts,
                added=added,
                deleted=deleted,
                files=files,
                binary_files=binary_files,
            )
        )
        current_hash = None
        current_day = None
        current_ts = None
        added = 0
        deleted = 0
        files = 0
        binary_files = 0

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if not line:
            continue
        if line.startswith(marker):
            flush()
            payload = line[len(marker) :]
            parts = payload.split("\t")
            if len(parts) != 3:
                raise RuntimeError(f"Unexpected commit header: {line!r}")
            current_hash, current_day = parts[0], parts[1]
            try:
                current_ts = int(parts[2])
            except ValueError as e:
                raise RuntimeError(f"Unexpected commit timestamp: {line!r}") from e
            continue

        parts = line.split("\t")
        if len(parts) < 3 or current_hash is None:
            continue

        files += 1
        a, d = parts[0], parts[1]
        if a == "-" or d == "-":
            binary_files += 1
            continue
        try:
            added += int(a)
            deleted += int(d)
        except ValueError:
            continue

    flush()
    return commits


def collect_commit_metrics(repo: Path, options: AnalyzeOptions) -> list[CommitMetrics]:
    repo = repo.expanduser().resolve()
    if not repo.exists():
        raise RuntimeError(f"Repo not found: {repo}")
    _run_git(repo, ["rev-parse", "--git-dir"])

    if options.by not in ("committer", "author"):
        raise RuntimeError(f"Invalid --by: {options.by}")

    date_token = "%cd" if options.by == "committer" else "%ad"
    epoch_token = "%ct" if options.by == "committer" else "%at"
    marker = "<<<GHR_COMMIT>>>\t"

    git_args = [
        "log",
        "--numstat",
        "--date=short",
        f"--pretty=format:{marker}%H\t{date_token}\t{epoch_token}",
    ]
    if not options.include_merges:
        git_args.append("--no-merges")
    if options.author:
        git_args.append(f"--author={options.author}")
    if options.since:
        git_args.append(f"--since={options.since}")
    if options.until:
        git_args.append(f"--until={options.until}")

    out = _run_git(repo, git_args)
    commits = _parse_numstat_log(out.splitlines(), marker=marker)
    commits.sort(key=lambda c: (c.day, c.timestamp, c.commit))

    if commits and options.outlier_method != "none":
        deltas = [c.delta for c in commits]
        if options.outlier_method == "mad-log-delta":
            flags, zscores = _robust_outliers_mad_log_delta(deltas, options.outlier_z)
        else:
            raise RuntimeError(f"Unknown outlier method: {options.outlier_method}")
        updated: list[CommitMetrics] = []
        for c, is_outlier, z in zip(commits, flags, zscores):
            updated.append(
                CommitMetrics(
                    commit=c.commit,
                    day=c.day,
                    timestamp=c.timestamp,
                    added=c.added,
                    deleted=c.deleted,
                    files=c.files,
                    binary_files=c.binary_files,
                    robust_z=z,
                    is_outlier=is_outlier,
                )
            )
        commits = updated

    return commits


def commit_rows(commits: list[CommitMetrics]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for c in commits:
        rows.append(
            {
                "day": c.day,
                "commit": c.commit,
                "timestamp": c.timestamp,
                "files": c.files,
                "binary_files": c.binary_files,
                "added": c.added,
                "deleted": c.deleted,
                "delta": c.delta,
                "is_outlier": int(bool(c.is_outlier)),
                "robust_z": round(c.robust_z, 4),
            }
        )
    return rows


def daily_rows(commits: list[CommitMetrics]) -> list[dict[str, object]]:
    day_to_commits: dict[str, list[CommitMetrics]] = {}
    for c in commits:
        day_to_commits.setdefault(c.day, []).append(c)

    all_intra_day_intervals: list[int] = []
    for day_commits in day_to_commits.values():
        if len(day_commits) < 2:
            continue
        times = sorted(c.timestamp for c in day_commits)
        all_intra_day_intervals.extend([b - a for a, b in zip(times, times[1:]) if b >= a])
    default_prep_seconds = _median_int(all_intra_day_intervals)

    out: list[dict[str, object]] = []
    for day, day_commits in sorted(day_to_commits.items()):
        deltas = [c.delta for c in day_commits]
        deltas_ex_outliers = [c.delta for c in day_commits if not c.is_outlier]
        outlier_commits = sum(1 for c in day_commits if c.is_outlier)

        day_commits_sorted = sorted(day_commits, key=lambda c: c.timestamp)
        first_ts = day_commits_sorted[0].timestamp
        last_ts = day_commits_sorted[-1].timestamp
        span_seconds = max(0, last_ts - first_ts)
        intervals = [
            b.timestamp - a.timestamp
            for a, b in zip(day_commits_sorted, day_commits_sorted[1:])
            if b.timestamp >= a.timestamp
        ]
        avg_seconds_between_commits = _mean_seconds(intervals)
        has_multiple_commits = len(day_commits_sorted) > 1
        prep_seconds = avg_seconds_between_commits if has_multiple_commits else default_prep_seconds
        estimated_work_seconds = span_seconds + prep_seconds

        hours_span = span_seconds / 3600.0
        hours_estimated = estimated_work_seconds / 3600.0
        hours_estimated_strict = (
            (span_seconds + avg_seconds_between_commits) / 3600.0 if has_multiple_commits else None
        )
        commits_count = len(day_commits_sorted)

        out.append(
            {
                "day": day,
                "commits": commits_count,
                "first_ts": first_ts,
                "last_ts": last_ts,
                "span_hours": round(hours_span, 3),
                "avg_seconds_between_commits": avg_seconds_between_commits,
                "prep_seconds": prep_seconds,
                "estimated_hours": round(hours_estimated, 3),
                "estimated_hours_strict": (
                    round(hours_estimated_strict, 3) if hours_estimated_strict is not None else ""
                ),
                "files": sum(c.files for c in day_commits),
                "binary_files": sum(c.binary_files for c in day_commits),
                "added": sum(c.added for c in day_commits),
                "deleted": sum(c.deleted for c in day_commits),
                "delta": sum(deltas),
                "outlier_commits": outlier_commits,
                "delta_ex_outliers": sum(deltas_ex_outliers),
                "commits_per_span_hour": (
                    round(commits_count / hours_span, 2) if hours_span > 0 else ""
                ),
                "delta_per_span_hour": round(sum(deltas) / hours_span, 2) if hours_span > 0 else "",
                "commits_per_estimated_hour": (
                    round(commits_count / hours_estimated, 2) if hours_estimated > 0 else 0
                ),
                "delta_per_estimated_hour": (
                    round(sum(deltas) / hours_estimated, 2) if hours_estimated > 0 else 0
                ),
                "delta_per_estimated_hour_ex_outliers": (
                    round(sum(deltas_ex_outliers) / hours_estimated, 2)
                    if hours_estimated > 0
                    else 0
                ),
                "commits_per_estimated_hour_strict": (
                    round(commits_count / hours_estimated_strict, 2)
                    if (hours_estimated_strict is not None and hours_estimated_strict > 0)
                    else ""
                ),
                "delta_per_estimated_hour_strict": (
                    round(sum(deltas) / hours_estimated_strict, 2)
                    if (hours_estimated_strict is not None and hours_estimated_strict > 0)
                    else ""
                ),
                "delta_per_estimated_hour_strict_ex_outliers": (
                    round(sum(deltas_ex_outliers) / hours_estimated_strict, 2)
                    if (hours_estimated_strict is not None and hours_estimated_strict > 0)
                    else ""
                ),
                "avg_delta_per_commit": round(sum(deltas) / len(deltas), 2) if deltas else 0,
                "median_delta_per_commit": _median_int(deltas),
                "p90_delta_per_commit": _percentile_int(deltas, 0.90),
                "max_delta_per_commit": max(deltas) if deltas else 0,
            }
        )

    return out


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(
    repo: Path,
    options: AnalyzeOptions,
    commits: list[CommitMetrics],
    daily: list[dict[str, object]],
) -> None:
    active_days = len(daily)
    total_commits = len(commits)
    print(f"repo: {repo}")
    print(f"group_by: {options.by}")
    print(f"include_merges: {options.include_merges}")
    print(f"active_days: {active_days}")
    print(f"total_commits: {total_commits}")
    if not daily:
        return

    date_range = (str(daily[0]["day"]), str(daily[-1]["day"]))
    commits_per_day = [_as_int(row["commits"]) for row in daily]
    print(f"date_range: {date_range[0]}..{date_range[1]}")
    print(
        "commits_per_active_day:"
        f" min={min(commits_per_day)}"
        f" median={_median_int(commits_per_day)}"
        f" max={max(commits_per_day)}"
    )

    estimated_hours = [_as_float(row["estimated_hours"]) for row in daily]
    total_estimated_hours = sum(estimated_hours)
    total_delta = sum(c.delta for c in commits)
    total_delta_ex_outliers = sum(c.delta for c in commits if not c.is_outlier)

    # Same heuristic used in daily rollups: median of intra-day intervals on multi-commit days.
    intervals: list[int] = []
    by_day: dict[str, list[int]] = {}
    for c in commits:
        by_day.setdefault(c.day, []).append(c.timestamp)
    for ts in by_day.values():
        if len(ts) < 2:
            continue
        ts_sorted = sorted(ts)
        intervals.extend([b - a for a, b in zip(ts_sorted, ts_sorted[1:]) if b >= a])
    default_prep_seconds = _median_int(intervals)
    print(f"default_prep_seconds: {default_prep_seconds}")
    print(f"total_estimated_hours: {round(total_estimated_hours, 2)}")
    if total_estimated_hours > 0:
        print(
            f"commits_per_estimated_hour_overall: {round(total_commits / total_estimated_hours, 2)}"
        )
        print(f"delta_per_estimated_hour_overall: {round(total_delta / total_estimated_hours, 2)}")
        if options.outlier_method != "none":
            print(
                f"delta_per_estimated_hour_overall_ex_outliers: {round(total_delta_ex_outliers / total_estimated_hours, 2)}"
            )

    strict_hours: list[float] = []
    strict_delta_total = 0
    strict_commits_total = 0
    strict_delta_ex_outliers_total = 0
    for row in daily:
        v = row.get("estimated_hours_strict")
        if v in ("", None):
            continue
        strict_hours.append(_as_float(v))
        strict_commits_total += _as_int(row["commits"])
        strict_delta_total += _as_int(row["delta"])
        strict_delta_ex_outliers_total += _as_int(row.get("delta_ex_outliers", row["delta"]))
    total_strict_hours = sum(strict_hours)
    if total_strict_hours > 0:
        print(
            f"commits_per_estimated_hour_overall_strict: {round(strict_commits_total / total_strict_hours, 2)}"
            " (multi-commit days only)"
        )
        print(
            f"delta_per_estimated_hour_overall_strict: {round(strict_delta_total / total_strict_hours, 2)}"
            " (multi-commit days only)"
        )
        if options.outlier_method != "none":
            print(
                "delta_per_estimated_hour_overall_strict_ex_outliers:"
                f" {round(strict_delta_ex_outliers_total / total_strict_hours, 2)}"
                " (multi-commit days only)"
            )

    if options.outlier_method != "none":
        outliers = sum(1 for c in commits if c.is_outlier)
        print(f"outlier_method: {options.outlier_method} (z>{options.outlier_z})")
        print(f"outlier_commits: {outliers}")

    deltas_per_commit = [c.delta for c in commits]
    if deltas_per_commit:
        print(
            "delta_per_commit:"
            f" median={_median_int(deltas_per_commit)}"
            f" p90={_percentile_int(deltas_per_commit, 0.90)}"
            f" max={max(deltas_per_commit)}"
        )
