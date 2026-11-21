"""No hosting or CI configuration for services this project does not use (I-09).

The owner's rules: the repo stores code and nothing else, GitHub Actions stays off, and
scheduled jobs run by hand. `railway.toml` started modules that do not exist and
`.github/workflows/ci.yml` was a live workflow in a public repo.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_there_is_no_railway_config_and_no_github_workflow() -> None:
    assert not (ROOT / "railway.toml").exists()
    assert not (ROOT / ".github").exists()


def test_nothing_points_at_the_deleted_ci_workflow() -> None:
    files = [
        ROOT / "Makefile",
        ROOT / "DEVELOPMENT.md",
        ROOT / "infra" / "README.md",
        ROOT / "infra" / "run_scheduled.py",
        *(ROOT / "docs").glob("*.md"),
    ]
    for path in files:
        text = path.read_text()
        assert "ci.yml" not in text, path
        assert "railway.toml" not in text, path


def test_the_docs_say_there_is_no_ci() -> None:
    assert "There is no CI" in (ROOT / "infra" / "README.md").read_text()
    head = "\n".join((ROOT / "Makefile").read_text().splitlines()[:4])
    assert "make check" in head


def test_gitignore_has_no_dead_rule_and_no_duplicate_log_line() -> None:
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert not any("manual_settlements" in line for line in lines)
    assert lines.count("*.log") == 1
    assert "data/manual/**/*.csv" in lines  # the rule that does match the real path
