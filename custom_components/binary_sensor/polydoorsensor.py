import logging
import voluptuous as vol
import time

from homeassistant.components.binary_sensor import (BinarySensorDevice)
import homeassistant.helpers.config_validation as cv

DOMAIN = 'door'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    "icon": {
        True: "bell-ring",
        False: "bell",
        None: "bell"
    }
}

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome binary_sensor platform."""

    doors = []
    if discovery_info is not None:
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        doors.append(PolySensorBinarySensor(hass, device))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            doors.append(PolySensorBinarySensor(hass, device))

    add_devices(doors, True)

    def event_zigbee_recv_handler(call):
        """Listener to handle fired events."""
        pack_list = call.data.get('data')
        mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
        mac_str = mac_l + '#' + mac_h
        dev = next((dev for dev in doors if dev.mac == mac_str), None)
        if dev is not None:
            if pack_list[0] == '0xa0' and pack_list[9] == '0xd':
                # 0xa0 0xc4 0x11 0x5 0x5 0x40 0x11 0x5 0x79 0xd 0x55
                dev.set_state(False)
            if pack_list[0] == '0xa0' and pack_list[9] == '0x1':
                # 0xa0 0xc6 0x11 0x5 0x5 0x40 0x11 0x5 0x79 0x1 0x5b
                dev.set_state(True)
            if pack_list[0] == '0xa0' and pack_list[5] == '0x40' and pack_list[8] == '0x78':
                # '0xa0', '0xd8', '0x11', '0x5', '0x13', '0x40', '0x11', '0x5', '0x78', '0x0', '0x0', '0x0',
                # '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x6', '0xf5', '0xa0'
                dev.set_available(True)
                dev.heart_beat()
                
    hass.bus.listen('zigbee_data_event', event_zigbee_recv_handler)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in doors:
            if round(now - device.heart_time_stamp) > 60 * 40:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')


class PolySensorBinarySensor(BinarySensorDevice):
    """an Polyhome Door Sensor Class."""

    def __init__(self, hass, device):
        """Initialize an PolyDoor."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._state = True
        self._available = True
        self._keys = ['0', '1']
        self._heart_timestamp = time.time()

    @property
    def name(self):
        """device name"""
        return self._name

    @property
    def mac(self):
        """device mac"""
        return self._mac

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        return self._state

    @property
    def icon(self):
        """Get an icon to display."""
        state_icon = SENSOR_TYPES["icon"][self._state]
        return "mdi:{}".format(state_icon)

    @property
    def available(self):
        """Return True if entity is available."""
        return True

    @property
    def heart_time_stamp(self):
        """heart beat time stamp"""
        return self._heart_timestamp

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polydoorsensor'}

    def set_available(self, available):
        """update available property"""
        self._available = available
        self.schedule_update_ha_state()

    def set_state(self, state):
        """update state"""
        self._state = state
        self.schedule_update_ha_state()

    def update(self):
        """update"""
        return self.is_on

    def heart_beat(self):
        """update heart beat"""
        self._heart_timestamp = time.time()
