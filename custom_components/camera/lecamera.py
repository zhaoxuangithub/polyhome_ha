import os
import logging
import homeassistant.util.dt as dt_util
from homeassistant.components.camera import Camera
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (CONF_NAME)
import homeassistant.helpers.config_validation as cv
import json
from requests.exceptions import ConnectionError as ConnectError, HTTPError, Timeout
import requests

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'lecamera'
LECAMERAURL = 'https://openapi.lechange.cn/'
LEAPPID = 'lc8ede5a420c914be6'
LEAPPSECRET = '337cb9f908644ca78c09dc1f0d5292'

SERVICE_CAPTURE = 'camera_capture'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the le camera platform."""
    camera_name = config.get(CONF_NAME)

    cameras = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'], 'devid': discovery_info['devid'],
				  'phone': discovery_info['phone'], 'channelid': discovery_info['channelid']}
        cameras.append(LeCamera(hass, config, device))
    else:
        for devid, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'devid': devid, \
					  'phone': device_config['phone'], 'channelid': device_config['channelid']}
            cameras.append(LeCamera(hass, device_config, device))

    add_devices(cameras, True)

    # def service_capture_handler(service):
    #     entity_id = service.data.get('entity_id')
    #     devid = entity_id.replace('camera.camera', '')
    #     dev = next((dev for dev in cameras if dev.devid == devid), None)
    #     if dev is None:
    #         return
    #     camera_capture(dev)
	#
    # def gettoken(phone):
	#
	#
	# hass.services.register('camera', SERVICE_CAPTURE, service_capture_handler)
	#
    # """le camera capture callback"""
    # def camera_capture(dev):
    #     """Get token use phone"""
    #     gettoken(dev.devid)
    #     url = WEIGUOURL + 'd002!retrieveRealData?SENSORID={0}&KEY={1}'.format(mac, KEY)
    #     resp = None
    #     try:
    #         resp = requests.get(url)
    #     except (ConnectError, HTTPError, Timeout, ValueError) as error:
    #         _LOGGER.error("Unable to connect to Dark Sky. %s", error)
    #         return
	#
		# rst_json = resp.json()
		# # print(rst_json)
		# # self._data = {}
		# if rst_json is not None:
		# 	if 'code' in rst_json and 'message' in rst_json:
		# 		code = rst_json['code']
		# 		message = rst_json['message']
		# 		if code == '1' and message == '查询数据成功':
		# 			sensor_data = rst_json['dataObject'][0]['sensorList'][0]['air']
		# 			temperature = sensor_data['temperature']
		# 			humidity = sensor_data['humidity']
		# 			pm25 = sensor_data['pm25']
		# 			co2 = sensor_data['co2']
		# 			voc = sensor_data['voc']
		# 			sensorId = sensor_data['sensorId']
		# 			# self._data['temperature'] = temperature + TYPES['temperature'][1]
		# 			# self._data['co2'] = temperature + TYPES['co2'][1]
		# 			# self._data['voc'] = temperature
		# 			# self._data['humidity'] = temperature + TYPES['humidity'][1]
		# 			# self._data['pm25'] = temperature + TYPES['pm25'][1]
		# 			for device in dev:
		# 				if device._mac == sensorId:
		# 					if device.sensor_type == 'temperature':
		# 						device.set_value(temperature)
		# 					if device.sensor_type == 'humidity':
		# 						device.set_value(humidity)
		# 					if device.sensor_type == 'pm25':
		# 						device.set_value(pm25)
		# 					if device.sensor_type == 'co2':
		# 						device.set_value(co2)
		# 					if device.sensor_type == 'voc':
		# 						device.set_value(voc)
	#
    return True


class LeCamera(Camera):
    """The representation of a Demo camera."""

    def __init__(self, hass, config, device):
        """Initialize demo camera component."""
        super().__init__()
        self._parent = hass
        self._config = config
        self._device = device
        self._name = device['name']
        self._motion_status = False
        self._devid = device['devid']
        self._phone = device['phone']
        self._channelid = device['channelid']

    def camera_image(self):
        """Return a faked still image response."""
        # now = dt_util.utcnow()
        # image_path = os.path.join(
        #     # os.path.dirname(__file__), 'demo_{}.jpg'.format(now.second % 4))
        #     os.path.dirname(__file__), 'lecamera.jpg')
        # with open(image_path, 'rb') as file:
        #     return file.read()
        return None

    @property
    def name(self):
        """Return the name of this camera."""
        return self._name

    @property
    def devid(self):
        """Return the devid of this camera."""
        return self._devid

    @property
    def phone(self):
        """Return the phone of this camera."""
        return self._phone

    @property
    def channelid(self):
        """Return the channelid of this camera."""
        return self._channelid

    @property
    def should_poll(self):
        """Camera should poll periodically."""
        return True

    @property
    def motion_detection_enabled(self):
        """Camera Motion Detection Status."""
        return self._motion_status

    def enable_motion_detection(self):
        """Enable the Motion detection in base station (Arm)."""
        self._motion_status = True

    def disable_motion_detection(self):
        """Disable the motion detection in base station (Disarm)."""
        self._motion_status = False