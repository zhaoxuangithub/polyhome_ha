import logging
import re
import time

import voluptuous as vol

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE, ATTR_FAN_MODE, ATTR_OPERATION_MODE,
    ATTR_SWING_MODE, PLATFORM_SCHEMA, STATE_AUTO, STATE_COOL, STATE_DRY,
    STATE_FAN_ONLY, STATE_HEAT, STATE_OFF, ClimateDevice)
from homeassistant.const import (
    ATTR_TEMPERATURE, CONF_HOST, CONF_NAME, TEMP_CELSIUS)
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string
})

SUPPORT_TARGET_TEMPERATURE = 1
SUPPORT_TARGET_TEMPERATURE_HIGH = 2
SUPPORT_TARGET_TEMPERATURE_LOW = 4
SUPPORT_TARGET_HUMIDITY = 8
SUPPORT_TARGET_HUMIDITY_HIGH = 16
SUPPORT_TARGET_HUMIDITY_LOW = 32
SUPPORT_FAN_MODE = 64
SUPPORT_OPERATION_MODE = 128
SUPPORT_HOLD_MODE = 256
SUPPORT_SWING_MODE = 512
SUPPORT_AWAY_MODE = 1024
SUPPORT_AUX_HEAT = 2048
SUPPORT_ON_OFF = 4096

HA_STATE_TO_DAIKIN = {
    STATE_FAN_ONLY: 'fan',
    STATE_DRY: 'dry',
    STATE_COOL: 'cool',
    STATE_HEAT: 'hot',
    STATE_AUTO: 'auto',
    STATE_OFF: 'off',
}

POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

# HA_ATTR_TO_DAIKIN = {
#     ATTR_OPERATION_MODE: 'mode',
#     ATTR_FAN_MODE: 'f_rate',
#     ATTR_SWING_MODE: 'f_dir',
#     ATTR_INSIDE_TEMPERATURE: 'htemp',
#     ATTR_OUTSIDE_TEMPERATURE: 'otemp',
#     ATTR_TARGET_TEMPERATURE: 'stemp'
# }

# 0x80,0x0,0xb4,0x53,0x6,0x44,0xb4,0x53,0x60,0x1,0x1,0xa2
CMD_OPEN = [0x80, 0x00, 0xb4, 0x53, 0x6, 0x44, 0xb4, 0x53, 0x60, 0x1, 0x1, 0xa2]
CMD_CLOSE = [0x80, 0x00, 0xb4, 0x53, 0x6, 0x44, 0xb4, 0x53, 0x60, 0x1, 0x0, 0xa3]


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Daikin HVAC platform."""
    climates = []
    if discovery_info is not None:
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        climates.append(PolyDaikin(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            climates.append(PolyDaikin(hass, device, device_config))

    add_devices(climates, True)

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
        
        if pack_list[0] == '0xa0' and pack_list[5] == '0x14' and pack_list[8] == '0x70':
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in climates if dev.mac == mac_str), None)
            if dev is not None:
                if pack_list[9] == '0x1':
                    dev.set_state(True)
                elif pack_list[9] == '0x0':
                    dev.set_state(False)
            """ 这里处理大金空调的上报命令 """
        if pack_list[0] == '0xc0' and pack_list[6] == '0x41':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in climates if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(False)
        if pack_list[0] == '0xc0' and pack_list[6] == '0x40':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in climates if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(True)
        if pack_list[0] == '0xa0' and pack_list[5] == '0x14' and pack_list[8] == '0xcc':
            """heart beat"""
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in climates if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.heart_beat()
            dev.set_available(True)
            if pack_list[9] == '0x1':
                dev.set_state(True)
            if pack_list[9] == '0x0':
                dev.set_state(False)
        if pack_list[0] == '0xa0' and pack_list[5] == '0x14' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in climates if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()
            if pack_list[9] == '0x1':
                dev.set_state(True)
            elif pack_list[9] == '0x0':
                dev.set_state(False)  

    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)


class PolyDaikin(ClimateDevice):
    """Representation of a Daikin HVAC."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an AwesomeLight."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._state = False
        self._available = True
        self._heart_timestamp = time.time()
        self._supported_features = 0

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._supported_features

    @property
    def name(self):
        """Return the name of the thermostat, if any."""
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

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polylnlight'}

    @property
    def temperature_unit(self):
        """Return the unit of measurement which this thermostat uses."""
        return TEMP_CELSIUS

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return 30

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return 20

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return 'current_operation'

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return 'operation_list'

    @property
    def current_fan_mode(self):
        """Return the fan setting."""
        return 'current_fan_mode'

    @property
    def fan_list(self):
        """List of available fan modes."""
        return 'fan_list'

    @property
    def current_swing_mode(self):
        """Return the fan setting."""
        return 'current_swing_mode'

    @property
    def swing_list(self):
        """List of available swing modes."""
        return 'swing_list'

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def set_operation_mode(self, operation_mode):
        """Set HVAC mode."""
        mac = self._mac.split('#')
        CMD_OPEN[2], CMD_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OPEN})
        print('set_operation_mode')

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        print(kwargs)

    def set_fan_mode(self, fan_mode):
        """Set fan mode."""
        mac = self._mac.split('#')
        CMD_OPEN[2], CMD_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OPEN})

    def set_swing_mode(self, swing_mode):
        """Set new target temperature."""
        mac = self._mac.split('#')
        CMD_OPEN[2], CMD_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OPEN})

    def update(self):
        """Retrieve latest state."""
        self.dakin_update()
        self._force_refresh = False

    def dakin_update(self):
        """turn on"""
        mac = self._mac.split('#')
        CMD_OPEN[2], CMD_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OPEN})
