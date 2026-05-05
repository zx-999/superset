# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Tests for examples/utils.py - YAML config loading and content assembly."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest
import yaml

from superset.commands.importers.v1.utils import METADATA_FILE_NAME


def _create_example_tree(base_dir: Path) -> Path:
    """Create a minimal example directory tree under base_dir/superset/examples/.

    Returns the 'superset' directory (what files("superset") would return).
    """
    superset_dir = base_dir / "superset"
    examples_dir = superset_dir / "examples"

    # _shared configs
    shared_dir = examples_dir / "_shared"
    shared_dir.mkdir(parents=True)
    (shared_dir / "database.yaml").write_text(
        "database_name: examples\n"
        "sqlalchemy_uri: __SQLALCHEMY_EXAMPLES_URI__\n"
        "uuid: a2dc77af-e654-49bb-b321-40f6b559a1ee\n"
        "version: '1.0.0'\n"
    )
    (shared_dir / "metadata.yaml").write_text(
        "version: '1.0.0'\ntimestamp: '2020-12-11T22:52:56.534241+00:00'\n"
    )

    # An example with dataset, dashboard, and chart
    example_dir = examples_dir / "test_example"
    example_dir.mkdir()
    (example_dir / "dataset.yaml").write_text(
        yaml.dump(
            {
                "table_name": "test_table",
                "schema": "main",
                "uuid": "14f48794-ebfa-4f60-a26a-582c49132f1b",
                "database_uuid": "a2dc77af-e654-49bb-b321-40f6b559a1ee",
                "version": "1.0.0",
            }
        )
    )
    (example_dir / "dashboard.yaml").write_text(
        yaml.dump(
            {
                "dashboard_title": "Test Dashboard",
                "uuid": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                "version": "1.0.0",
            }
        )
    )
    charts_dir = example_dir / "charts"
    charts_dir.mkdir()
    (charts_dir / "test_chart.yaml").write_text(
        yaml.dump(
            {
                "slice_name": "Test Chart",
                "uuid": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "dataset_uuid": "14f48794-ebfa-4f60-a26a-582c49132f1b",
                "version": "1.0.0",
            }
        )
    )

    return superset_dir


def test_load_contents_builds_correct_import_structure():
    """load_contents() must produce the key structure ImportExamplesCommand expects.

    This tests the orchestration entry point: YAML files are discovered from
    the examples directory, the shared database config has its URI placeholder
    replaced, and the result has the correct key prefixes (databases/, datasets/,
    metadata.yaml).
    """
    from superset.examples.utils import load_contents

    with TemporaryDirectory() as tmpdir:
        superset_dir = _create_example_tree(Path(tmpdir))

        test_examples_uri = "sqlite:///path/to/examples.db"
        mock_app = MagicMock()
        mock_app.config = {"SQLALCHEMY_EXAMPLES_URI": test_examples_uri}

        with patch("superset.examples.utils.files", return_value=superset_dir):
            with patch("flask.current_app", mock_app):
                contents = load_contents()

        # Verify database config is present with placeholder replaced
        assert "databases/examples.yaml" in contents
        db_content = contents["databases/examples.yaml"]
        assert "__SQLALCHEMY_EXAMPLES_URI__" not in db_content
        assert test_examples_uri in db_content

        # Verify metadata is present
        assert "metadata.yaml" in contents

        # Verify dataset is discovered with correct key prefix
        assert "datasets/examples/test_example.yaml" in contents

        # Verify dashboard is discovered with correct key prefix
        assert "dashboards/test_example.yaml" in contents

        # Verify chart is discovered with correct key prefix
        assert "charts/test_example/test_chart.yaml" in contents

        # Verify schema normalization happened (main -> null)
        dataset_content = contents["datasets/examples/test_example.yaml"]
        assert "schema: main" not in dataset_content
        assert "schema: null" in dataset_content


def test_load_contents_replaces_sqlalchemy_examples_uri_placeholder():
    """The __SQLALCHEMY_EXAMPLES_URI__ placeholder must be replaced with the real URI.

    If this placeholder is not replaced, the database import will fail with an
    invalid connection string, preventing all examples from loading.
    """
    from superset.examples.utils import _load_shared_configs

    with TemporaryDirectory() as tmpdir:
        superset_dir = _create_example_tree(Path(tmpdir))
        examples_root = Path("examples")

        test_uri = "postgresql://user:pass@host/db"
        mock_app = MagicMock()
        mock_app.config = {"SQLALCHEMY_EXAMPLES_URI": test_uri}

        with patch("superset.examples.utils.files", return_value=superset_dir):
            with patch("flask.current_app", mock_app):
                contents = _load_shared_configs(examples_root)

        assert "databases/examples.yaml" in contents
        assert test_uri in contents["databases/examples.yaml"]
        assert "__SQLALCHEMY_EXAMPLES_URI__" not in contents["databases/examples.yaml"]


