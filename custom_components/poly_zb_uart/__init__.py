"""
Support for Automation Device Specification (ADS).

For more details about this component, please refer to the documentation.
https://home-assistant.io/components/ads/
"""
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'poly_zb_uart'

def setup(hass, config):
    """Set up the ADS component."""

    hass.services.register(DOMAIN, 'polyzigbee_data', 'polyzigbee_handle', schema='services.yaml')

    return True