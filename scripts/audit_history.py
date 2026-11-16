"""Audit the whole git history before the repository is made public (design notes 6.3c, 10.2).

Usage, from the repository root: ``uv run python scripts/audit_history.py [DATA_DIR]``

It reads every blob reachable from any ref (every version of every file ever committed) and
reports, as **file paths and counts only, never values**:

- files ever committed under ``data/`` other than ``data/README.md``;
- spreadsheets, and CSV files outside ``examples/`` and ``tests/``;
- text that looks like a secret (cloud keys, tokens, private keys, assigned passwords);
- valid IBANs;
- e-mail addresses other than GitHub's noreply and example domains;
- any ISIN of the **real portfolio**. The ISINs are collected from the local, git-ignored
  ``DATA_DIR`` (default ``data/``) and kept in memory only.

It also reads every commit and annotated tag reachable from any ref (design note 10.2), and
reports their hashes only:

- author, committer and tagger e-mail addresses other than the allowed ones;
- messages with any of the findings above that apply to text (secrets, IBANs, e-mails, ISINs).

The allowed e-mail addresses are GitHub's ``noreply`` ones, the example domains, and
``noreply@anthropic.com``, which ``Co-Authored-By`` trailers use.

The exit code is 0 when nothing is found, 1 otherwise, and 2 for a usage error. A finding is
not necessarily a leak. For example, a synthetic IBAN in a test is reported too; each path must
be reviewed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from qrlab.instruments import is_valid_isin

__all__ = ["Findings", "audit", "blobs", "history", "main", "real_isins"]

ISIN = re.compile(rb"\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b")
IBAN = re.compile(rb"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\b")
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALLOWED_EMAIL_DOMAINS = (b"users.noreply.github.com", b"example.com", b"example.org")
ALLOWED_EMAILS = (b"noreply@github.com", b"noreply@anthropic.com")
SHOWN = 20  # paths or hashes listed per kind of finding; the rest are counted
SECRETS = (
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{60,}"),
    re.compile(rb"pypi-AgE[A-Za-z0-9_-]{50,}"),
    re.compile(rb"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(rb"sk-(?:ant-)?[A-Za-z0-9_-]{32,}"),
    re.compile(rb"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
)
SPREADSHEETS = (".xlsx", ".xls", ".xlsm", ".ods")
CSV_ALLOWED = ("examples/", "tests/")


@dataclass
class Findings:
    """Paths per kind of finding; no values are ever stored."""

    blobs: int = 0
    commits: int = 0
    data_files: set[str] = field(default_factory=set)
    spreadsheets: set[str] = field(default_factory=set)
    csv_outside_examples: set[str] = field(default_factory=set)
    secrets: set[str] = field(default_factory=set)
    ibans: set[str] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    real_isins: set[str] = field(default_factory=set)
    real_isins_known: int = 0
    commit_emails: set[str] = field(default_factory=set)
    commit_messages: set[str] = field(default_factory=set)

    def kinds(self) -> dict[str, set[str]]:
        """Every kind of finding with its paths."""
        return {
            "files under data/": self.data_files,
            "spreadsheets": self.spreadsheets,
            "CSV outside examples/ and tests/": self.csv_outside_examples,
            "possible secrets": self.secrets,
            "valid IBANs": self.ibans,
            "e-mail addresses": self.emails,
            "ISINs of the real portfolio": self.real_isins,
            "commits or tags with other e-mail addresses": self.commit_emails,
            "commit or tag messages to review": self.commit_messages,
        }

    @property
    def clean(self) -> bool:
        """Whether nothing was found."""
        return not any(self.kinds().values())


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=repo, input=stdin, capture_output=True, check=True, timeout=600
    ).stdout


def blobs(repo: Path) -> Iterator[tuple[str, bytes]]:
    """Yield ``(path, content)`` for every blob reachable from any ref, each blob once."""
    paths: dict[str, str] = {}
    for line in _git(repo, "rev-list", "--all", "--objects").decode().splitlines():
        sha, _, path = line.partition(" ")
        if path and sha not in paths:
            paths[sha] = path
    if not paths:
        return
    kinds = _git(repo, "cat-file", "--batch-check", stdin="\n".join(paths).encode() + b"\n")
    wanted = [line.split()[0] for line in kinds.decode().splitlines() if line.split()[1] == "blob"]
    batch = _git(repo, "cat-file", "--batch", stdin="\n".join(wanted).encode() + b"\n")
    position = 0
    for sha in wanted:
        header_end = batch.index(b"\n", position)
        size = int(batch[position:header_end].split()[2])
        start = header_end + 1
        yield paths[sha], batch[start : start + size]
        position = start + size + 1


def history(repo: Path) -> Iterator[tuple[str, list[bytes], bytes]]:
    """Yield ``(hash, e-mail addresses, message)`` for every commit and annotated tag."""
    log = _git(repo, "log", "--all", "--format=%H%x00%ae%x00%ce%x00%B%x1e")
    for record in log.split(b"\x1e"):
        if record.strip():
            sha, author, committer, message = record.lstrip(b"\n").split(b"\x00", 3)
            yield sha.decode(), [author, committer], message
    tag_format = "--format=%(objectname)%00%(objecttype)%00%(taggeremail)%00%(contents)%1e"
    for record in _git(repo, "for-each-ref", tag_format, "refs/tags").split(b"\x1e"):
        if record.strip():
            sha, kind, tagger, message = record.lstrip(b"\n").split(b"\x00", 3)
            if kind == b"tag":  # a lightweight tag is only a name for a commit
                yield sha.decode(), [tagger.strip(b"<>")], message


def real_isins(data_dir: Path) -> set[str]:
    """Return the valid ISINs found in the files under ``data_dir`` (except its README)."""
    found: set[str] = set()
    if not data_dir.is_dir():
        return found
    for path in data_dir.rglob("*"):
        if path.is_file() and path.name.lower() != "readme.md":
            for match in ISIN.findall(path.read_bytes()):
                code = match.decode()
                if is_valid_isin(code):
                    found.add(code)
    return found


def _valid_iban(text: bytes) -> bool:
    code = text.decode()
    rearranged = code[4:] + code[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


def _allowed_email(email: bytes) -> bool:
    lower = email.lower()
    return lower.endswith(ALLOWED_EMAIL_DOMAINS) or lower in ALLOWED_EMAILS


def _text_findings(content: bytes, wanted: Sequence[bytes]) -> set[str]:
    """Return the kinds of finding in a text: secrets, IBANs, e-mails, real ISINs."""
    kinds: set[str] = set()
    if any(pattern.search(content) for pattern in SECRETS):
        kinds.add("secrets")
    if any(_valid_iban(m) for m in IBAN.findall(content)):
        kinds.add("ibans")
    if any(not _allowed_email(e) for e in EMAIL.findall(content)):
        kinds.add("emails")
    if any(isin in content for isin in wanted):
        kinds.add("real_isins")
    return kinds


def audit(repo: Path, isins: set[str]) -> Findings:
    """Scan the history of ``repo`` for every kind of finding."""
    findings = Findings(real_isins_known=len(isins))
    wanted = [i.encode() for i in isins]
    for sha, emails, message in history(repo):
        findings.commits += 1
        if any(not _allowed_email(email) for email in emails):
            findings.commit_emails.add(sha)
        if _text_findings(message, wanted):
            findings.commit_messages.add(sha)
    for path, content in blobs(repo):
        findings.blobs += 1
        posix = PurePosixPath(path)
        if path.startswith("data/") and path != "data/README.md":
            findings.data_files.add(path)
        if posix.suffix.lower() in SPREADSHEETS:
            findings.spreadsheets.add(path)
        if posix.suffix.lower() == ".csv" and not path.startswith(CSV_ALLOWED):
            findings.csv_outside_examples.add(path)
        kinds = _text_findings(content, wanted)
        for kind in kinds:
            getattr(findings, kind).add(path)
    return findings


def report(findings: Findings) -> str:
    """Return the text report: counts and paths, never values."""
    lines = [
        f"blobs scanned: {findings.blobs}",
        f"commits and tags scanned: {findings.commits}",
        f"ISINs of the real portfolio checked: {findings.real_isins_known}",
    ]
    hashes = findings.commit_emails | findings.commit_messages
    for kind, items in findings.kinds().items():
        lines.append(f"{kind}: {len(items)}")
        shown = sorted(items)[:SHOWN]
        lines += [f"  {item[:12] if item in hashes else item}" for item in shown]
        if len(items) > SHOWN:
            lines.append(f"  ... and {len(items) - SHOWN} more")
    lines.append("CLEAN" if findings.clean else "REVIEW THE PATHS ABOVE")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None, *, repo: Path | None = None) -> int:
    """Run the audit on the repository; print the report."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) > 1:
        print("usage: audit_history.py [DATA_DIR]", file=sys.stderr)
        return 2
    root = repo if repo is not None else Path.cwd()
    data_dir = Path(args[0]) if args else root / "data"
    findings = audit(root, real_isins(data_dir))
    print(report(findings))
    return 0 if findings.clean else 1


if __name__ == "__main__":  # pragma: no cover - run by hand before publication
    raise SystemExit(main())
