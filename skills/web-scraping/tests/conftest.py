"""conftest.py — shared pytest configuration for web-scraping skill tests.

Registers the 'integration' marker and provides a --integration flag so that
network-hitting tests are skipped by default in offline / CI runs.
"""

import sys
import os
import pytest

# Make sure the scripts directory is importable (no package __init__ needed)
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that make real HTTP requests",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring real network access (skipped by default)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip_integration = pytest.mark.skip(
            reason="Pass --integration to run network tests"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
