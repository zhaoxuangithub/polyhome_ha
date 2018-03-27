import logging
import json
import voluptuous as vol
import os
import time
import copy

from homeassistant.util.yaml import load_yaml, dump
from homeassistant.components.remote import RemoteDevice
import time
import polyhome.util.algorithm as checkcrc
import polyhome.util.crc16 as crc16
import asyncio
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import track_utc_time_change

_LOGGER = logging.getLogger(__name__)


DOMAIN = 'remoteforward'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
ENENT_ZIGBEE_RECV = 'zigbee_data_event'

SERVICE_LEARN = 'learn_command'

COMMAND_SCHEMA = vol.Schema({
    vol.Required('name'): cv.string
})

# 0x80,0x0,0x2b,0x65,0x10,0x44,0x2b,0x65,0x63,0x1,0x5,0x2,0x6,0x1,0x1,0x3,0x1,0x1,0x0,0x4e,0x95,0x6f
CMD_REMOTE_STUDY_PRE  = [0x80, 0x0, 0x0, 0x0, 0x0, 0x44, 0x0, 0x0, 0x63]
CMD_REMOTE_STUDY = [0x01, 0x05, 0x02, 0x6, 0x1, 0x1, 0x03, 0x1,0x0, 0x0]


CMD_REMOTE_SEND_PRE  = [0x80, 0x0, 0x0, 0x0, 0x0,0x44, 0x0, 0x0, 0x63]
CMD_REMOTE_SEND = [0x01, 0x05, 0x02, 0x6, 0x1, 0x1, 0x05, 0x2, 0x0, 0x0, 0xf, 0x1,0x0, 0x0]

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the RemoteForward platform."""

    remote = []
    if discovery_info is not None:
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        remote.append(PolyReForward(hass, config, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            remote.append(PolyReForward(hass, config, device, device_config))

    add_devices(remote, True)

    open(hass.config.config_dir + '/remote_key.yaml' , 'a')
    
    def event_zigbee_msg_handle(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
  
        # '0xa0', '0xd3', '0x2b', '0x65', '0x11', '0x2', '0x2b', '0x65', '0x70', '0x1', '0x0', '0x0', '0x0', '0x0', '0x0', 
        # '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x11'
        if pack_list[0] == '0xa0' and pack_list[5] == '0x2' and pack_list[8] == '0x70':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in remote if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
        if pack_list[0] =='0xa0' and pack_list[-4] == '0x0':
            # Study Ok: 0xa0 0xbb 0x2b 0x65 0xc 0x55 0x2b 0x65 0x74 0xf 0x24 0xf 0x24 0x1 0x0 0x6c 0x32 0x69 
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in remote if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.study_ok()
        if pack_list[0] =='0xa0' and pack_list[-4] == '0x5':
            # error: 0xa0 0xba 0x2b 0x65 0xc 0x55 0x2b 0x65 0x74 0xf 0x24 0xf 0x24 0x1 0x5 0x6f 0xf2 0xae
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in remote if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.study_error()
        if pack_list[0] == '0xa0' and pack_list[5] == '0x2' and pack_list[8] == '0xcc':
            """heart_beat"""
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in remote if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()
        if pack_list[0] == '0xc0':
            #0xc0 0x0 0x2b 0x65 0x2 0xff 0x40 0x33 
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in remote if dev.mac == mac_str), None)
            if dev is None:
                return    
            if pack_list[6] == '0x41':
                dev.set_available(False)
            if pack_list[6] == '0x40':
                dev.set_available(True)
            now = time.time()
            hass.loop.call_later(12, handle_time_changed_event, '')
            
    hass.bus.listen(ENENT_ZIGBEE_RECV, event_zigbee_msg_handle)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in remote:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')
    
    def service_learn_handler(service):
        entity_id = service.data.get('entity_id')
        key = service.data.get('key')
        name = service.data.get('name', key)
        mac = entity_id.replace('remote.remote', '')
        dev = next((dev for dev in remote if dev.mac.replace('#', '') == mac), None)
        if dev is None:
            return
        dev.study_command(key, name)

    def service_get_remote_keys_handler(service):
        entity_id = service.data.get('entity_id')
        mac = entity_id.replace('remote.remote', '')
        dev = next((dev for dev in remote if dev.mac.replace('#', '') == mac), None)
        if dev is None:
            return
        dev.get_keys()
        

    hass.services.register('remote', SERVICE_LEARN, service_learn_handler)
    hass.services.register('remote', 'get_remote_keys', service_get_remote_keys_handler)

    
class PolyReForward(RemoteDevice):
    """Representation of an Polyhome ReForward Class."""
   
    def __init__(self, hass, config, device, dev_conf):
        """Initialize an PolyReForward."""
        self._hass = hass
        self._config = config
        self._name = device['name']
        self._mac = device['mac']
        self._state = False
        self._available = True
        self._heart_timestamp = time.time()
        self._unsub_listener_study = None
        self._requested_studing = False
        self._time = 0
        self._cur_study_key = None
        self._cur_study_name = None

    @property
    def should_poll(self):
        """polling remote"""
        return False

    @property
    def mac(self):
        return self._mac

    @property
    def name(self):
        """Return the name of the remote if any."""
        return self._name

    @property
    def is_on(self):
        """Return true if remote is on."""
        return self._state

    def turn_on(self, **kwargs):
        """Turn the device on."""
        return

    def turn_off(self, **kwargs):
        """Turn the device off."""
        return 
    
    @property
    def heart_time_stamp(self):
        """heart timestamp"""
        return self._heart_timestamp

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.
        Implemented by platform classes.
        """
        return {'platform': 'polyremoteforward'}

    def set_available(self, state):
        self._available = state

    def heart_beat(self):
        self._heart_timestamp = time.time()
        entity_id = 'remote.' + self.name
        self._hass.services.call('gateway', 'publish_heart_beat', {'entity_id': entity_id})

    def send_command(self, command, **kwargs):
        """Send a command to a device."""
        print(command)
        for com in command:
            self._last_command_sent = com
            mac = self._mac.split('#')
            key_int = int(com)
            CMD_REMOTE_SEND[7] = 0x2
            CMD_REMOTE_SEND[8] = key_int % 256
            CMD_REMOTE_SEND[9] = key_int // 256
            CMD_REMOTE_SEND[12] = key_int % 256
            CMD_REMOTE_SEND[13] = key_int // 256
            CMD_REMOTE_SEND_PRE[2] = int('0x' + mac[0], 16)
            CMD_REMOTE_SEND_PRE[3] = int('0x' + mac[1], 16)
            CMD_REMOTE_SEND_PRE[4] = 4 + len(CMD_REMOTE_SEND) + 2
            CMD_REMOTE_SEND_PRE[6] = int('0x' + mac[0], 16)
            CMD_REMOTE_SEND_PRE[7] = int('0x' + mac[1], 16)
            CMD_SEND16 = crc16.createarray(CMD_REMOTE_SEND)
            result = CMD_REMOTE_SEND_PRE + CMD_SEND16 +[0xff]
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": result})

    def study_command(self, key, name):
        if self._requested_studing == True:
            print('正在学习中')
            return 
        self._requested_studing = True
        self._listen_study()
        self._cur_study_key = key
        self._cur_study_name = name

        mac = self._mac.split('#')
        key_int = int(key)
        CMD_STUDY = copy.deepcopy(CMD_REMOTE_STUDY)
        CMD_REMOTE_STUDY[7] = 0x1
        CMD_STUDY[8] = key_int % 256
        CMD_STUDY[9] = key_int // 256
        CMD_REMOTE_STUDY_PRE[2] = int('0x' + mac[0], 16)
        CMD_REMOTE_STUDY_PRE[3] = int('0x' + mac[1], 16)
        CMD_REMOTE_STUDY_PRE[4] = 4 + len(CMD_STUDY) + 2
        CMD_REMOTE_STUDY_PRE[6] = int('0x' + mac[0], 16)
        CMD_REMOTE_STUDY_PRE[7] = int('0x' + mac[1], 16)
        CMD_STUDY16 = crc16.createarray(CMD_STUDY)
        result = CMD_REMOTE_STUDY_PRE + CMD_STUDY16 + [0xff]
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": result})

    def get_keys(self):
        key_mgr = RemoteKeyManager(self._hass, self._config)
        data_keys = key_mgr.get_friendly_name(self._mac)
        data_obj = {'status':'OK', 'data': {"entity_id": self.entity_id, 'list': data_keys}, 'type': 'get_remote_keys'}
        data_str = {'data': json.dumps(data_obj)}
        self._hass.services.call('poly_mqtt', 'pub_data', data_str)

    def _listen_study(self):
        if self._unsub_listener_study is None:
            self._unsub_listener_study = track_utc_time_change(self._hass, self._time_changed_study)

    def _time_changed_study(self, now):
        """Track time changes."""
        if self._requested_studing:
            self._time += 1
            print(self._time)
            if self._time == 12:
                self.time = 0
                self._requested_studing = False
        else:
            self._study_timeout()

    def study_ok(self):
        if self._requested_studing == True:
            key_mgr = RemoteKeyManager(self._hass, self._config)
            key_mgr.edit_friendly_name(self._mac, {'key': self._cur_study_key, 'name': self._cur_study_name}) 
            data_obj = {'status':'OK', 'data': {'entity_id': self.entity_id, 'key': self._cur_study_key, 'name': self._cur_study_name}, 'type': 'learn_command'}
            data_str = {'data': json.dumps(data_obj)}
            self._hass.services.call('poly_mqtt', 'pub_data', data_str)
            self.reset_flag()
            
    def _study_timeout(self):
        data_obj = {'status':'Error', 'data': {'entity_id': self.entity_id, 'key': self._cur_study_key, 'name': self._cur_study_name}, 'type': 'learn_command'}
        data_str = {'data': json.dumps(data_obj)}
        self._hass.services.call('poly_mqtt', 'pub_data', data_str)
        self.reset_flag()

    def study_error(self):
        data_obj = {'status':'Error', 'data': {'entity_id': self.entity_id, 'key': self._cur_study_key, 'name': self._cur_study_name}, 'type': 'learn_command'}
        data_str = {'data': json.dumps(data_obj)}
        self._hass.services.call('poly_mqtt', 'pub_data', data_str)
        self.reset_flag()

    def reset_flag(self):
        self._time = 0
        self._requested_studing = False  
        self._unsub_listener_study()
        self._unsub_listener_study = None
        self._cur_study_key = None

            
class RemoteKeyManager(object):
    """All FriendlyName Manager."""
    
    def __init__(self, hass, config):
        self._hass = hass
        self._config = config
        self._path = hass.config.path('remote_key.yaml')
        
    def edit_friendly_name(self, dev_mac, value):
        """Edit id friendlyname"""
        current = self._read_config('remote_key.yaml')
        self._write_friendly_name(current, dev_mac, value)
        self._write(self._path, current)

    def del_friendly_name(self, name_id):
        """Edit id friendlyname"""
        current = self._read_config('remote_key.yaml')
        self._delete_value(current, name_id)
        self._write(self._path, current)

    def get_friendly_name(self, name_id):
        current = self._read_config('remote_key.yaml')
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
    
    def _write_friendly_name(self, current, key, value):
        """Set value."""
        print(current)
        data = self._get_value(current, key)  
        if data is not None:
            data.append(value)   
    
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