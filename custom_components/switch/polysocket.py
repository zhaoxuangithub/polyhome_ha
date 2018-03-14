#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
import asyncio
import time
import voluptuous as vol

from homeassistant.components.switch import (SwitchDevice, PLATFORM_SCHEMA)
from homeassistant.helpers.dispatcher import (async_dispatcher_connect, dispatcher_send)

import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'switch'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
ENENT_ZIGBEE_RECV = 'zigbee_data_event'

# 0x80,0x0,0xb4,0x53,0x6,0x44,0xb4,0x53,0x60,0x1,0x1,0xa2
CMD_OPEN = [0x80, 0x00, 0x2b, 0x2f, 0x6, 0x44, 0x2b, 0x2f, 0x60, 0x1, 0x1, 0xff]
CMD_CLOSE = [0x80, 0x00, 0x2b, 0x2f, 0x6, 0x44, 0x2b, 0x2f, 0x60, 0x1, 0x0, 0xff]

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome Socket platform."""

    sockets = []
    if discovery_info is not None:
        device = {'mac': discovery_info['mac'], 'name': discovery_info['name']}
        sockets.append(PolySocket(hass, device))
    else:
        for mac, device_config in config['devices'].items():
            device = {'mac': mac, 'name': device_config['name']}
            sockets.append(PolySocket(hass, device))

    add_devices(sockets, True)
    
    def event_zigbee_msg_handle(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
        """ A0包类: 1.主动上报 2.心跳 4.getstatus 5.执行失败重发 6.广播情景设定 7.发现机制(针对平台)
        8.判断设备是否为有校
        """
        if pack_list[0] == '0xa0' and pack_list[5] == '0x0' and pack_list[8] == '0x70':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in sockets if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            """local trigger"""
            if pack_list[9] == '0x1':
                dev.set_state(True)
            if pack_list[9] == '0x0':
                dev.set_state(False) 
        if pack_list[0] == '0xa0' and pack_list[5] == '0x0' and pack_list[8] == '0xcc':
            # heart beat
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in sockets if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()
            if pack_list[9] == '0x1':
                dev.set_state(True)
            elif pack_list[9] == '0x0':
                dev.set_state(False)
        if pack_list[0] == '0xa0' and pack_list[5] == '0x0' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in sockets if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()
            if pack_list[9] == '0x1':
                dev.set_state(True)
            elif pack_list[9] == '0x0':
                dev.set_state(False)
        if pack_list[0] == '0xc0':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in sockets if dev.mac == mac_str), None)
            if dev is None:
                return
            if pack_list[6] == '0x41':
                dev.set_available(False)
            elif pack_list[6] == '0x40':
                dev.set_available(True)

    hass.bus.listen(ENENT_ZIGBEE_RECV, event_zigbee_msg_handle)
    
    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in sockets:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')

    # def handle_frame(frame):
    #     print('recv: ' + frame)
    # async_dispatcher_connect(hass, 'signal_zigbee_frame_recv', handle_frame)


class PolySocket(SwitchDevice):
    """Polyhome Socket Class."""

    def __init__(self, hass, device):
        """Initialize an PolySocket."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._state = None
        self._available = True
        self._heart_timestamp = time.time()

    @property
    def name(self):
        """name"""
        return self._name

    @property
    def mac(self):
        """mac node"""
        return self._mac

    @property
    def is_on(self):
        """return current state"""
        return self._state

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    @property
    def entity_id(self):
        return 'switch.' + self._name

    @property
    def supported_features(self):
        """Flag Switch features that are supported."""
        return 0

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polysocket'}

    @property
    def heart_time_stamp(self):
        return self._heart_timestamp
    
    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state(True)
    
    def set_state(self, state):
        self._state = state
        self.schedule_update_ha_state(True)

    def turn_on(self):
        """turn on"""
        mac = self._mac.split('#')
        CMD_OPEN[2], CMD_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OPEN})
        self._state = True
        
    def turn_off(self):
        """turn off"""
        mac = self._mac.split('#')
        CMD_CLOSE[2], CMD_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_CLOSE[6], CMD_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CLOSE})
        self._state = False

    def update(self):
        """update status"""
        self._state = self.is_on

    def heart_beat(self):
        self._heart_timestamp = time.time()
        entity_id = 'switch.' + self.name
        self._hass.services.call('gateway', 'publish_heart_beat', {'entity_id': entity_id})
    