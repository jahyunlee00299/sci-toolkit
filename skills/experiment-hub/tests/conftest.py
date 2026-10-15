"""Pin canon_gate to the bundled SYNTHETIC example registry for every test, so a registry a user keeps next to
canon_gate.py (or names in LAB_CANON_REGISTRY) never changes a test result. Tests of the lookup order itself
override or delete the variable with monkeypatch."""
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parent.parent / "canonical_constants.example.toml"


@pytest.fixture(autouse=True)
def _example_registry(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("LAB_CANON_REGISTRY", str(EXAMPLE))
    # reaction_matrix.main publishes into a configured Methods folder; never the real one from a test
    monkeypatch.setenv("LAB_METHODS_DIR", str(tmp_path_factory.mktemp("methods")))
