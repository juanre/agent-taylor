from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoBeadsMetrics:
    repo: str
    beads_dir: str
    beads_total_bytes: int
    beads_db_bytes: int
    beads_db_wal_bytes: int
    beads_db_shm_bytes: int
    issues_jsonl_bytes: int
    issues_jsonl_lines: int


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _count_lines(path: Path) -> int:
    try:
        with path.open("rb") as f:
            return sum(chunk.count(b"\n") for chunk in iter(lambda: f.read(1024 * 1024), b""))
    except FileNotFoundError:
        return 0


def _dir_total_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def gather_beads_metrics(repo: Path) -> RepoBeadsMetrics:
    repo = repo.expanduser().resolve()
    beads = repo / ".beads"
    db = beads / "beads.db"
    wal = beads / "beads.db-wal"
    shm = beads / "beads.db-shm"
    issues = beads / "issues.jsonl"

    return RepoBeadsMetrics(
        repo=str(repo),
        beads_dir=str(beads),
        beads_total_bytes=_dir_total_bytes(beads),
        beads_db_bytes=_file_size(db),
        beads_db_wal_bytes=_file_size(wal),
        beads_db_shm_bytes=_file_size(shm),
        issues_jsonl_bytes=_file_size(issues),
        issues_jsonl_lines=_count_lines(issues),
    )


def write_beads_csv(path: Path, metrics: list[RepoBeadsMetrics]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "repo",
                "beads_total_bytes",
                "beads_db_bytes",
                "beads_db_wal_bytes",
                "beads_db_shm_bytes",
                "issues_jsonl_lines",
                "issues_jsonl_bytes",
            ],
        )
        writer.writeheader()
        for m in metrics:
            writer.writerow(
                {
                    "repo": m.repo,
                    "beads_total_bytes": m.beads_total_bytes,
                    "beads_db_bytes": m.beads_db_bytes,
                    "beads_db_wal_bytes": m.beads_db_wal_bytes,
                    "beads_db_shm_bytes": m.beads_db_shm_bytes,
                    "issues_jsonl_lines": m.issues_jsonl_lines,
                    "issues_jsonl_bytes": m.issues_jsonl_bytes,
                }
            )


def human_bytes(n: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    v = float(n)
    for u in units:
        if v < 1024 or u == units[-1]:
            return f"{int(v)} B" if u == "B" else f"{v:.2f} {u}"
        v /= 1024.0
    return f"{n} B"
