## Issue

Issue #36: retry test 1

The `Dependency Review` workflow in `.github/workflows/dependency-review.yml` had `continue-on-error: true` configured on the `actions/dependency-review-action` step. This made the dependency review advisory only — the workflow could report success on a pull request even when the action detected vulnerable dependencies or denied licenses, weakening supply-chain enforcement.

## Findings

- The `dependency-review` job invoked `actions/dependency-review-action@v4.9.0` with `continue-on-error: true`.
- With that setting, any non-zero exit from the action (e.g., a vulnerability matching `fail-on-severity: critical` or a `deny-licenses` hit) was swallowed and the step was reported as successful.
- Because the step always succeeded, the job became green regardless of findings, so the workflow could not enforce blocking PRs on vulnerable dependencies as intended by the action's documentation.
- The `fail-on-severity: critical`, `deny-licenses`, and `allow-dependencies-licenses` configuration was already present and correct — only the `continue-on-error` override prevented enforcement.

## Fixes

- Removed the `continue-on-error: true` line from the `Dependency Review` step in `.github/workflows/dependency-review.yml`.
- No other behavior changed: the action version pin, `fail-on-severity: critical`, `deny-licenses` list, and `allow-dependencies-licenses` exceptions are all preserved.
- The workflow now propagates the action's exit code, so a PR introducing a critical-severity vulnerability or a denied license will fail the `Dependency Review` check and block the PR (when the check is required).

### Verification

- YAML validity confirmed by parsing the file with `python -c "import yaml; yaml.safe_load(open('.github/workflows/dependency-review.yml'))"` — parses successfully and `fail-on-severity` remains `critical`, `continue-on-error` key is absent.
- `pre-commit run --files .github/workflows/dependency-review.yml` — all applicable hooks (`check-yaml`, `check for added large files`, `fix end of files`, `trim trailing whitespace`) passed.
- Note: the GitHub-hosted dependency review check additionally requires the Dependency Graph feature to be enabled on the repository; that is a repository-configuration concern outside the workflow file.