@patch("superset.examples.utils.ImportExamplesCommand")
@patch("superset.examples.utils.load_contents")
def test_load_examples_from_configs_wires_command_correctly(
    mock_load_contents,
    mock_command_cls,
):
    """load_examples_from_configs() must construct ImportExamplesCommand
    with overwrite=True and thread force_data through.

    A wiring regression here would silently skip overwriting existing
    examples or ignore the force_data flag.
    """
    from superset.examples.utils import load_examples_from_configs

    mock_load_contents.return_value = {"databases/examples.yaml": "content"}
    mock_command = MagicMock()
    mock_command_cls.return_value = mock_command

    load_examples_from_configs(force_data=True)

    mock_load_contents.assert_called_once_with(False)
    mock_command_cls.assert_called_once_with(
        {"databases/examples.yaml": "content"},
        overwrite=True,
        force_data=True,
    )
    mock_command.run.assert_called_once()


@patch("superset.examples.utils.ImportExamplesCommand")
@patch("superset.examples.utils.load_contents")
def test_load_examples_from_configs_defaults(
    mock_load_contents,
    mock_command_cls,
):
    """Default call should pass force_data=False and load_test_data=False."""
    from superset.examples.utils import load_examples_from_configs

    mock_load_contents.return_value = {}
    mock_command = MagicMock()
    mock_command_cls.return_value = mock_command

    load_examples_from_configs()

    mock_load_contents.assert_called_once_with(False)
    mock_command_cls.assert_called_once_with(
        {},
        overwrite=True,
        force_data=False,
    )
    mock_command.run.assert_called_once()


def _write_metadata(directory: Path, content: str) -> None:
    """Write a metadata.yaml payload into a temporary import directory."""
    (directory / METADATA_FILE_NAME).write_text(content)


@patch("superset.examples.utils.ImportExamplesCommand")
def test_load_configs_from_directory_strips_type_from_metadata(mock_command_cls):
    """Valid metadata YAML must round-trip with the ``type`` key removed.

    This guards the documented behavior of ``load_configs_from_directory``:
    the ``type`` field is stripped so any exported model can be re-imported.
    """
    from superset.examples.utils import load_configs_from_directory

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_metadata(
            root,
            "version: '1.0.0'\n"
            "type: Database\n"
            "timestamp: '2020-12-11T22:52:56.534241+00:00'\n",
        )

        load_configs_from_directory(root)

        contents = mock_command_cls.call_args.args[0]
        rewritten = yaml.safe_load(contents[METADATA_FILE_NAME])
        assert "type" not in rewritten
        assert rewritten["version"] == "1.0.0"


@patch("superset.examples.utils.ImportExamplesCommand")
def test_load_configs_from_directory_handles_missing_metadata(mock_command_cls):
    """Directories without a metadata.yaml must not crash the importer.

    ``yaml.safe_load`` returns ``None`` for empty input, so the importer must
    coerce that into an empty mapping before serializing it back out.
    """
    from superset.examples.utils import load_configs_from_directory

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Ensure at least one YAML file exists so the directory is processed
        (root / "placeholder.yaml").write_text("foo: bar\n")

        load_configs_from_directory(root)

        contents = mock_command_cls.call_args.args[0]
        assert yaml.safe_load(contents[METADATA_FILE_NAME]) == {}


@patch("superset.examples.utils.ImportExamplesCommand")
def test_load_configs_from_directory_rejects_unsafe_yaml_tags(mock_command_cls):
    """Unsafe YAML tags must be rejected by the hardened loader.

    Prior to hardening, ``yaml.load`` with the default ``Loader`` would happily
    construct arbitrary Python objects via tags such as ``!!python/object``.
    The safe loader must raise instead of executing the payload, and the
    importer command must never be invoked with attacker-controlled objects.
    """
    from superset.examples.utils import load_configs_from_directory

    unsafe_payload = (
        "version: '1.0.0'\nevil: !!python/object/apply:os.system ['echo pwned']\n"
    )

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_metadata(root, unsafe_payload)

        with pytest.raises(yaml.YAMLError):
            load_configs_from_directory(root)

        mock_command_cls.assert_not_called()


@patch("superset.examples.utils.ImportExamplesCommand")
def test_load_configs_from_directory_rejects_malformed_yaml(mock_command_cls):
    """Malformed metadata YAML must surface as a YAMLError, not silently pass."""
    from superset.examples.utils import load_configs_from_directory

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_metadata(root, "version: '1.0.0'\n  bad-indent: : :\n")

        with pytest.raises(yaml.YAMLError):
            load_configs_from_directory(root)

        mock_command_cls.assert_not_called()
