# Issue 17: zoe webhook testin

## Issue
`superset/examples/utils.py` deserialized `metadata.yaml` from on-disk export
bundles via `yaml.load(..., Loader=yaml.Loader)` (suppressed with
`# noqa: S506`). PyYAML's `Loader` resolves arbitrary tags such as
`!!python/object/apply:`, which can construct or invoke arbitrary Python
objects. Even though the example importer is administrative, parsing
untrusted YAML with the unrestricted loader does not match the project's
secure-deserialization expectations.

## Findings
- The unsafe call is at the end of `load_configs_from_directory()` in
  `superset/examples/utils.py`, which reads `metadata.yaml` from a directory
  the caller passes in, strips the `type` key, and re-serializes the result
  before handing it to `ImportExamplesCommand`.
- Only `dict`-shaped metadata is ever expected here: the subsequent code path
  performs `if "type" in metadata` and `del metadata["type"]`, which already
  assumes a plain mapping.
- `yaml.safe_load` covers the full set of scalar/collection tags emitted by
  `yaml.safe_dump` (used elsewhere in the import/export flow), so swapping to
  `safe_load` preserves behavior for valid metadata while refusing
  Python-object construction tags and other unsafe constructors.
- No other call sites in `superset/examples/utils.py` use `yaml.load`; this is
  the only occurrence flagged.

## Fixes
- Replaced
  `yaml.load(contents.get(METADATA_FILE_NAME, "{}"), Loader=yaml.Loader)  # noqa: S506`
  with `yaml.safe_load(contents.get(METADATA_FILE_NAME, "{}"))` in
  `superset/examples/utils.py`. The `# noqa: S506` suppression is removed
  because the underlying lint finding no longer applies.
- Added unit tests in `tests/unit_tests/examples/utils_test.py` covering
  `load_configs_from_directory`:
  1. Valid metadata is still parsed and the `type` key is stripped before the
     contents reach `ImportExamplesCommand`.
  2. A canonical unsafe payload (`!!python/object/apply:os.system [...]`) now
     raises `yaml.YAMLError` and `ImportExamplesCommand` is never invoked.
  3. Malformed YAML in `metadata.yaml` raises `yaml.YAMLError` rather than
     silently returning unexpected types.

## Local validation
- `ruff check superset/examples/utils.py tests/unit_tests/examples/utils_test.py` - passed.
- `pre-commit run --files superset/examples/utils.py tests/unit_tests/examples/utils_test.py` - all hooks passed (mypy, ruff, ruff-format, pylint, etc.).
- Standalone behavioral check exercising `load_configs_from_directory` against
  the three test payloads above (valid metadata strip, unsafe tag rejected,
  malformed YAML rejected) - all three behaviors verified locally.
- The full pytest run was intentionally skipped per the task's
  "targeted validation only" guidance; existing collateral test coverage is
  exercised by CI.
