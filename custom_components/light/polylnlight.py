import logging
import json
import voluptuous as vol
import time

# Import the device class from the component that you want to support
from homeassistant.components.light import Light, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polylnlight'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

# 0x80,0x0,0xb4,0x53,0x6,0x44,0xb4,0x53,0x60,0x1,0x1,0xa2
CMD_OPEN = [0x80, 0x00, 0xb4, 0x53, 0x6, 0x44, 0xb4, 0x53, 0x60, 0x1, 0x1, 0xa2]
CMD_CLOSE = [0x80, 0x00, 0xb4, 0x53, 0x6, 0x44, 0xb4, 0x53, 0x60, 0x1, 0x0, 0xa3]

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome Light platform."""

    lights = []
    if discovery_info is not None:
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        lights.append(PolyLnLight(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            lights.append(PolyLnLight(hass, device, device_config))

    add_devices(lights, True)

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        bytearr = event.data.get('data')
        
        if bytearr[0] == '0xa0' and bytearr[5] == '0x30' and bytearr[8] == '0x70':
            mac_l, mac_h = bytearr[6].replace('0x', ''), bytearr[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                if bytearr[9] == '0x1':
                    dev.set_state(True)
                elif bytearr[9] == '0x0':
                    dev.set_state(False)
        if bytearr[0] == '0xc0' and bytearr[6] == '0x41':
            mac_l, mac_h = bytearr[2].replace('0x', ''), bytearr[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(False)
        if bytearr[0] == '0xc0' and bytearr[6] == '0x40':
            mac_l, mac_h = bytearr[2].replace('0x', ''), bytearr[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(True)
        if bytearr[0] == '0xa0' and bytearr[5] == '0x30' and bytearr[8] == '0xcc':
            """heart beat"""
            mac_l, mac_h = bytearr[2].replace('0x', ''), bytearr[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.heart_beat()
            dev.set_available(True)
            if bytearr[9] == '0x1':
                dev.set_state(True)
            if bytearr[9] == '0x0':
                dev.set_state(False)
            
    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in lights:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')


class PolyLnLight(Light):
    """Representation of an Polyhome Light."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an AwesomeLight."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._state = 'unkown'
        self._available = True
        self._heart_timestamp = time.time()

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def mac(self):
        """Return the display mac of this light."""
        return self._mac

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    @property
    def heart_time_stamp(self):
        return self._heart_timestamp

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def turn_on(self, **kwargs):
        """turn on"""
        mac = self._mac.split('#')
        CMD_OPEN[2], CMD_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OPEN})
        self._state = True

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        mac = self._mac.split('#')
        CMD_CLOSE[2], CMD_CLOSE[3] = int(mac[0],16), int(mac[1],16)
        CMD_CLOSE[6], CMD_CLOSE[7] = int(mac[0],16), int(mac[1],16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CLOSE})
        self._state = False

    def set_state(self, state):
        self._state = state
        self.schedule_update_ha_state()

    def update(self):
        self._state = self.is_on

    def heart_beat(self):
        self._heart_timestamp = time.time()
        entity_id = 'light.' + self.name
        self._hass.services.call('gateway', 'publish_heart_beat', {'entity_id': entity_id})
    