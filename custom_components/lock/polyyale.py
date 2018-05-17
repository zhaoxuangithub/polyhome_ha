import logging
import json
import voluptuous as vol
import time

from homeassistant.components.lock import LockDevice
from homeassistant.const import (STATE_LOCKED, STATE_UNLOCKED)

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'lock'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
ENENT_ZIGBEE_RECV = 'zigbee_data_event'

# 0x80,0x0,0xb4,0x53,0x6,0x44,0xb4,0x53,0x60,0x1,0x1,0xa2
CMD_LOCK_OPEN  = [0x80, 0x00, 0x9, 0x7f, 0xb, 0x44, 0x9, 0x7f, 0x63, \
                    0x05, 0x19, 0x02, 0x11, 0x0A, 0x0F, 0x14]
CMD_LOCK_CLOSE = [0x80, 0x00, 0x9, 0x7f, 0xb, 0x44, 0x9, 0x7f, 0x63, \
                    0x05, 0x19, 0x02, 0x12, 0x09, 0x0F, 0x14]


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Yale lock platform."""
    locks = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        locks.append(YaleLock(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            locks.append(YaleLock(hass, device, device_config))

    add_devices(locks, True)

    def event_zigbee_msg_handle(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
        """ A0包类: 1.主动上报 2.心跳 3.设备入网 4.getstatus 5.执行失败重发 6.广播情景设定 7.发现机制(针对平台)
        8.判断设备是否为有校
        """
        if pack_list[0] == '0xa0' and pack_list[5] == '0x0' and pack_list[8] == '0x70':
            """这一层级判断A0和设备类型"""
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in locks if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
        elif pack_list[0] == '0xa0' and pack_list[5] == '0x0' and pack_list[8] == '0xcc':
            """心跳"""
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in locks if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
        elif pack_list[0] == '0xc0':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in locks if dev.mac == mac_str), None)
            if dev is None:
                return
            if pack_list[6] == '0x41':
                dev.set_available(False)
            if pack_list[6] == '0x40':
                dev.set_available(True)
    
    hass.bus.listen(ENENT_ZIGBEE_RECV, event_zigbee_msg_handle)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in locks:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')


class YaleLock(LockDevice):
    """Yale Lock Class."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an PolyLock."""
        self._hass = hass
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._state = None
        self._available = True
        self._heart_timestamp = time.time()

    @property
    def should_poll(self):
        """polling lock"""
        return False

    @property
    def mac(self):
        return self._mac

    @property
    def name(self):
        """Return the name of the lock if any."""
        return self._name

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    @property
    def is_locked(self):
        """Return true if lock is locked."""
        return self._state == STATE_LOCKED

    @property
    def heart_time_stamp(self):
        """heart timestamp"""
        return self._heart_timestamp

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polyyale'}

    def set_available(self, state):
        self._available = state

    def lock(self, **kwargs):
        """Lock the device."""
        self._state = STATE_LOCKED
        self.schedule_update_ha_state()
        mac = self._mac.split('#')
        CMD_LOCK_CLOSE[2], CMD_LOCK_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_LOCK_CLOSE[6], CMD_LOCK_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {'data': CMD_LOCK_CLOSE})

    def unlock(self, **kwargs):
        """Unlock the device."""
        self._state = STATE_UNLOCKED
        self.schedule_update_ha_state()
        mac = self._mac.split('#')
        CMD_LOCK_OPEN[2], CMD_LOCK_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_LOCK_OPEN[6], CMD_LOCK_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {'data': CMD_LOCK_OPEN})

    def heart_beat(self):
        self._heart_timestamp = time.time()
        entity_id = 'lock.' + self.name
        self._hass.services.call('gateway', 'publish_heart_beat', {'entity_id': entity_id})
