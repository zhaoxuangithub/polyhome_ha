import logging
import voluptuous as vol
import time

# Import the device class from the component that you want to support
from homeassistant.components.light import ATTR_BRIGHTNESS, Light, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'switch'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

# 0x80,0x0,0xb4,0x53,0x6,0x44,0xb4,0x53,0x60,0x1,0x1,0xa2
CMD_OPEN = [0x80, 0x00, 0x46, 0xb1, 0x7, 0x44, 0xd, 0x7, 0x60, 0x0, 0x1, 0xa2]
CMD_CLOSE = [0x80, 0x00, 0x46, 0xb1, 0x7, 0x44, 0xd, 0x7, 0x60, 0x0, 0x1, 0xa3]

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome Light platform."""

    lights = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'] + '1', 'mac': discovery_info['mac'], 'way': 1}
        device1 = {'name': discovery_info['name'] + '2', 'mac': discovery_info['mac'], 'way': 2}
        lights.append(PolyLight(hass, device, None))
        lights.append(PolyLight(hass, device1, None))
    else:
        for mac, device_config in config['devices'].items():
            device_1 = {'name': device_config['name'] + '1', 'mac': mac, 'way': 1}
            device_2 = {'name': device_config['name'] + '2', 'mac': mac, 'way': 2}
            lights.append(PolyLight(hass, device_1, device_config))
            lights.append(PolyLight(hass, device_2, device_config))

    add_devices(lights, True)

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')

        if  pack_list[0] == '0xa0' and pack_list[5] == '0x31' and pack_list[8] == '0x70':
            """'0xa0', '0xd7', '0x4e', '0x41', '0x11', '0x31', '0x4e', '0x41', '0x70', '0x1', '0x1', '0x0', 
            '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x27'
            """
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in lights:
                if mac_str in dev.mac:
                    mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
                    mac_str = mac_l + '#' + mac_h
                    dev.set_available(True)
                    if dev.way == 1 and pack_list[9] == '0x1':
                        dev.set_state(True)
                    if dev.way == 1 and pack_list[9] == '0x0':
                        dev.set_state(False)
                    if dev.way == 2 and pack_list[10] == '0x1':
                        dev.set_state(True)
                    if dev.way == 2 and pack_list[10] == '0x0':
                        dev.set_state(False)
        if  pack_list[0] == '0xa0' and pack_list[5] == '0x31' and pack_list[8] == '0xcc':
            # '0xa0', '0xd6', '0x4e', '0x41', '0x34', '0x31', '0x4e', '0x41', '0xcc', '0x0', '0x1', '0x0', \
            # '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0x41'
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in lights:
                if mac_str in dev.mac:
                    mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
                    mac_str = mac_l + '#' + mac_h
                    dev.set_available(True)
                    dev.heart_beat()
                    if dev.way == 1 and pack_list[9] == '0x1':
                        dev.set_state(True)
                    if dev.way == 1 and pack_list[9] == '0x0':
                        dev.set_state(False)
                    if dev.way == 2 and pack_list[10] == '0x1':
                        dev.set_state(True)
                    if dev.way == 2 and pack_list[10] == '0x0':
                        dev.set_state(False)
        if pack_list[0] == '0xa0' and pack_list[5] == '0x31' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in lights:
                if mac_str in dev.mac:
                    mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
                    mac_str = mac_l + '#' + mac_h
                    dev.set_available(True)
                    dev.heart_beat()
                    if dev.way == 1 and pack_list[9] == '0x1':
                        dev.set_state(True)
                    if dev.way == 1 and pack_list[9] == '0x0':
                        dev.set_state(False)
                    if dev.way == 2 and pack_list[10] == '0x1':
                        dev.set_state(True)
                    if dev.way == 2 and pack_list[10] == '0x0':
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


class PolyLight(Light):
    """Polyhome Light."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an AwesomeLight."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._way = device['way']
        self._config = dev_conf
        self._state = None
        self._available = True
        self._heart_time_stamp = time.time()

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def mac(self):
        """Return the display mac of this light."""
        return self._mac

    @property
    def way(self):
        """Return the display mac of this light."""
        return self._way

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
        return self._heart_time_stamp

    def set_state(self, state):
        self._state = state
        self.schedule_update_ha_state()

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def turn_on(self, **kwargs):
        """turn on"""
        mac = self._mac.split('#')
        CMD_OPEN[2], CMD_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[-3] = self._way
        CMD_OPEN[-2] = 0x1
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OPEN})
        self._state = True

    def turn_off(self, **kwargs):
        """turn off"""
        mac = self._mac.split('#')
        CMD_CLOSE[2], CMD_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_CLOSE[6], CMD_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        CMD_CLOSE[-3] = self._way
        CMD_CLOSE[-2] = 0x0
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CLOSE})
        self._state = False

    def update(self):
        self._state = self.is_on

    def heart_beat(self):
        self._heart_time_stamp = time.time()

