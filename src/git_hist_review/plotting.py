from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


@dataclass(frozen=True)
class RateSeries:
    commits_per_hour: list[float]
    delta_per_hour: list[float]
    date_range: tuple[str, str]


@dataclass(frozen=True)
class ProgressionSeries:
    cumulative_hours: list[float]
    delta_per_hour: list[float]
    rolling_delta_per_hour: list[float]
    date_range: tuple[str, str]


def _parse_float(value: str) -> Optional[float]:
    v = str(value).strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _rolling_mean(values: list[float], window: int) -> list[float]:
    if window <= 1:
        return values[:]
    out: list[float] = []
    buf: list[float] = []
    for v in values:
        buf.append(v)
        if len(buf) > window:
            buf.pop(0)
        out.append(sum(buf) / len(buf))
    return out


def _rolling_weighted_mean_by_hours(
    x_cumulative_hours: list[float],
    values: list[float],
    weights_hours: list[float],
    window_hours: float,
) -> list[float]:
    if window_hours <= 0:
        return values[:]
    out: list[float] = []
    n = len(values)
    for i in range(n):
        window_end = x_cumulative_hours[i]
        window_start = window_end - window_hours
        w_sum = 0.0
        v_sum = 0.0

        # Walk backwards until this day's end is before the window start.
        for j in range(i, -1, -1):
            day_end = x_cumulative_hours[j]
            if day_end <= window_start:
                break
            day_hours = max(0.0, weights_hours[j])
            day_start = day_end - day_hours
            overlap = max(0.0, min(day_end, window_end) - max(day_start, window_start))
            if overlap <= 0:
                continue
            w_sum += overlap
            v_sum += values[j] * overlap

        out.append(v_sum / w_sum if w_sum > 0 else values[i])
    return out


