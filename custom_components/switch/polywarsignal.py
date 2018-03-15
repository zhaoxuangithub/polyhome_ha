import logging
import json
import voluptuous as vol
import time

from homeassistant.components.switch import SwitchDevice, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'warsignal'
POLY_MQTT_DOMAIN = 'poly_mqtt_json'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'


#open 0x80,0x0,0x9c,0xa5,0x6,0x44,0x9c,0xa5,0x60,0x2,0x1,0xa1 mac 9c a5
CMD_OPEN = [0x80, 0x0, 0x9c, 0xa5, 0x6, 0x44, 0x9c, 0xa5, 0x60, 0x2, 0x1, 0xa1]
#close 0x80,0x0,0x9c,0xa5,0x6,0x44,0x9c,0xa5,0x60,0x2,0x0,0xa0 mac 9c a5
CMD_CLOSE = [0x80, 0x0, 0x9c, 0xa5, 0x6, 0x44, 0x9c, 0xa5, 0x60, 0x2, 0x0, 0xa0]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """ Setup the Polyhome warsignal platform. """

    warsignals = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        warsignals.append(PolyWarsignal(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            warsignals.append(PolyWarsignal(hass, device, device_config))

    add_devices(warsignals, True)

    # Listener to handle fired events
    """0xa0 0xc6 0x46 0x34 0x11 0x60 0x46 0x34 0x70 0x0 0x0 0x0 0x0 0x0 0x0
    0x0 0x0 0x0 0x0 0x0 0x0 0x0 0x7"""
    def event_zigbee_msg_handle(event):
        pack_list = event.data.get('data')
        if pack_list[0] == '0xa0' and pack_list[5] == '0x60':
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in warsignals if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            if pack_list[8] == '0x70':
                """locat test"""
                if pack_list[9] == '0x1':
                    dev.set_state(True)
                elif pack_list[9] == '0x0':
                    dev.set_state(False)
        if pack_list[0] == '0xa0' and pack_list[5] == '0x60' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in warsignals if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()
            if pack_list[9] == '0x1':
                dev.set_state(True)
            elif pack_list[9] == '0x0':
                dev.set_state(False)
        if pack_list[0] == '0xc0' and pack_list[5] != '0xab' and pack_list[4] != '0x4c':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in warsignals if dev.mac == mac_str), None)
            if dev is None:
                return
            if pack_list[6] == '0x40':
                dev.set_available(True)
            elif pack_list[6] == '0x41':
                dev.set_available(False)
        if pack_list[0] == '0xa0' and pack_list[5] == '0x60' and pack_list[8] == '0xcc':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in warsignals if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()

    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_msg_handle)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in warsignals:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')

    return True


class PolyWarsignal(SwitchDevice):
    """Representation of an Polyhome Warsignal."""

    def __init__(self, hass, device, dev_config):
        """Initialize an PolyWarsignal"""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_config
        self._state = None
        self._available = True
        self._heart_timestamp = time.time()

    @property
    def name(self):
        """name"""
        return self._name

    @property
    def mac(self):
        """mac"""
        return self._mac

    @property
    def is_on(self):
        """state"""
        return self._state

    @property
    def available(self):
        """available"""
        return self._available

    @property
    def heart_time_stamp(self):
        return self._heart_timestamp

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polywarsignal'}

    def set_available(self, available):
        self._available = available

    def set_state(self, state):
        self._state = state
        self.schedule_update_ha_state()

    def turn_on(self):
        """turn on"""
        mac = self._mac.split('#')
        CMD_OPEN[2] = CMD_OPEN[6] = int(mac[0], 16)
        CMD_OPEN[3] = CMD_OPEN[7] = int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {'data': CMD_OPEN})
        self._state = True

    def turn_off(self):
        """turn off"""
        mac = self._mac.split('#')
        CMD_CLOSE[2] = CMD_CLOSE[6] = int(mac[0], 16)
        CMD_CLOSE[3] = CMD_CLOSE[7] = int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {'data': CMD_CLOSE})
        self._state = False

    def update(self):
        """update status"""
        self._state = self.is_on

    def heart_beat(self):
        self._heart_timestamp = time.time()

