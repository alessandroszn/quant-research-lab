"""The pre-publication history audit (design note 6.3c), on synthetic git repositories."""

from __future__ import annotations

import subprocess
from pathlib import Path

import audit_history
import pytest

from qrlab.instruments import is_valid_isin

TEXTBOOK_IBAN = "GB82WEST12345698765432"  # the standard documentation example, not an account


def _isin(body: str) -> str:
    """Return a synthetic ISIN: ``body`` (11 characters) plus its check digit."""
    for digit in "0123456789":
        if is_valid_isin(body + digit):
            return body + digit
    raise AssertionError(body)  # pragma: no cover - every body has a check digit


REAL = _isin("XS999999999")  # stands for an ISIN of the private portfolio
SYNTHETIC = _isin("IE000000001")  # stands for an invented ISIN in the examples


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _commit(repo: Path, files: dict[str, str | bytes], message: str) -> None:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _commit(
        root,
        {
            "README.md": "# demo\nContact: someone@users.noreply.github.com\n",
            "data/README.md": "Put your files here; they are never committed.\n",
            "examples/data/holdings.csv": f"holding,weight\n{SYNTHETIC},1.0\n",
            "tests/fixture.csv": "a,b\n1,2\n",
        },
        "clean start",
    )
    return root


def _private_data(tmp_path: Path) -> Path:
    data = tmp_path / "private-data"
    (data / "raw").mkdir(parents=True)
    (data / "README.md").write_text(f"{SYNTHETIC} is only an example\n", encoding="utf-8")
    (data / "raw" / "portfolio.csv").write_text(
        f"isin,qty\n{REAL},10\nAB1234567890,3\n",
        encoding="utf-8",  # the second is invalid
    )
    return data


def test_real_isins_come_from_data_files_only(tmp_path: Path) -> None:
    assert audit_history.real_isins(_private_data(tmp_path)) == {REAL}
    assert audit_history.real_isins(tmp_path / "missing") == set()


def test_a_clean_history_passes(repo: Path, tmp_path: Path) -> None:
    findings = audit_history.audit(repo, audit_history.real_isins(_private_data(tmp_path)))
    assert findings.clean
    assert findings.blobs == 4
    assert findings.commits == 1
    assert findings.real_isins_known == 1
    assert audit_history.report(findings).endswith("CLEAN")


def test_every_kind_of_finding_is_reported_without_values(repo: Path, tmp_path: Path) -> None:
    # A private file committed and then deleted is still in the history.
    _commit(repo, {"data/raw/portfolio.csv": f"isin,qty\n{REAL},10\n"}, "oops")
    _git(repo, "rm", "-q", "data/raw/portfolio.csv")
    _git(repo, "commit", "-q", "-m", "remove it")
    _commit(
        repo,
        {
            "reports/positions.xlsx": b"PK\x03\x04 not really a spreadsheet",
            "results/out.csv": "x\n1\n",
            "configs/secret.toml": 'token = "ghp_' + "a" * 36 + '"\n',
            "notes/bank.txt": f"pay to {TEXTBOOK_IBAN}\n",
            "notes/contact.txt": "write to someone@gmail.com\n",
            "notes/holding.md": f"we hold {REAL}\n",
        },
        "more",
    )
    findings = audit_history.audit(repo, {REAL})
    assert not findings.clean
    assert findings.data_files == {"data/raw/portfolio.csv"}
    assert findings.spreadsheets == {"reports/positions.xlsx"}
    assert findings.csv_outside_examples == {"data/raw/portfolio.csv", "results/out.csv"}
    assert findings.secrets == {"configs/secret.toml"}
    assert findings.ibans == {"notes/bank.txt"}
    assert findings.emails == {"notes/contact.txt"}
    assert findings.real_isins == {"data/raw/portfolio.csv", "notes/holding.md"}
    text = audit_history.report(findings)
    assert REAL not in text
    assert TEXTBOOK_IBAN not in text
    assert "ghp_" not in text
    assert "gmail" not in text
    assert "ISINs of the real portfolio: 2" in text
    assert text.endswith("REVIEW THE PATHS ABOVE")


def test_an_invalid_iban_like_string_is_not_reported(repo: Path) -> None:
    _commit(repo, {"notes/code.txt": "GB00WEST12345698765432 is not a valid IBAN\n"}, "x")
    assert audit_history.audit(repo, set()).ibans == set()


def test_an_empty_repository_has_nothing_to_scan(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, "init", "-q")
    findings = audit_history.audit(empty, set())
    assert findings.blobs == 0
    assert findings.clean


def test_command_line(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _private_data(tmp_path)
    assert audit_history.main([str(data)], repo=repo) == 0
    assert capsys.readouterr().out.endswith("CLEAN\n")
    _commit(repo, {"notes/holding.md": f"{REAL}\n"}, "leak")
    assert audit_history.main([str(data)], repo=repo) == 1
    output = capsys.readouterr().out
    assert "notes/holding.md" in output
    assert REAL not in output
    assert audit_history.main(["a", "b"], repo=repo) == 2
    # No arguments: the current folder and its own data/ folder, which holds no real ISINs, so
    # the committed one is not recognised as private. The audit is only as good as data/.
    monkeypatch.chdir(repo)
    assert audit_history.main([]) == 0
    assert "ISINs of the real portfolio checked: 0" in capsys.readouterr().out


# ------------------------------------------------- commits and tags (design note 10.2)
def _rev(repo: Path, ref: str) -> str:
    done = subprocess.run(
        ["git", "rev-parse", ref], cwd=repo, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def _commit_as(repo: Path, email: str, name: str, message: str) -> str:
    (repo / name).write_text(name + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", f"user.email={email}", "commit", "-q", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return _rev(repo, "HEAD")


def test_commit_and_tag_metadata_is_audited_without_values(repo: Path) -> None:
    trailer = "\n\nCo-Authored-By: Bot <noreply@anthropic.com>"
    private = _commit_as(repo, "someone@private.test", "a.txt", "add a")
    holding = _commit_as(repo, "t@example.com", "b.txt", f"we hold {REAL}{trailer}")
    _commit_as(repo, "t@example.com", "c.txt", f"add c{trailer}")  # the trailer is allowed
    tagger = ["git", "-c", "user.name=t", "-c", "user.email=tagger@private.test"]
    subprocess.run(
        [*tagger, "tag", "-a", "v1", "-m", "release"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    _git(repo, "tag", "light")  # a lightweight tag has no tagger and no message of its own
    tag = _rev(repo, "v1")
    findings = audit_history.audit(repo, {REAL})
    # Four commits (the fixture's and three) and one annotated tag.
    assert findings.commits == 5
    assert findings.commit_emails == {private, tag}
    assert findings.commit_messages == {holding}
    text = audit_history.report(findings)
    assert "commits or tags with other e-mail addresses: 2" in text
    assert f"  {private[:12]}\n" in text
    assert private not in text  # hashes are shortened
    assert "private.test" not in text
    assert REAL not in text
    assert text.endswith("REVIEW THE PATHS ABOVE")


def test_a_long_list_of_findings_is_cut() -> None:
    findings = audit_history.Findings(data_files={f"data/{i:02}.csv" for i in range(25)})
    text = audit_history.report(findings)
    assert "files under data/: 25" in text
    assert "  data/19.csv\n" in text
    assert "data/20.csv" not in text
    assert "  ... and 5 more\n" in text
