from unittest.mock import Mock, patch

import pytest

from krkn.rollback.config import RollbackConfig
from krkn.rollback.handler import RollbackExecutionError, execute_rollback_version_files


def test_executes_remaining_files_and_raises_aggregate_error():
    version_files = ["first.py", "second.py", "third.py"]
    calls = []

    def parse_version_file(path):
        def rollback(content, telemetry):
            calls.append(path)
            if path != "second.py":
                raise RuntimeError(f"failed {path}")

        return rollback, Mock(skip_kubernetes=False)

    with (
        patch.object(RollbackConfig, "search_rollback_version_files", return_value=version_files),
        patch("krkn.rollback.handler._parse_rollback_module", side_effect=parse_version_file),
        patch("krkn.rollback.handler.os.rename") as rename,
    ):
        with pytest.raises(RollbackExecutionError) as error:
            execute_rollback_version_files(Mock(), ignore_auto_rollback_config=True)

    assert calls == version_files
    assert [path for path, _ in error.value.failures] == ["first.py", "third.py"]
    assert "failed first.py" in str(error.value)
    assert "failed third.py" in str(error.value)
    rename.assert_called_once_with("second.py", "second.py.executed")


def test_collects_rename_failure_and_continues():
    version_files = ["first.py", "second.py"]
    rollback = Mock()
    content = Mock(skip_kubernetes=True)

    with (
        patch.object(RollbackConfig, "search_rollback_version_files", return_value=version_files),
        patch("krkn.rollback.handler._parse_rollback_module", return_value=(rollback, content)),
        patch("krkn.rollback.handler.os.rename", side_effect=[OSError("rename failed"), None]),
    ):
        with pytest.raises(RollbackExecutionError) as error:
            execute_rollback_version_files(Mock(), ignore_auto_rollback_config=True)

    assert rollback.call_count == 2
    assert [path for path, _ in error.value.failures] == ["first.py"]
