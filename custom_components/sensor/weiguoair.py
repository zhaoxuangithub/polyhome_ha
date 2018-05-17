import logging
import json
from requests.exceptions import ConnectionError as ConnectError, HTTPError, Timeout
import voluptuous as vol
import time
from datetime import timedelta
from homeassistant.const import (CONF_NAME)
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

import requests
_LOGGER = logging.getLogger(__name__)

DOMAIN = 'weiguoair'
WEIGUOURL = 'http://weiguo.airradio.cn/smart/hwmobile/smart/'
KEY = 'ssdVBdpdshnefs'

TYPES = {
    'temperature': ['temperature', '°C'],
    'co2': ['co2', 'ppm'],
    'voc': ['voc', None],
    'humidity': ['humidity', '%'],
    'pm25': ['pm25', 'μg/m3']
}


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the sensor platform."""

    dev = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'] + '1', 'mac': discovery_info['mac']}
        dev.append(weiguoairSensor(hass, device, None, 'temperature', '°C', 'mdi:thermometer'))
        device = {'name': discovery_info['name'] + '2', 'mac': discovery_info['mac']}
        dev.append(weiguoairSensor(hass, device, None, 'humidity', '%', 'mdi:water-percent'))
        device = {'name': discovery_info['name'] + '3', 'mac': discovery_info['mac']}
        dev.append(weiguoairSensor(hass, device, None, 'pm25', 'μg/m3', 'mdi:blur'))
        device = {'name': discovery_info['name'] + '4', 'mac': discovery_info['mac']}
        dev.append(weiguoairSensor(hass, device, None, 'co2', 'ppm', 'mdi:water-percent'))
        device = {'name': discovery_info['name'] + '5', 'mac': discovery_info['mac']}
        dev.append(weiguoairSensor(hass, device, None, 'voc', '', 'mdi:water-percent'))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'] + '1', 'mac': mac}
            dev.append(weiguoairSensor(hass, device, device_config, 'temperature', '°C', 'mdi:thermometer'))
            device = {'name': device_config['name'] + '2', 'mac': mac}
            dev.append(weiguoairSensor(hass, device, device_config, 'humidity', '%', 'mdi:water-percent'))
            device = {'name': device_config['name'] + '3', 'mac': mac}
            dev.append(weiguoairSensor(hass, device, device_config, 'pm25', 'μg/m3', 'mdi:blur'))
            device = {'name': device_config['name'] + '4', 'mac': mac}
            dev.append(weiguoairSensor(hass, device, device_config, 'co2', 'ppm', 'mdi:water-percent'))
            device = {'name': device_config['name'] + '5', 'mac': mac}
            dev.append(weiguoairSensor(hass, device, device_config, 'voc', '', 'mdi:water-percent'))

    add_devices(dev, True)

    # device update data
    def handle_data_update_event(call):
        for device in dev:
            if device is not None:
                if device._sensor_type == 'voc':
                    hass.add_job(request_data, device.mac)
        hass.loop.call_later(30, handle_data_update_event, '')

    hass.loop.call_later(30, handle_data_update_event, '')

    def request_data(macl):
        """Get data from cloud"""

        mac = macl.upper()
        url = WEIGUOURL + 'd002!retrieveRealData?SENSORID={0}&KEY={1}'.format(mac, KEY)
        resp = None
        try:
            resp = requests.get(url)
        except (ConnectError, HTTPError, Timeout, ValueError) as error:
            _LOGGER.error("Unable to connect to Dark Sky. %s", error)
            return

        rst_json = resp.json()
        # print(rst_json)
        if rst_json is not None:
            if 'code' in rst_json and 'message' in rst_json:
                code = rst_json['code']
                message = rst_json['message']
                if code == '1' and message == '查询数据成功':
                    sensor_data = rst_json['dataObject'][0]['sensorList'][0]['air']
                    temperature = sensor_data['temperature']
                    humidity = sensor_data['humidity']
                    pm25 = sensor_data['pm25']
                    co2 = sensor_data['co2']
                    voc = sensor_data['voc']
                    sensorId = sensor_data['sensorId'].lower()
                    # self._data['temperature'] = temperature + TYPES['temperature'][1]
                    # self._data['co2'] = temperature + TYPES['co2'][1]
                    # self._data['voc'] = temperature
                    # self._data['humidity'] = temperature + TYPES['humidity'][1]
                    # self._data['pm25'] = temperature + TYPES['pm25'][1]
                    for device in dev:
                        if device._mac == sensorId:
                            if device.sensor_type == 'temperature':
                                device.set_value(temperature)
                            if device.sensor_type == 'humidity':
                                device.set_value(humidity)
                            if device.sensor_type == 'pm25':
                                device.set_value(pm25)
                            if device.sensor_type == 'co2':
                                device.set_value(co2)
                            if device.sensor_type == 'voc':
                                device.set_value(voc)
    # return True


class weiguoairSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, hass, device, dev_conf, sensor_type, measurement, icon):
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._sensor_type = sensor_type
        self._measurement = measurement
        self._available = True
        self._state = 0
        self._data = None
        self._icon = icon

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def mac(self):
        return self._mac

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def unit_of_measurement(self):
        """Return the unit this state is expressed in."""
        return self._measurement

    @property
    def sensor_type(self):
        return self._sensor_type

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.
		Implemented by platform classes.
		"""
        return {'platform': 'weiguoair'}

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    def set_value(self, value):
        self._state = value
        self.schedule_update_ha_state()

    def update(self):
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """
        return self._state

