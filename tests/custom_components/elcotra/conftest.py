"""Common fixtures for ElCoTra tests."""

from unittest.mock import MagicMock

import pytest

from homeassistant.core import HomeAssistant


@pytest.fixture
def hass():
    """Return a mock HomeAssistant instance."""
    hass_mock = MagicMock(spec=HomeAssistant)
    hass_mock.data = {}
    return hass_mock
