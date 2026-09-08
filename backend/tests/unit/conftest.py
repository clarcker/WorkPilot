import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Override parent conftest - no database needed for unit tests."""
    yield


@pytest.fixture(autouse=True)
def cleanup_tables():
    """Override parent conftest - no cleanup needed for unit tests."""
    yield
