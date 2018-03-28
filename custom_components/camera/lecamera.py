import os
import json
import logging
import requests
import voluptuous as vol

import homeassistant.util.dt as dt_util
import homeassistant.helpers.config_validation as cv
from homeassistant.components.camera import Camera
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (CONF_NAME)
from requests.exceptions import ConnectionError as ConnectError, HTTPError, Timeout


_LOGGER = logging.getLogger(__name__)

DOMAIN = 'lecamera'
LECAMERAURL = 'https://openapi.lechange.cn/'
LEAPPID = 'lc8ede5a420c914be6'
LEAPPSECRET = '337cb9f908644ca78c09dc1f0d5292'

SERVICE_CAPTURE = 'camera_capture'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the le camera platform."""
    
    cameras = []
    if discovery_info is not None:
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
        return False

    @property
    def motion_detection_enabled(self):
        """Camera Motion Detection Status."""
        return self._motion_status

    @property
    def device_state_attributes(self):
        return {'platform': 'lecamera'}

    @property
    def entity_picture(self):
        """Return a link to the camera feed as entity picture."""
        return None

    def camera_image(self):
        """Return a faked still image response."""
        return None

    # def enable_motion_detection(self):
    #     """Enable the Motion detection in base station (Arm)."""
    #     self._motion_status = True

    # def disable_motion_detection(self):
    #     """Disable the motion detection in base station (Disarm)."""
    #     self._motion_status = False