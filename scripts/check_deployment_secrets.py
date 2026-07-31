from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


IGNORED_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "__pycache__",
    "pytest-of-root",
    "node_modules",
    "dist",
    "tmp",
    "tests",
}

SAFE_ENV_EXAMPLES = {".env.example"}
SENSITIVE_SUFFIXES = {".dump", ".backup", ".sql"}
SAFE_SQL_FILES = {"app/docs/database/database_schema.sql"}
TEXT_SUFFIXES = {
    ".env",
    ".example",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

SECRET_PATTERNS = (
    ("OpenAI API key", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("OrderPro token assignment", re.compile(r"^\s*(?:\$env:)?ORDERPRO_API_TOKEN\s*=\s*[^\s#]+", re.IGNORECASE)),
    ("Bearer token", re.compile(r"Bearer\s+[A-Za-z0-9_\-.]{20,}", re.IGNORECASE)),
    (
        "PostgreSQL URL with password",
        re.compile(r"postgres(?:ql)?://[^:\s/]+:[^@\s]+@[^/\s]+/[^\s'\"]+", re.IGNORECASE),
    ),
)


@dataclass(frozen=True)
class Finding:
    path: str
    kind: str
    line: int | None = None


def _is_safe_env_example(path: Path) -> bool:
    return path.name in SAFE_ENV_EXAMPLES


def _is_env_file(path: Path) -> bool:
    return path.name == ".env" or path.name.startswith(".env.")


def iter_project_files(root: Path) -> list[Path]:
    git_dir = root / ".git"
    if git_dir.exists():
        try:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            files: list[Path] = []
            for line in result.stdout.splitlines():
                if not line.strip():
                    continue
                candidate = root / line.strip()
                if any(part in IGNORED_DIRS for part in candidate.relative_to(root).parts):
                    continue
                if candidate.is_file():
                    files.append(candidate)
            return files
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    files: list[Path] = []
    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIRS for part in relative_parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def scan_path(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_project_files(root):
        relative_path = path.relative_to(root)
        relative = str(relative_path)

        if _is_env_file(path) and not _is_safe_env_example(path):
            findings.append(Finding(relative, "env file must not be committed"))

        if path.suffix.lower() in SENSITIVE_SUFFIXES and relative.replace("\\", "/") not in SAFE_SQL_FILES:
            findings.append(Finding(relative, "database dump/export file must not be committed"))

        if path.suffix.lower() not in TEXT_SUFFIXES and not _is_env_file(path):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if any(placeholder in stripped.lower() for placeholder in ("your-read-only-token", "<read-only-token>", "...")):
                continue
            if "ORDERPRO_API_TOKEN=" in stripped and stripped.endswith("="):
                continue
            if "OPENAI_API_KEY=" in stripped and stripped.endswith("="):
                continue

            for kind, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(Finding(relative, kind, line_number))
    return findings


def format_findings(findings: list[Finding]) -> str:
    lines = []
    for finding in findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        lines.append(f"{location} - {finding.kind}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check deployment files for obvious secrets.")
    parser.add_argument("--root", default=".", help="Project root to scan.")
    args = parser.parse_args()

    findings = scan_path(Path(args.root).resolve())
    if findings:
        print("Potential deployment secret risks found:")
        print(format_findings(findings))
        return 1

    print("No obvious deployment secrets found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
