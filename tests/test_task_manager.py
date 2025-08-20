import pytest
from unittest.mock import patch
from src import task_manager

# A sample task_info tuple to be used across tests
SAMPLE_TASK_INFO = ('2023', '1A', '1', '问题')
# Expected task_id for the sample task_info
EXPECTED_TASK_ID = '2023-1A_第1問_问题'

def test_get_task_id():
    """Tests the helper function that generates a task ID."""
    assert task_manager.get_task_id(SAMPLE_TASK_INFO) == EXPECTED_TASK_ID

# We patch the methods on the class that will be instantiated
@patch('pathlib.Path.is_file', return_value=True)
@patch('pathlib.Path.exists', return_value=True)
def test_is_task_truly_complete_when_marker_exists(mock_exists, mock_is_file):
    """
    Tests that the function returns True when the success marker file
    exists and is a file.
    """
    result = task_manager.is_task_truly_complete(SAMPLE_TASK_INFO)

    # Assert that the function returned True
    assert result is True

    # Assert that the path checks were actually called
    mock_exists.assert_called_once()
    mock_is_file.assert_called_once()

@patch('pathlib.Path.exists', return_value=False)
def test_is_task_truly_complete_when_marker_does_not_exist(mock_exists):
    """
    Tests that the function returns False when the success marker file
    does not exist.
    """
    result = task_manager.is_task_truly_complete(SAMPLE_TASK_INFO)

    # Assert that the function returned False
    assert result is False

    # Assert that exists was called (is_file should not be called due to short-circuiting)
    mock_exists.assert_called_once()

@patch('pathlib.Path.is_file', return_value=False)
@patch('pathlib.Path.exists', return_value=True)
def test_is_task_truly_complete_when_path_is_a_directory(mock_exists, mock_is_file):
    """
    Tests that the function returns False when the path exists but is
    a directory, not a file.
    """
    result = task_manager.is_task_truly_complete(SAMPLE_TASK_INFO)

    # Assert that the function returned False
    assert result is False

    # Assert that both path checks were called
    mock_exists.assert_called_once()
    mock_is_file.assert_called_once()
