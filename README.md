## agent-taylor

Compares AI-assisted programming productivity across different tool configurations:
- **none**: No beads, no beadhub
- **beads**: Using beads for issue tracking
- **beads+beadhub**: Using beads plus beadhub repos

The tool analyzes your actual work sessions (from Claude Code and Codex logs) and matches them with git commits to compute accurate productivity metrics.

### Install

```bash
uv sync
```

### Compare productivity across configurations

```bash
uv run agent-taylor compare --author "Your Name" --verbose
```

**How it works:**

1. Parses AI conversation logs from Claude Code (`~/.claude/`) and Codex (`~/.codex/`)
2. Detects the earliest date from each source and uses the later one as start date
3. Extracts working directory paths from conversations to discover git repos
4. For each work session, classifies it by configuration:
   - Checks if the repo has `.beads/` committed (beads adoption date)
   - Checks if the repo name is `beadhub` or starts with `beadhub-`
5. Gets git commits that occurred during each session's time window
6. Aggregates metrics by configuration

**Why session-based measurement matters:**

Daily aggregation loses precision when you work on multiple projects concurrently. Sessions allow proper attribution of commits to the specific tool configuration active at that time.

**Output:**

```
claude_logs_start: 2025-12-09
codex_logs_start: 2025-10-31
effective_start_date: 2025-12-09
repos_detected: 10
  - beadhub (/Users/name/prj/beadhub)
  - llmring (/Users/name/prj/llmring)
  ...
  beadhub: beads: 2025-11-30, beadhub repo
sessions_skipped_no_repo: 47
sessions_skipped_before_start: 22

configuration    sessions    hours  commits      delta   delta/hr commits/hr
----------------------------------------------------------------------------------
none                   13      2.0        3       2232     1114.5       1.50
beads                  83     16.0       65      33378     2083.2       4.06
beads+beadhub          39      5.3        9       8318     1567.7       1.70
```

**Options:**

| Flag | Description |
|------|-------------|
| `--author` | **Required.** Filter commits by author regex |
| `--config` | Path config for remapping/ignoring paths |
| `--claude-dir` | Claude Code config dir (default: `~/.claude`) |
| `--codex-dir` | Codex config dir (default: `~/.codex`) |
| `--verbose` | Show detected repos, adoption dates, and skipped sessions |
| `--history` | Show daily breakdown over time (skips empty days) |

### Path configuration (optional)

If you've moved repos or want to ignore certain paths, create a config file at
`~/.config/agent-taylor/paths.toml`:

```toml
[remap]
"/old/path/to/repo" = "/new/path/to/repo"

[ignore]
paths = ["/tmp", "/Users/name/Downloads"]
```

### Beads usage metrics

Reports the size of `.beads/beads.db` and counts issues via `.beads/issues.jsonl` line count.

```bash
uv run agent-taylor beads ~/prj/repo1 ~/prj/repo2 --output-csv out/beads.csv
```

### How sessions are detected

The tool parses conversation logs from:
- **Claude Code**: `~/.claude/projects/*/` session files
- **Codex**: `~/.codex/sessions/YYYY/MM/DD/` session files

A **session** is a continuous work period on a single project. A new session starts when the gap between an assistant's reply and your next message is **≥ 5 minutes**.

Each session includes **3 minutes of thinking time** prepended to account for work before your first message.

### Configuration detection

- **beads**: Detected by finding the first commit that added `.beads/` to the repo
- **beadhub**: Detected by repo name (`beadhub` or `beadhub-*`)

A session is classified based on the repo's configuration state at the time the session started.
