## agent-taylor

Utilities to analyze a git repository’s commit history and produce:

- `commit_metrics.csv`: per-commit added/deleted/delta, plus optional outlier flags
- `daily_metrics.csv`: per-active-day rollups, including `commits/hour` and `delta/hour`
- `rates_over_time.png`: commits/hour and delta/hour over active days (PNG via matplotlib)

This is designed for “agentic programming” productivity studies where you care about *rates* and want a robust way
to down-weight or exclude extreme bulk-change commits.

### Install (uv)

From this repo:

```bash
uv sync
```

### Commands

#### Analyze a repo

```bash
uv run agent-taylor analyze \
  --repo ../beadhub \
  --output-dir out/beadhub-history \
  --outlier-method mad-log-delta
```

Outputs:

- `out/beadhub-history/commit_metrics.csv`
- `out/beadhub-history/daily_metrics.csv`

Outliers:

- `--outlier-method mad-log-delta` flags per-commit outliers using a robust z-score computed from MAD on `log1p(delta)`
- `--outlier-z` controls the threshold (default `3.5`)

Hours:

- `estimated_hours` = (last_commit - first_commit) + “prep time”
- `estimated_hours_strict` only exists for multi-commit days

#### Plot commits/hour and delta/hour (PNG)

```bash
uv run agent-taylor plot-rates \
  --daily-csv out/beadhub-history/daily_metrics.csv \
  --output-png out/beadhub-history/rates_over_time.png \
  --hours estimated \
  --rolling-window 7
```

Notes:

- The x-axis is the **active day index** (days without commits are not included).
- Delta/hour uses the outlier-excluded column when available.

#### Plot delta/hour progression vs cumulative hours (PNG)

This is the “efficiency over time” plot: x is cumulative estimated hours across *active* days only; y is a rolling
mean of delta/hour.

```bash
uv run agent-taylor plot-progression \
  --daily-csv out/beadhub-history/daily_metrics.csv \
  --output-png out/beadhub-history/delta_progression.png \
  --hours estimated \
  --window-hours 40
```

#### Estimate work hours from AI assistant logs

Git commit timestamps are unreliable for estimating work hours. If you commit at 9am and 8pm, the
commit-based estimate counts 11 hours of work when you may have only worked two separate sessions.

The `ai-hours` command solves this by parsing conversation logs from Claude Code and Codex to
detect actual work sessions.

```bash
uv run agent-taylor ai-hours --output-dir out/ai-hours
uv run agent-taylor ai-hours --project beadhub --output-dir out/ai-hours
```

Outputs:

- `ai_sessions.csv`: Hours per project per day
- `ai_sittings.csv`: Total active hours per day (across all projects)

##### How it works

The tool parses conversation logs from:

- **Claude Code**: `~/.claude/projects/*/` session files
- **Codex**: `~/.codex/sessions/YYYY/MM/DD/` session files

It detects two levels of work periods:

**Sessions** (per project):

A session is a continuous work period on a single project. A new session starts when the gap
between an assistant's reply and your next message is **≥ 5 minutes**. This threshold assumes
that if you don't respond within 5 minutes, you've switched context.

Each session includes **3 minutes of thinking time** prepended to account for the work you did
before sending your first message in that session.

**Sittings** (across all projects):

A sitting is a continuous work period at your desk, potentially spanning multiple projects.
A new sitting starts when there's **≥ 20 minutes** without any AI interaction (regardless of project).

Each sitting includes **3 minutes of preparation time** prepended.

##### Example

```
9:00-9:30   beadhub     (session 1)
9:32-10:00  llmring     (session 1)
10:02-10:30 beadhub     (session 2)
    -- 45 min gap --
11:15-12:00 beadhub     (session 3)
```

- **Sessions**: beadhub has 3 sessions, llmring has 1 session
- **Sittings**: 2 sittings (9:00-10:30, 11:15-12:00)
- **Session hours for beadhub**: (30 + 3) + (28 + 3) + (45 + 3) = 112 min ≈ 1.87h
- **Sitting hours**: (90 + 3) + (45 + 3) = 141 min ≈ 2.35h

##### Output columns

`ai_sessions.csv`:

| Column | Description |
|--------|-------------|
| day | Date (YYYY-MM-DD) |
| project | Project name (last path element) |
| session_hours | Total hours worked on this project this day |
| sessions | Number of sessions |
| interactions | Number of messages exchanged |

`ai_sittings.csv`:

| Column | Description |
|--------|-------------|
| day | Date (YYYY-MM-DD) |
| sitting_hours | Total active hours this day |
| sittings | Number of sittings |
| interactions | Total messages across all projects |
| projects | Semicolon-separated list of projects touched |

