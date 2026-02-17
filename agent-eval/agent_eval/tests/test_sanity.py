"""
Sanity tests to verify testing infrastructure is set up correctly.
"""

import pytest


def test_pytest_works():
    """Verify pytest is working."""
    assert True


def test_imports():
    """Verify core dependencies can be imported."""
    import json
    import jsonschema
    import pydantic
    
    # pyyaml package provides yaml module
    try:
        import yaml
        assert yaml is not None
    except ImportError:
        pytest.fail("yaml module (from pyyaml) could not be imported")
    
    assert json is not None
    assert jsonschema is not None
    assert pydantic is not None


@pytest.mark.unit
def test_pytest_markers():
    """Verify pytest markers are configured."""
    assert True


class TestPytestConfiguration:
    """Test class to verify pytest class discovery."""
    
    def test_class_discovery(self):
        """Verify pytest discovers test classes."""
        assert True
