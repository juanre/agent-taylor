# ABOUTME: Shared pytest fixtures for agent-taylor tests.
# ABOUTME: Provides git repo fixtures and path helpers for testing.

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with one commit.

    Returns the path to the repo root.
    """
    repo = tmp_path / "test-repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Create a file and commit
    (repo / "README.md").write_text("# Test Repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


@pytest.fixture
def non_git_dir(tmp_path: Path) -> Path:
    """Create a temporary directory that is NOT a git repository."""
    non_git = tmp_path / "not-a-repo"
    non_git.mkdir()
    (non_git / "some_file.txt").write_text("hello\n")
    return non_git
