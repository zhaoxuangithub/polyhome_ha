import logging
import time

from polyhome.util.crc16 import createarraymodbus as crcmod
from polyhome.util.misc import startaddrswitch as strswitch
from custom_components.poly_config import async_restart
from polyhome import FriendlyNameManager
from polyhome.util.misc import inttobin16str_reverse
from homeassistant.helpers import discovery
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import track_utc_time_change
from homeassistant.components.climate import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string
})
SUPPORT_TARGET_TEMPERATURE = 1
SUPPORT_TARGET_TEMPERATURE_HIGH = 32
SUPPORT_TARGET_TEMPERATURE_LOW = 18

DOMAIN = 'polyconadapter'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

# 0x80,0x0,0xb4,0x53,0x6,0x44,0xb4,0x53,0x60,0x1,0x1,0xa2
CMD_READ = [0x80, 0x0, 0x9, 0xcc, 0xc, 0x44, 0x9, 0xcc, 0x63, 0x1, 0x4, 0x0, 0x0, 0x0, 0x1, 0x31, 0xca, 0x54]
READ = [0x01, 0x04, 0x00, 0x00, 0x00, 0x01]
CMD_CONTROL = [0x80, 0x0, 0x9, 0xcc, 0xc, 0x44, 0x9, 0xcc, 0x63, 0x1, 0x6, 0x0, 0x0, 0x0, 0x1, 0x31, 0xca, 0x54]
CONTROL = [0x01, 0x06, 0xff, 0xff, 0xff, 0xff]
DATA = []


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the polyconadapter platform."""

    time_init = 0
    unsub_listen_init = None
    climates = []

    if discovery_info is not None:
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        climates.append(PolyConAdapter(hass, device, config))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            climates.append(PolyConAdapter(hass, device, config))

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
        
        if pack_list[0] == '0xa0' and pack_list[5] == '0x15' and pack_list[8] == '0x70':
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
        if pack_list[0] == '0xc0' and pack_list[6] == '0x40':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            # 这里处理子设备状态
        if pack_list[0] == '0xc0' and pack_list[6] == '0x41':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
        if pack_list[0] == '0xa0' and pack_list[5] == '0x15' and pack_list[8] == '0xcc':
            """heart beat"""
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
        if pack_list[0] == '0xa0' and pack_list[5] == '0x15' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
        """ 这里处理艾瑞柯的上报命令 """
        if pack_list[0] == '0xa0' and pack_list[8] == '0x74' and pack_list[9] == '0x1' and pack_list[10] == '0x4':
            # 0xa0 0xaa 0x9 0xcc 0xb 0x55 0x9 0xcc 0x74 0x1 0x4 0x2 0x0 0x1 0x78 0xf0 0xae
            if pack_list[11] != 0:
                mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
                mac_str = mac_l + '#' + mac_h
                dev = next((dev for dev in climates if dev.mac == mac_str), None)
                if dev is not None:
                    addr, count = int((pack_list[9].replace('0x', '')), 16), int((pack_list[11].replace('0x', '')), 16)
                    data = pack_list[12:12 + count]
                    if count == 2 and len(data) == 2:
                        """适配器通讯状态回包"""
                        if data[1] == '0x1':
                            dev.set_state(True)
                        else:
                            dev.set_state(False)
                    if count == 8 and len(data) == 8:
                        """空调转接器read connect data回包"""
                        data1 = int(data[0], 16) * 256 + int(data[1], 16)
                        data2 = int(data[2], 16) * 256 + int(data[3], 16)
                        data3 = int(data[4], 16) * 256 + int(data[5], 16)
                        data4 = int(data[6], 16) * 256 + int(data[7], 16)
                        # bin reverse
                        con1 = inttobin16str_reverse(data1)
                        con2 = inttobin16str_reverse(data2)
                        con3 = inttobin16str_reverse(data3)
                        con4 = inttobin16str_reverse(data4)
                        dev.handle_connect_status(con1)

    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)

    def time_changed_read_status(now):
        nonlocal time_init
        time_init += 1
        if time_init == 11:
            for device in climates:
                device.read_connect_status()
        if time_init == 14:
            for device in climates:
                if device.state:
                    device.read_climate_connect_inner()
                else:
                    print('%s Iracc Adapter is OffLine' %(device.mac))
            time_init = 0

    unsub_listen_init = track_utc_time_change(hass, time_changed_read_status)

    def unsub_listen(call):
        nonlocal unsub_listen_init
        unsub_listen_init()
        unsub_listen_init = None

    hass.bus.async_listen_once('homeassistant_stop', unsub_listen)


"""
   空调管理者
