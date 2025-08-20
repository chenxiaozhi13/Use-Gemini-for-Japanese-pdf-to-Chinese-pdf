import pytest
from src import scheduler, config

# We can directly patch the config values for testing purposes
@pytest.fixture(autouse=True)
def override_config():
    """A pytest fixture to temporarily override config values for tests."""
    original_max_per_key = config.MAX_CONCURRENT_PER_KEY
    original_penalty = config.FAILURE_PENALTY_WEIGHT

    config.MAX_CONCURRENT_PER_KEY = 5
    config.FAILURE_PENALTY_WEIGHT = 3

    yield # This is where the test runs

    # Restore original values after the test
    config.MAX_CONCURRENT_PER_KEY = original_max_per_key
    config.FAILURE_PENALTY_WEIGHT = original_penalty

def test_get_least_busy_key_clear_winner():
    """Tests that the function correctly identifies the key with the lowest score."""
    api_key_status = {
        'key1': {'active': 4, 'failures': 1}, # score = 4 + 1*3 = 7
        'key2': {'active': 1, 'failures': 1}, # score = 1 + 1*3 = 4  <- WINNER
        'key3': {'active': 3, 'failures': 2}, # score = 3 + 2*3 = 9
    }
    assert scheduler.get_least_busy_key(api_key_status) == 'key2'

def test_get_least_busy_key_tie_returns_first():
    """Tests that the function returns the first key in case of a tie."""
    api_key_status = {
        'key1': {'active': 2, 'failures': 0}, # score = 2
        'key2': {'active': 5, 'failures': 0}, # score = 5 (at max)
        'key3': {'active': 2, 'failures': 0}, # score = 2
    }
    config.MAX_CONCURRENT_PER_KEY = 5
    # key1 and key3 have the same score. The function should return the first one it encounters.
    assert scheduler.get_least_busy_key(api_key_status) == 'key1'

def test_get_least_busy_key_failure_penalty():
    """Tests that the failure penalty is correctly applied."""
    api_key_status = {
        'key1': {'active': 1, 'failures': 0}, # score = 1 <- WINNER
        'key2': {'active': 0, 'failures': 1}, # score = 0 + 1*3 = 3
    }
    config.FAILURE_PENALTY_WEIGHT = 3
    assert scheduler.get_least_busy_key(api_key_status) == 'key1'

def test_get_least_busy_key_all_at_max_capacity():
    """Tests that the function returns None if all keys are at max concurrency."""
    api_key_status = {
        'key1': {'active': 5, 'failures': 0},
        'key2': {'active': 5, 'failures': 2},
    }
    config.MAX_CONCURRENT_PER_KEY = 5
    assert scheduler.get_least_busy_key(api_key_status) is None

def test_get_least_busy_key_one_key_available():
    """Tests that the only available key is chosen, regardless of failures."""
    api_key_status = {
        'key1': {'active': 5, 'failures': 0},
        'key2': {'active': 4, 'failures': 10}, # score = 4 + 10*3 = 34, but it's the only one available
        'key3': {'active': 5, 'failures': 0},
    }
    config.MAX_CONCURRENT_PER_KEY = 5
    assert scheduler.get_least_busy_key(api_key_status) == 'key2'

def test_get_least_busy_key_empty_status():
    """Tests that the function returns None for an empty status dictionary."""
    assert scheduler.get_least_busy_key({}) is None

def test_get_least_busy_key_all_idle():
    """Tests that the first key is returned when all keys are idle."""
    api_key_status = {
        'key1': {'active': 0, 'failures': 0},
        'key2': {'active': 0, 'failures': 0},
        'key3': {'active': 0, 'failures': 0},
    }
    assert scheduler.get_least_busy_key(api_key_status) == 'key1'
