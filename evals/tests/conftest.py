from __future__ import annotations

import pytest

from mitra_evals.loader import Suite, load_suite
from mitra_evals.schema import EmployeePack


@pytest.fixture(scope="session")
def suite() -> Suite:
    return load_suite()


@pytest.fixture(scope="session")
def clinic(suite: Suite) -> EmployeePack:
    return suite.packs["sunrise_clinic"]


@pytest.fixture(scope="session")
def homes(suite: Suite) -> EmployeePack:
    return suite.packs["skyline_homes"]
