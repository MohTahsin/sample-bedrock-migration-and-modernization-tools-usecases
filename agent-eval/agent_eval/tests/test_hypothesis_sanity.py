"""
Sanity test to verify Hypothesis (property-based testing) is working.
"""

import pytest
from hypothesis import given, strategies as st


@pytest.mark.property
@given(st.integers())
def test_hypothesis_integers(x):
    """Verify Hypothesis can generate integers."""
    assert isinstance(x, int)


@pytest.mark.property
@given(st.text())
def test_hypothesis_text(s):
    """Verify Hypothesis can generate text."""
    assert isinstance(s, str)


@pytest.mark.property
@given(st.lists(st.integers(), min_size=0, max_size=10))
def test_hypothesis_lists(lst):
    """Verify Hypothesis can generate lists."""
    assert isinstance(lst, list)
    assert len(lst) <= 10
