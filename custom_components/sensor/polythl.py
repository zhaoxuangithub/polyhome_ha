import logging
import struct
import time

from homeassistant.const import (CONF_API_KEY, CONF_NAME, ATTR_ATTRIBUTION, CONF_ID)
import voluptuous as vol
from datetime import timedelta
from homeassistant.const import (
    CONF_API_KEY, CONF_NAME, CONF_MONITORED_CONDITIONS, ATTR_ATTRIBUTION,
    CONF_LATITUDE, CONF_LONGITUDE)
from homeassistant.const import TEMP_CELSIUS ,CONF_LATITUDE, CONF_LONGITUDE,CONF_API_KEY
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle
from homeassistant.const import (
    CONF_MONITORED_CONDITIONS)


_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string
})

DOMAIN = 'sensor'

POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the sensor platform."""

    sensors = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        sensors.append(THLSensor(hass, device, None, 'temperature', '°C', 'mdi:water-percent'))
        sensors.append(THLSensor(hass, device, None, 'humidity', '%', 'mdi:water-percent'))
        sensors.append(THLSensor(hass, device, None, 'light', 'lux', 'mdi:water-percent'))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            sensors.append(THLSensor(hass, device, device_config, 'temperature', '°C', 'mdi:water-percent'))
            sensors.append(THLSensor(hass, device, device_config, 'humidity', '%', 'mdi:water-percent'))
            sensors.append(THLSensor(hass, device, device_config, 'light', 'lux', 'mdi:water-percent'))

    add_devices(sensors, True)

    # Listener to handle fired events
    """0xa0 0xc3 0x46 0xb1 0xe 0x53 0x46 0xb1 0x7b 
    0x82 0xeb 0xd5 0x41 温度值
    0x3a 0x81 0x22 0x42 湿度值
    0x0 0x6b 光照
    0x8
    """
    def event_zigbee_msg_handle(event):
        pack_list = event.data.get('data')
        if len(pack_list) >= 10 and pack_list[0] == '0xa0' and pack_list[5] == '0x53' and pack_list[8] == '0x7b':
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in sensors:
                if dev.mac == mac_str:
                    dev.set_available(True)
                    if dev.sensor_type == 'temperature':
                        temp = ''
                        for data in pack_list[9:13]:
                            temp += data.replace('0x', '')
                        temp = "{:0>8}".format(temp)
                        temp_f = struct.unpack('f', bytes.fromhex(temp))[0]
                        dev.set_value(round(temp_f, 1))
                    if dev.sensor_type == 'humidity':
                        temp = ''
                        for data in pack_list[13:17]:
                            temp += data.replace('0x', '')
                        temp = "{:0>8}".format(temp)
                        temp_f = struct.unpack('f', bytes.fromhex(temp))[0]
                        dev.set_value(round(temp_f))
                    if dev.sensor_type == 'light':
                        temp = ''
                        for data in pack_list[17:19]:
                            temp += data.replace('0x', '')
                        temp_f = int(temp, 16)
                        dev.set_value(round(temp_f))
        if pack_list[0] == '0xa0' and pack_list[5] == '0x53' and pack_list[8] == '0xcc':
            """heart beat"""
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in sensors:
                if dev.mac == mac_str:
                    dev.set_available(True)
                    dev.heart_beat()
                    if dev.sensor_type == 'temperature':
                        temp = ''
                        for data in pack_list[9:13]:
                            temp += data.replace('0x', '')
                        temp = "{:0>8}".format(temp)
                        temp_f = struct.unpack('f', bytes.fromhex(temp))[0]
                        dev.set_value(round(temp_f, 1))
                    if dev.sensor_type == 'humidity':
                        temp = ''
                        for data in pack_list[13:17]:
                            temp += data.replace('0x', '')
                        temp = "{:0>8}".format(temp)
                        temp_f = struct.unpack('f', bytes.fromhex(temp))[0]
                        dev.set_value(round(temp_f))
                    if dev.sensor_type == 'light':
                        temp = ''
                        for data in pack_list[17:19]:
                            temp += data.replace('0x', '')
                        temp_f = int(temp, 16)
                        dev.set_value(round(temp_f))
        if pack_list[0] == '0xa0' and pack_list[5] == '0x53' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in sensors if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()
            if pack_list[9] == '0x1':
                dev.set_state(True)
            elif pack_list[9] == '0x0':
                dev.set_state(False)

            if not pack_list[22] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[22:27]})
            if not pack_list[27] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[27:32]})
            if not pack_list[32] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[32:37]})
            if not pack_list[37] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[37:42]})
            if not pack_list[42] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[42:47]})
            if not pack_list[47] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[47:52]})
            if not pack_list[52] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[52:57]})
        if len(pack_list) > 7 and pack_list[0] == '0xc0' and pack_list[5] != '0xab' and pack_list[4] != '0x4c':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in sensors if dev.mac == mac_str), None)
            if dev is None:
                return
            if pack_list[6] == '0x40':
                dev.set_available(True)
            elif pack_list[6] == '0x41':
                dev.set_available(False)

    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_msg_handle)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in sensors:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')

    return True


class THLSensor(Entity):
    """Poly Tempreture Hum Light Sensor."""

    def __init__(self, hass, device, dev_config, sensor_type, measurement, icon):
        self._hass = hass
        self._device = device
        self._mac = device['mac']
        self._name = device['name']
        self._sensor_type = sensor_type
        self._measurement = measurement
        self._available = False
        self._state = 0
        self.data = None
        self._icon = icon
        self._heart_timestamp = time.time()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property 
    def mac(self):
        return self._mac

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    @property
    def unit_of_measurement(self):
        """Return the unit this state is expressed in."""
        return self._measurement

    @property
    def sensor_type(self):
        return self._sensor_type

    @property
    def heart_time_stamp(self):
        return self._heart_timestamp

    def set_value(self, value):
        self._state = value

    def set_available(self, available):
        self._available = available

    def update(self):
        return self._state

    def heart_beat(self):
        self._heart_timestamp = time.time()