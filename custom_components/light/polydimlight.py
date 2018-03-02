import logging
from typing import Tuple
import time

import voluptuous as vol

from homeassistant.const import CONF_DEVICES, CONF_NAME
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_TRANSITION, ATTR_COLOR_TEMP,
    ATTR_FLASH, ATTR_XY_COLOR, FLASH_SHORT, FLASH_LONG, ATTR_EFFECT,
    SUPPORT_BRIGHTNESS, Light, PLATFORM_SCHEMA)
import homeassistant.helpers.config_validation as cv
import polyhome.util.algorithm as checkcrc

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polydimlight'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

DEVICE_SCHEMA = vol.Schema({
    vol.Optional(CONF_NAME): cv.string
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Optional(CONF_DEVICES, default={}): {cv.string: DEVICE_SCHEMA}, })


# 0x80,0x0,0x5,0x3a,0x7,0x44,0x5,0x3a,0x60,0x1,0x1,0x2d,0x8e
BYTES_OPEN = [0x80, 0x00, 0x5, 0x3a, 0x7, 0x44, 0x5, 0x3a, 0x60, 0x1, 0x1, 0x2d, 0xa3]
BYTES_CLOSE = [0x80, 0x00, 0x5, 0x3a, 0x7, 0x44, 0x5, 0x3a, 0x60, 0x1, 0x0, 0x2d, 0xa3]


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Yeelight bulbs."""
    lights = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        lights.append(PolyDimLight(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            lights.append(PolyDimLight(hass, device, device_config))

    add_devices(lights, True)

    def handle_event(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
        if pack_list[0] == '0xa0' and pack_list[5] == '0xb0':
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                if pack_list[9] == '0x1':
                    dev.set_state(True)
                elif pack_list[9] == '0x0':
                    dev.set_state(False)
                brightness = int(pack_list[10].replace('0x', ''), 16)
                dev.set_brightness(brightness)
        if pack_list[0] == '0xc0' and pack_list[6] == '0x41':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(False)  
        if pack_list[0] == '0xa0' and pack_list[5] == '0xb0' and pack_list[8] == '0xcc':
            """heart beat"""
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            if dev is not None:
                if pack_list[9] == '0x1':
                    dev.set_state(True)
                elif pack_list[9] == '0x0':
                    dev.set_state(False)
                brightness = int(pack_list[10].replace('0x', ''), 16)
                dev.set_brightness(brightness)
            dev.heart_beat()
        if pack_list[0] == '0xa0' and pack_list[5] == '0xb0' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()
            if pack_list[9] == '0x1':
                dev.set_state(True)
            elif pack_list[9] == '0x0':
                dev.set_state(False)
            brightness = int(pack_list[10].replace('0x', ''), 16)
            dev.set_brightness(brightness)
        
    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, handle_event)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in lights:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')


class PolyDimLight(Light):
    """Representation of a light."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an AwesomeLight."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._state = True
        self._available = True
        self._brightness = 0
        self._is_on = None
        self._supported_features = SUPPORT_BRIGHTNESS
        self._heart_timestamp = time.time()

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    @property
    def name(self):
        """Return the name of the device if any."""
        return self._name

    @property
    def mac(self):
        """Return the display mac of this light."""
        return self._mac

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._state

    @property
    def brightness(self):
        """Return the brightness of this light between 1..255."""
        return self._brightness

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    @property
    def heart_time_stamp(self):
        return self._heart_timestamp

    def set_brightness(self, bright):
        """Set light brightness."""
        brightness = 255 - bright * (255 / 120)
        self._brightness = brightness
        self.schedule_update_ha_state()

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def turn_on(self, **kwargs):
        """turn on"""
        brightness = 120
        if 'brightness' in kwargs:  # passed kwarg overrides config
            bright = int(kwargs.get('brightness'))
            brightness = bright * (120 / 255)
            self._brightness = brightness * (255 / 120)
        mac = self._mac.split('#')
        BYTES_OPEN[2], BYTES_OPEN[3] = int(mac[0],16), int(mac[1],16)
        BYTES_OPEN[6], BYTES_OPEN[7] = int(mac[0],16), int(mac[1],16)
        BYTES_OPEN[11] = int(120 - brightness)
        resu_crc = checkcrc.xorcrc_hex(BYTES_OPEN)
        BYTES_OPEN[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": BYTES_OPEN})
        self._state = True

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        print('close')
        mac = self._mac.split('#')
        BYTES_CLOSE[2], BYTES_CLOSE[3] = int(mac[0],16), int(mac[1],16)
        BYTES_CLOSE[6], BYTES_CLOSE[7] = int(mac[0],16), int(mac[1],16)
        resu_crc = checkcrc.xorcrc_hex(BYTES_CLOSE)
        BYTES_CLOSE[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": BYTES_CLOSE})
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
    