import logging
import json
import voluptuous as vol
import os

from homeassistant.util.yaml import load_yaml, dump
from homeassistant.components.lock import LockDevice
from homeassistant.const import (STATE_LOCKED, STATE_UNLOCKED)
import polyhome.util.algorithm as checkcrc

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'lock'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
ENENT_ZIGBEE_RECV = 'zigbee_data_event'

# 0x80,0x0,0x51,0x7b,0xb,0x44,0x51,0x7b,0x63,0x2,0x13,0x7,0x17,0x1,0x32,0xff,0x61
CMD_LOCK_OPEN  = [0x80, 0x00, 0x51, 0x7b, 0xb, 0x44, 0x51, 0x7b, 0x63, \
                    0x2, 0x13, 0x7, 0x17, 0x1, 0x32, 0xff, 0x61]
CMD_LOCK_CLOSE = [0x80, 0x00, 0x51, 0x7b, 0xb, 0x44, 0x51, 0x7b, 0x63, \
                    0x2, 0x13, 0x7, 0x17, 0x2, 0x33, 0xff, 0x63]


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Yale lock platform."""
    locks = []
    if discovery_info is not None:
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        locks.append(HoLiShiLock(hass, config, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            locks.append(HoLiShiLock(hass, config, device, device_config))

    add_devices(locks, True)

    open(hass.config.config_dir + '/lock_key.yaml' , 'r')
    
    def event_zigbee_msg_handle(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
        """ A0包类: 1.主动上报 2.心跳 3.设备入网 4.getstatus 5.执行失败重发 6.广播情景设定 7.发现机制(针对平台)
        8.判断设备是否为有校
        """        
        # '0xa0', '0xc6', '0x51', '0x7b', '0xd', '0x55', '0x51', '0x7b', '0x74', '0x2', '0x13', '0x7', 
        # '0x17', '0x5', '0x99', '0x89', '0x58', '0xff', '0xf9'
        if pack_list[0] == '0xa0' and pack_list[8] == '0x74':
            """这一层级判断A0和设备类型"""
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in locks if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            if pack_list[9] == '0x2' and pack_list[-2] == '0xff':
                key_mgr = LockKeyManager(hass, config)
                key_mgr.edit_friendly_name(dev.mac, pack_list[10:13])     
        if pack_list[0] == '0xa0' and pack_list[5] == '0x0' and pack_list[8] == '0xcc':
            """心跳"""
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in locks if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
        if pack_list[0] == '0xc0':
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


class HoLiShiLock(LockDevice):
    """HoLiShi lock Class."""

    def __init__(self, hass, config, device, dev_conf):
        """Initialize an PolyLock."""
        self._hass = hass
        self._config = config
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._state = None
        self._available = True

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
    def is_locked(self):
        """Return true if lock is locked."""
        return self._state == STATE_LOCKED

    def set_available(self, state):
        self._available = state

    def lock(self, **kwargs):
        """Lock the device."""
        self._state = STATE_LOCKED
        self.schedule_update_ha_state()
        mac = self._mac.split('#')
        CMD_LOCK_CLOSE[2], CMD_LOCK_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_LOCK_CLOSE[6], CMD_LOCK_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        key_mgr = LockKeyManager(self._hass, self._config)
        lock_key = key_mgr.get_friendly_name(self._mac)
        CMD_LOCK_CLOSE[10] = int(lock_key[0].replace('0x', ''), 16)
        CMD_LOCK_CLOSE[11] = int(lock_key[1].replace('0x', ''), 16)
        CMD_LOCK_CLOSE[12] = int(lock_key[2].replace('0x', ''), 16)
        CMD_LOCK_CLOSE[14] = checkcrc.sumup(CMD_LOCK_CLOSE[10:14])
        resu_crc = checkcrc.xorcrc_hex(CMD_LOCK_CLOSE)
        CMD_LOCK_CLOSE[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {'data': CMD_LOCK_CLOSE})

    def unlock(self, **kwargs):
        """Unlock the device."""
        self._state = STATE_UNLOCKED
        self.schedule_update_ha_state()
        mac = self._mac.split('#')
        CMD_LOCK_OPEN[2], CMD_LOCK_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_LOCK_OPEN[6], CMD_LOCK_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        key_mgr = LockKeyManager(self._hass, self._config)
        lock_key = key_mgr.get_friendly_name(self._mac)  
        CMD_LOCK_OPEN[10] = int(lock_key[0].replace('0x', ''), 16)
        CMD_LOCK_OPEN[11] = int(lock_key[1].replace('0x', ''), 16)
        CMD_LOCK_OPEN[12] = int(lock_key[2].replace('0x', ''), 16)
        CMD_LOCK_OPEN[14] = checkcrc.sumup(CMD_LOCK_OPEN[10:14])
        resu_crc = checkcrc.xorcrc_hex(CMD_LOCK_OPEN)
        CMD_LOCK_OPEN[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {'data': CMD_LOCK_OPEN})


class LockKeyManager(object):
    """All FriendlyName Manager."""
    
    def __init__(self, hass, config):
        self._hass = hass
        self._config = config
        self._path = hass.config.path('lock_key.yaml')
        
    def edit_friendly_name(self, dev_mac, lock_key):
        """Edit id friendlyname"""
        current = self._read_config('lock_key.yaml')
        self._write_friendly_name(current, dev_mac, lock_key)
        self._write(self._path, current)

    def del_friendly_name(self, name_id):
        """Edit id friendlyname"""
        current = self._read_config('lock_key.yaml')
        self._delete_value(current, name_id)
        self._write(self._path, current)

    def get_friendly_name(self, name_id):
        current = self._read_config('lock_key.yaml')
        name = current.get(name_id, None)
        return name

    def _read_config(self, filename):
        """Read the config."""
        current = self._read(self._hass.config.path(filename))
        if not current:
            current = {}
        return current

    def _read(self, path):
        """Read YAML helper."""
        if not os.path.isfile(path):
            return None
        return load_yaml(path)
    
    def _write_friendly_name(self, current, key, alias):
        """Set value."""        
        name = {key: alias}
        current.update(name)
    
    def _write(self, path, data):
        """Write YAML helper."""
        data = dump(data)
        with open(path, 'w', encoding='utf-8') as outfile:
            outfile.write(data)

    def _delete_value(self, data, key):
        """Delete value."""
        value = self._get_value(data, key)
        if value is not None:
            del data[key]

    def _get_value(self, data, config_key):
        """Get value."""
        for k, v in data.items():
            if k == config_key:
                return v    
        return None