# Releasing

How a version is released (design note 6.3c).

```{note}
1.0.0 went out on GitHub only (design note 10.3): the owner had no PyPI account yet, so the
PyPI and TestPyPI steps below were skipped and the publish jobs were rejected. They apply once
the accounts exist.
```
 The workflows do the building and checking; the
steps that publish or change settings are done by the owner, on their own accounts.

## One-time setup (owner)

1. **Audit the history.** Before the repository becomes public:

   ```bash
   uv run python scripts/audit_history.py [FOLDER_WITH_YOUR_REAL_PORTFOLIO_FILES]
   ```

   The script scans every file version, every commit and every annotated tag in the history
   (author, committer and tagger e-mails, and messages). It prints only counts, paths and
   commit hashes, never values. It must end with `CLEAN`, with two accepted exceptions:
   - its own test file, `tests/unit/scripts/test_audit_history.py`, whose documentation IBAN
     and invented e-mail addresses exist to test it;
   - design note 10.2, which quotes one of those invented addresses (on the reserved `.test`
     domain).

   The ISIN check is only as good as the folder given:
   point it at the folder that holds your real broker exports and holdings. The default is
   `data/`.

   The history was rewritten once, on 2026-11-16, before the first publication (design note
   10.3): the owner's personal e-mail address became the `noreply` one, and three personal
   passages were replaced. Every commit kept its tree, except the 55 whose files held one of
   those passages.
2. **Make the repository public:** *Settings → General → Danger Zone → Change visibility*.
3. **Create the protected environments** in *Settings → Environments*:
   - `testpypi`;
   - `pypi`.

   Add yourself as a required reviewer for each: a publish then waits for your approval.
4. **Add the trusted publishers.** On <https://test.pypi.org> and on <https://pypi.org>, use
   *Your projects → Publishing → Add a pending publisher*:

   | Field | Value |
   |---|---|
   | PyPI project name | `quant-research-lab` |
   | Owner | `alessandroszn` |
   | Repository name | `quant-research-lab` |
   | Workflow name | `release.yml` |
   | Environment name | `testpypi` (on TestPyPI) or `pypi` (on PyPI) |

   No token is created or stored anywhere.
5. **Link Zenodo:** log in to <https://zenodo.org> with GitHub, then under *GitHub* switch the
   repository on. Every published GitHub release is then archived with a DOI. Zenodo reads
   `.zenodo.json`.
6. **Turn on GitHub Pages:** *Settings → Pages → Source: GitHub Actions*.
7. **Optional:** *Settings → Code security → Private vulnerability reporting*, which
   `SECURITY.md` refers to.

## Each release

1. On a branch:
   - set the version in `pyproject.toml` and in `CITATION.cff`, and add `date-released` to
     `CITATION.cff`;
   - move the CHANGELOG's *Unreleased* entries under the new version;
   - for a final release, set the `Development Status` classifier.

   Open the PR and merge it once CI is green.
2. Tag the merge commit and push the tag. A release candidate such as `v1.0.0rc1` goes to
   TestPyPI; a final version such as `v1.0.0` goes to PyPI and also publishes the docs.
3. The **Release** workflow then runs these steps:
   1. it checks that the tag matches `pyproject.toml`;
   2. it builds the sdist and the wheel, checks their metadata, and installs the wheel in a
      clean environment;
   3. it runs the full Windows build and its checks (results equal to the source, self-test,
      installer round trip);
   4. it creates a **draft** GitHub Release with every file;
   5. it waits for your approval in the `testpypi` or `pypi` environment, then publishes.
4. Review the draft release and publish it. Zenodo archives it and mints the DOI.
5. For a release candidate, install it from TestPyPI in a clean environment and run an
   example:

   ```bash
   uv venv rc && uv pip install --python rc --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ quant-research-lab==1.0.0rc1
   ```
