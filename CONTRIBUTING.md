# Contributing

Thank you for your interest. Quant Research Lab puts correctness and reproducibility before
features, so every change follows the same steps.

1. **Open an issue first.** For anything beyond a typo, describe the change and why it is
   needed.
2. **Design note.** New features start with a short note in `docs/design/` covering:
   - inputs and outputs;
   - edge cases and risks;
   - a test plan with hand-calculated examples.

   The note is agreed before code is written.
3. **Tests first.** For financial formulas:
   - write a hand-calculated example, then the test, then the code;
   - cross-check against independent implementations, such as statsmodels or SciPy, where
     they exist;
   - test the edge cases: empty, all-NaN, a single observation, zero variance, an unsorted or
     duplicated index.
4. **Quality gate.** It must pass before review:

   ```bash
   uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest
   ```

   Coverage stays at 100%. Warnings are errors in tests. To run CI's exact steps, on Linux
   too, see `docs/project/linux-checks.md`.
5. **Public API.** If a public name or signature changes, regenerate the listing with
   `uv run python tests/api_snapshot.py --write`, and follow `docs/compatibility.md`.
6. **Commits and PRs.**
   - Use [Conventional Commits](https://www.conventionalcommits.org/).
   - Keep one topic per PR.
   - Update `CHANGELOG.md`.
   - Give the reason for any new dependency in the PR description.

Never commit real portfolio data, credentials or machine-specific paths. Tests, fixtures and
examples use synthetic data only.

By contributing you agree that your contribution is licensed under the BSD-3-Clause licence of
the project, and documentation under CC BY 4.0.
