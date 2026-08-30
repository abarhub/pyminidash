"""État Git d'un répertoire, obtenu en invoquant le binaire `git`."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_TIMEOUT = 5


def git_on_path() -> bool:
    # Vrai si le binaire `git` est présent dans le PATH.
    return shutil.which("git") is not None


@dataclass(frozen=True)
class GitInfo:
    branch: str
    dirty_count: int
    ahead: int | None
    behind: int | None
    upstream: str | None
    commit_hash_short: str | None
    commit_date: datetime | None
    commit_subject: str | None
    branches: tuple[str, ...]
    remotes: tuple[str, ...]


def _run(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # Chaque invocation porte un timeout ; `check=False` : on inspecte le code retour.
    return subprocess.run(
        ("git", *args), cwd=path, capture_output=True, text=True,
        check=False, timeout=_TIMEOUT,
    )


def _parse_status(out: str) -> tuple[str, int, int | None, int | None, str | None]:
    # Parsing défensif de `git status --porcelain=v2 --branch`.
    branch = ""
    ahead = behind = None
    upstream = None
    dirty = 0
    for line in out.splitlines():
        if line.startswith("# branch.head "):
            head = line[len("# branch.head "):].strip()
            branch = "(HEAD détachée)" if head == "(detached)" else head
        elif line.startswith("# branch.upstream "):
            upstream = line[len("# branch.upstream "):].strip()
        elif line.startswith("# branch.ab "):
            parts = line.split()  # ["#", "branch.ab", "+A", "-B"]
            if len(parts) >= 4:
                try:
                    ahead = int(parts[2])
                    behind = -int(parts[3])
                except ValueError:
                    ahead = behind = None
        elif line[:2] in ("1 ", "2 ", "u ", "? "):
            # Lignes de fichiers : modifiés, renommés, non fusionnés, non suivis.
            dirty += 1
    return branch, dirty, ahead, behind, upstream


def git_info(path: Path) -> GitInfo | None:
    # Renvoie None si `path` n'est pas dans un dépôt ou si `git` échoue ; ne lève jamais.
    try:
        st = _run(path, "status", "--porcelain=v2", "--branch")
    except (OSError, subprocess.SubprocessError):
        return None
    if st.returncode != 0:
        return None
    branch, dirty, ahead, behind, upstream = _parse_status(st.stdout)

    h = d = s = None
    try:
        lg = _run(path, "log", "-1", "--format=%h%n%cI%n%s")
        if lg.returncode == 0 and lg.stdout.strip():
            parts = lg.stdout.split("\n", 2)
            h = parts[0].strip() or None
            if len(parts) > 1:
                try:
                    # %cI : date ISO 8601 stricte, donc tz-aware.
                    d = datetime.fromisoformat(parts[1].strip())
                except ValueError:
                    d = None
            s = parts[2].strip() if len(parts) > 2 else None
    except (OSError, subprocess.SubprocessError):
        pass

    branches: tuple[str, ...] = ()
    remotes: tuple[str, ...] = ()
    try:
        br = _run(path, "for-each-ref", "--format=%(refname:short)", "refs/heads")
        if br.returncode == 0:
            branches = tuple(x.strip() for x in br.stdout.splitlines() if x.strip())
        rm = _run(path, "remote", "-v")
        if rm.returncode == 0:
            seen: dict[str, str] = {}
            for line in rm.stdout.splitlines():
                cols = line.split()
                if len(cols) >= 2:
                    seen.setdefault(cols[0], cols[1])
            remotes = tuple(f"{n} {u}" for n, u in seen.items())
    except (OSError, subprocess.SubprocessError):
        pass

    return GitInfo(
        branch=branch, dirty_count=dirty, ahead=ahead, behind=behind,
        upstream=upstream, commit_hash_short=h, commit_date=d,
        commit_subject=s, branches=branches, remotes=remotes,
    )
