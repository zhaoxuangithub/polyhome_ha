import logging
import voluptuous as vol

from homeassistant.components.binary_sensor import (
    BinarySensorDevice, PLATFORM_SCHEMA, DEVICE_CLASSES_SCHEMA)
import homeassistant.helpers.config_validation as cv

DOMAIN = 'smoke'
EVENT_MQTT_RECV = 'poly_mqtt_json'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the PolyhomeSmokeSenser platform."""

    smoke = []
    if discovery_info is not None:
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        smoke.append(PolySensorBinarySensor(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            smoke.append(PolySensorBinarySensor(hass, device, config))

    add_devices(smoke, True)

    def event_zigbee_recv_handler(call):
        """Listener to handle fired events."""
        pack_list = call.data.get('data')
        mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
        mac_str = mac_l + '#' + mac_h
        dev = next((dev for dev in smoke if dev.mac == mac_str), None)
        if dev is not None:
            if pack_list[0] == '0xa0' and pack_list[9] == '0x1':
                # 0xa0 0xc4 0x11 0x5 0x5 0x40 0x11 0x5 0x79 0xd 0x55
                hass.bus.fire('binarysensor.' + dev._name + '_' + 'triggered')

    hass.bus.listen('zigbee_data_event', event_zigbee_recv_handler)


class PolySensorBinarySensor(BinarySensorDevice):
    """Representation of an Polyhome PolySmoke."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an PolySmoke."""
        self._hass = hass
        self._device = device
        self._mac = device['mac']
        self._name = device['name']
        self._config = dev_conf

    @property
    def name(self):
        return self._name

    @property
    def mac(self):
        return self._mac

    @property
    def icon(self):
        """Get an icon to display."""
        return "mdi:smoking-off"

    @property
    def available(self):
        """Return True if entity is available."""
        return True

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polysmokesensor'}

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()