def _choose_log_scale(values: list[float], threshold_ratio: float = 50.0) -> bool:
    xs = [v for v in values if v > 0]
    if len(xs) < 8:
        return False
    xs_sorted = sorted(xs)
    median = xs_sorted[len(xs_sorted) // 2]
    mx = xs_sorted[-1]
    if median <= 0:
        return False
    return mx / median >= threshold_ratio


def load_rates_from_daily_csv(daily_csv: Path, hours: str) -> RateSeries:
    daily_csv = daily_csv.expanduser().resolve()
    with daily_csv.open("r", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"No rows in daily CSV: {daily_csv}")

    rows.sort(key=lambda r: str(r.get("day", "")))
    date_range = (str(rows[0].get("day", "")), str(rows[-1].get("day", "")))

    if hours not in ("estimated", "strict"):
        raise RuntimeError(f"Invalid hours mode: {hours}")

    commits_key = (
        "commits_per_estimated_hour"
        if hours == "estimated"
        else "commits_per_estimated_hour_strict"
    )
    delta_key = (
        "delta_per_estimated_hour_ex_outliers"
        if hours == "estimated"
        else "delta_per_estimated_hour_strict_ex_outliers"
    )
    delta_raw_key = (
        "delta_per_estimated_hour" if hours == "estimated" else "delta_per_estimated_hour_strict"
    )

    has_delta_ex = delta_key in rows[0]

    commits: list[float] = []
    delta: list[float] = []

    for r in rows:
        c = _parse_float(str(r.get(commits_key, "")))
        d = _parse_float(str(r.get(delta_key, ""))) if has_delta_ex else None
        d_raw = _parse_float(str(r.get(delta_raw_key, "")))

        # Strict series has blanks for single-commit days; drop those rows entirely.
        if hours == "strict" and c is None:
            continue

        if c is None:
            raise RuntimeError(f"Missing {commits_key} in row for day={r.get('day')}")
        commits.append(c)

        if d is None:
            if d_raw is None:
                raise RuntimeError(f"Missing delta/hour columns in row for day={r.get('day')}")
            delta.append(d_raw)
        else:
            delta.append(d)

    return RateSeries(
        commits_per_hour=commits,
        delta_per_hour=delta,
        date_range=date_range,
    )


def load_progression_from_daily_csv(
    daily_csv: Path,
    hours: str,
    window_hours: float,
) -> ProgressionSeries:
    daily_csv = daily_csv.expanduser().resolve()
    with daily_csv.open("r", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"No rows in daily CSV: {daily_csv}")

    rows.sort(key=lambda r: str(r.get("day", "")))
    date_range = (str(rows[0].get("day", "")), str(rows[-1].get("day", "")))

    if hours not in ("estimated", "strict"):
        raise RuntimeError(f"Invalid hours mode: {hours}")

    hours_key = "estimated_hours" if hours == "estimated" else "estimated_hours_strict"
    delta_key = (
        "delta_per_estimated_hour_ex_outliers"
        if hours == "estimated"
        else "delta_per_estimated_hour_strict_ex_outliers"
    )
    delta_raw_key = (
        "delta_per_estimated_hour" if hours == "estimated" else "delta_per_estimated_hour_strict"
    )

    has_delta_ex = delta_key in rows[0]

    per_day_hours: list[float] = []
    delta_per_hour: list[float] = []

    for r in rows:
        h = _parse_float(str(r.get(hours_key, "")))
        d_ex = _parse_float(str(r.get(delta_key, ""))) if has_delta_ex else None
        d_raw = _parse_float(str(r.get(delta_raw_key, "")))

        if hours == "strict" and (h is None or h <= 0):
            continue

        if h is None or h <= 0:
            raise RuntimeError(f"Missing/invalid {hours_key} in row for day={r.get('day')}")
        per_day_hours.append(h)

        if d_ex is None:
            if d_raw is None:
                raise RuntimeError(f"Missing delta/hour columns in row for day={r.get('day')}")
            delta_per_hour.append(d_raw)
        else:
            delta_per_hour.append(d_ex)

    cumulative_hours: list[float] = []
    total = 0.0
    for h in per_day_hours:
        total += h
        cumulative_hours.append(total)

    rolling = _rolling_weighted_mean_by_hours(
        x_cumulative_hours=cumulative_hours,
        values=delta_per_hour,
        weights_hours=per_day_hours,
        window_hours=window_hours,
    )

    return ProgressionSeries(
        cumulative_hours=cumulative_hours,
        delta_per_hour=delta_per_hour,
        rolling_delta_per_hour=rolling,
        date_range=date_range,
    )


def plot_rates_png(
    rates: RateSeries,
    output_png: Path,
    title: str,
    rolling_window: int = 7,
    dpi: int = 160,
) -> None:
    output_png = output_png.expanduser().resolve()
    output_png.parent.mkdir(parents=True, exist_ok=True)

    x = list(range(1, len(rates.commits_per_hour) + 1))
    commits_roll = _rolling_mean(rates.commits_per_hour, rolling_window)
    delta_roll = _rolling_mean(rates.delta_per_hour, rolling_window)

    fig, (ax1, ax2) = plt.subplots(nrows=2, ncols=1, figsize=(12, 7), sharex=True)
    fig.suptitle(title, fontsize=14, fontweight="semibold")

    ax1.plot(x, rates.commits_per_hour, color="#2563eb", linewidth=1.8, label="commits/hour")
    if rolling_window > 1:
        ax1.plot(
            x,
            commits_roll,
            color="#2563eb",
            linewidth=1.6,
            alpha=0.35,
            linestyle="--",
            label=f"{rolling_window}-day mean",
        )
    ax1.set_ylabel("commits/hour")
    ax1.grid(True, axis="y", alpha=0.25)
    ax1.legend(loc="upper left", fontsize=9, frameon=False)

    ax2.plot(x, rates.delta_per_hour, color="#111827", linewidth=1.8, label="delta/hour")
    if rolling_window > 1:
        ax2.plot(
            x,
            delta_roll,
            color="#111827",
            linewidth=1.6,
            alpha=0.35,
            linestyle="--",
            label=f"{rolling_window}-day mean",
        )
    ax2.set_ylabel("delta/hour (added+deleted)")
    ax2.set_xlabel("active day index")
    ax2.grid(True, axis="y", alpha=0.25)
    ax2.legend(loc="upper left", fontsize=9, frameon=False)

    if _choose_log_scale(rates.delta_per_hour):
        ax2.set_yscale("log")
        ax2.set_ylabel("delta/hour (log scale)")

    fig.text(0.5, 0.01, f"active days: {len(x)}", ha="center", fontsize=9, color="#555")

    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    fig.savefig(output_png, dpi=dpi)
    plt.close(fig)


def plot_delta_progression_png(
    series: ProgressionSeries,
    output_png: Path,
    title: str,
    dpi: int = 160,
    log_y: bool = False,
) -> None:
    output_png = output_png.expanduser().resolve()
    output_png.parent.mkdir(parents=True, exist_ok=True)

    x = series.cumulative_hours
    y_raw = series.delta_per_hour
    y_roll = series.rolling_delta_per_hour

    fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(12, 4.5))
    fig.suptitle(title, fontsize=14, fontweight="semibold")

    ax.plot(
        x, y_raw, color="#9ca3af", linewidth=1.0, alpha=0.35, label="delta/hour (per active day)"
    )
    ax.plot(x, y_roll, color="#111827", linewidth=2.2, label="rolling mean (hour-weighted)")

    ax.set_xlabel("cumulative estimated hours")
    ax.set_ylabel("delta/hour (added+deleted)")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="upper left", fontsize=9, frameon=False)

    if log_y or _choose_log_scale(y_raw):
        ax.set_yscale("log")
        ax.set_ylabel("delta/hour (log scale)")

    fig.text(0.5, 0.02, f"active days: {len(x)}", ha="center", fontsize=9, color="#555")

    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    fig.savefig(output_png, dpi=dpi)
    plt.close(fig)