"""
class PolyConAdapter(Entity):
    """Representation of a ConAdapter."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an PolyConAdapter."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._state = True
        self._available = True
        self._heart_time_stamp = time.time()

    @property
    def name(self):
        """Return the name of the thermostat, if any."""
        return self._name

    @property
    def mac(self):
        """Return the display mac of this light."""
        return self._mac

    @property
    def state(self):
        """return current state"""
        return self._state

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        return {'platform': 'polyconadapter'}

    def set_state(self, state):
        self._state = state
        b_find = False
        for states in self._hass.states.async_all():
            state_dict = states.as_dict()
            entity_id = 'climate.' + self._name + '0'
            if entity_id == state_dict['entity_id']:
                b_find = True
        if b_find:
            self._hass.services.call('iracc', 'iracc_adapter_state_change', \
                                     {'iracc': {'mac': self._mac, 'state': self._state}})

    def read_connect_status(self):
        """获取适配器状态"""
        mac = self._mac.split('#')
        CMD_READ[2], CMD_READ[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_READ[6], CMD_READ[7] = int(mac[0], 16), int(mac[1], 16)
        listraddr = strswitch(0)
        count = 1
        data = READ.copy()
        data[2], data[3], data[-1] = listraddr[0], listraddr[1], count
        liscrc = crcmod(data)
        CMD_READ[-9:-1] = liscrc
        time.sleep(0.15)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_READ})

    def read_climate_connect_inner(self):
        """获取室内机连接个数"""
        mac = self._mac.split('#')
        CMD_READ[2], CMD_READ[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_READ[6], CMD_READ[7] = int(mac[0], 16), int(mac[1], 16)
        listraddr = strswitch(30002 - 30001)
        count = 4
        data = READ.copy()
        data[0], data[2], data[3], data[-1] = 1, listraddr[0], listraddr[1], count
        liscrc = crcmod(data)
        CMD_READ[-9:-1] = liscrc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_READ})

    def handle_connect_status(self, connect_count):
        """动态添加和删除室内机"""
        print('handle_connect_status == ' + connect_count)
        connect_count = '1110000000000000'
        if connect_count == '0000000000000000':
            print('No connect device')
        else:
            print('has some connect device')
            entity_id = 'climate.climate' + self._mac.replace('#', '')
            connect_list = []
            find_list = []
            for index in range(16):
                if connect_count[index] == '1':
                    connect_list.append(index)
                    b_find = False
                    for state in self._hass.states.async_all():
                        state_dict = state.as_dict()
                        entity_id = 'climate.' + self._name + str(index)
                        if entity_id == state_dict['entity_id']:
                            b_find = True
                    find_list.append(b_find)
                elif connect_count[index] == '0':
                    for states in self._hass.states.async_all():
                        state_dict = states.as_dict()
                        entity_id = 'climate.' + self._name + str(index)
                        if entity_id == state_dict['entity_id']:
                            # restart homeassistant service
                            self._hass.add_job(async_restart(self._hass))
            if len(find_list) > 0 and False in find_list:
                friendly_name = '艾瑞柯'
                component = 'climate'
                platform = 'polyiracc'
                data = {'devices': {self._mac: {'name': 'climate' + self._mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': entity_id, 'plugin_info': data}
                # mgr = DevicePluginManager(hass, config)
                # if mgr.add_plugin(pack):
                discovery.load_platform(self._hass, component, data['platform'],
                                        {'name': data['devices'][self._mac]['name'], 'mac': self._mac,
                                        'inner_list': connect_list})
                name_mgr = FriendlyNameManager(self._hass, self._config)
                for index in range(len(find_list)):
                    if not find_list[index]:
                        name_mgr.edit_friendly_name(pack['entity_id'] + str(connect_list[index]), \
                                                    friendly_name + str(connect_list[index]))

    def heart_beat(self):
        self._heart_time_stamp = time.time()