#### Combine git metrics with AI hours

The `combine` command joins git metrics (delta, commits) with AI-based hours to compute accurate
productivity rates.

**Why this matters**: Git commit timestamps can wildly overestimate work hours. If you commit at
9am and 8pm, git-based methods count 11 hours of work when you may have only worked two separate
1-hour sessions. The AI-based hours from `ai-hours` provide accurate timing.

```bash
# Single project: beadhub delta per AI session hour
uv run agent-taylor combine \
  --git-daily out/beadhub-history/daily_metrics.csv \
  --ai-sessions out/beadhub-history/ai_sessions.csv \
  --project beadhub \
  --since 2025-12-11 \
  --output-dir out/beadhub-combined

# Multiple repos: aggregate all beadhub-* repos vs sitting time
uv run agent-taylor combine \
  --git-daily out/beadhub-history/daily_metrics.csv out/beadhub-be/daily_metrics.csv \
  --ai-sittings out/ai-hours-all/ai_sittings.csv \
  --since 2025-12-11 \
  --output-dir out/combined-all
```

**Important**: Use `--since` to limit analysis to dates where you have complete AI log coverage.
Check your AI log date ranges with `ai-hours` first.

##### Output

`combined_session.csv` or `combined_sitting.csv`:

| Column | Description |
|--------|-------------|
| day | Date (YYYY-MM-DD) |
| commits | Number of commits |
| delta | Lines added + deleted |
| delta_ex_outliers | Delta excluding outlier commits |
| ai_hours | Hours from AI assistant logs |
| delta_per_ai_hour | delta / ai_hours |
| delta_per_ai_hour_ex_outliers | delta_ex_outliers / ai_hours |

##### Example comparison

Git-based vs AI-based productivity measurement for the same period:

| Metric | Git-based | AI-based |
|--------|-----------|----------|
| Hours estimated | 300.9 | 96.7 |
| delta/hour | 831 | 2,585 |
| commits/hour | 2.85 | 8.85 |

The git commit-timestamp method overcounted hours by 3.1x, making productivity appear 3x lower
than actual.

#### Unified productivity analysis (recommended)

The `productivity` command automatically detects git repos from your AI assistant logs and combines
everything in one step. This is the recommended way to measure productivity.

```bash
uv run agent-taylor productivity \
  --author "Your Name" \
  --output-dir out/productivity \
  --verbose
```

**How it works:**

1. Parses AI logs from Claude Code (`~/.claude/`) and Codex (`~/.codex/`)
2. Detects the earliest date from each source and uses the later one as start date
3. Extracts working directory paths from each conversation
4. Detects git repos from those paths (runs `git rev-parse --show-toplevel`)
5. Analyzes each discovered repo for commits matching your author filter
6. Combines git metrics with AI session hours
7. Outputs unified productivity CSV

**Automatic date range detection:**

When `--since` is not specified, the command automatically determines the start date by finding
the earliest log entry from both Claude Code and Codex, then using the *later* of the two. This
ensures you only analyze periods where both log sources have complete data.

**Options:**

| Flag | Description |
|------|-------------|
| `--author` | **Required.** Filter commits by author regex |
| `--since` | Start date (YYYY-MM-DD). Auto-detected if not specified. |
| `--until` | End date (YYYY-MM-DD) |
| `--output-dir` | Output directory (default: `out/productivity`) |
| `--config` | Path config for remapping/ignoring paths |
| `--verbose` | Show source date ranges and detected repos |
| `--outlier-method` | Outlier detection method (default: `mad-log-delta`) |

**Output (with --verbose):**

```
claude_logs_start: 2025-01-15
codex_logs_start: 2025-06-01
effective_start_date: 2025-06-01
repos_detected: 3
  - beadhub (/Users/name/prj/beadhub)
  - llmring (/Users/name/prj/llmring)
  - pgdbm (/Users/name/prj/pgdbm)
date_range: 2025-06-01..2026-01-12
days_analyzed: 28
total_commits: 342
total_ai_hours: 96.7
delta_per_ai_hour: 924.8
csv: out/productivity/productivity.csv
```

##### Path configuration (optional)

If you've moved repos or want to ignore certain paths, create a config file at
`~/.config/agent-taylor/paths.toml`:

```toml
[remap]
"/old/path/to/repo" = "/new/path/to/repo"

[ignore]
paths = ["/tmp", "/Users/name/Downloads"]
```

#### Beads usage (optional)

Reports the size of `.beads/beads.db` and counts beads via `.beads/issues.jsonl` line count.

```bash
uv run agent-taylor beads ~/prj/llmring-all/llmring ~/prj/llmring-all/llmring-api --output-csv out/beads.csv
```
