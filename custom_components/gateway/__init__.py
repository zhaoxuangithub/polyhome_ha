"""
Support for Automation Device Specification (ADS).

For more details about this component, please refer to the documentation.
https://home-assistant.io/components/ads/
"""
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'gateway'

def setup(hass, config):
    """Set up the ADS component."""

    hass.services.register(DOMAIN, 'gateway_data', 'gateway_handle', schema='services.yaml')

    return True