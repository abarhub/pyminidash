import shutil
import subprocess
from datetime import datetime

import pytest

from pyminidash.providers.localproj.gitinfo import GitInfo, git_info, git_on_path

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git absent du PATH"
)


def _git(repo, *args):
    subprocess.run(("git", *args), cwd=repo, check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-b", "main")
    _git(r, "config", "user.email", "t@t.tt")
    _git(r, "config", "user.name", "T")
    (r / "f.txt").write_text("a", encoding="utf-8")
    _git(r, "add", ".")
    _git(r, "commit", "-m", "premier commit")
    return r


def test_git_on_path_true():
    assert git_on_path() is True


def test_clean_repo(repo):
    info = git_info(repo)
    assert isinstance(info, GitInfo)
    assert info.branch == "main"
    assert info.dirty_count == 0
    assert info.commit_subject == "premier commit"
    assert isinstance(info.commit_date, datetime)
    assert info.commit_date.tzinfo is not None
    assert "main" in info.branches


def test_dirty_count_includes_untracked(repo):
    (repo / "f.txt").write_text("modifié", encoding="utf-8")
    (repo / "nouveau.txt").write_text("x", encoding="utf-8")
    assert git_info(repo).dirty_count == 2


def test_branches_and_remotes(repo):
    _git(repo, "branch", "feature/x")
    _git(repo, "remote", "add", "origin", "git@example.com:me/r.git")
    info = git_info(repo)
    assert set(info.branches) == {"main", "feature/x"}
    assert info.remotes == ("origin git@example.com:me/r.git",)


def test_ahead_behind_vs_upstream(repo, tmp_path):
    bare = tmp_path / "bare.git"
    _git(repo, "clone", "--bare", str(repo), str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "main")
    (repo / "g.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "local en avance")
    info = git_info(repo)
    assert info.upstream == "origin/main"
    assert info.ahead == 1
    assert info.behind == 0


def test_not_a_repo_returns_none(tmp_path):
    assert git_info(tmp_path) is None


def test_commit_subject_utf8_non_ascii(repo):
    # C1 : git émet de l'UTF-8 ; le décodage ne doit pas planter sur une
    # console française (cp1252) et le texte doit être exact.
    (repo / "f.txt").write_text("b", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Café Œuvre €")
    info = git_info(repo)
    assert info is not None
    assert info.commit_subject == "Café Œuvre €"
