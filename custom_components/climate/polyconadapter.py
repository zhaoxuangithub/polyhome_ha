import logging
import json
import time
import os

from polyhome.util.crc16 import createarraymodbus as crcmod
from polyhome.util.misc import startaddrswitch as strswitch
from polyhome import GroupsManager, FriendlyNameManager, DevicePluginManager
from polyhome.util.misc import (
    sDaiKinInnerStateMap, sDaiKinInnerStateMapReverse, inttobin16str_noreverse,
    sDaiKinInnerControlMap, sDaiKinInnerControlMapReverse, inttobin16str_reverse)

from homeassistant.util.yaml import load_yaml, dump
from homeassistant.helpers import discovery
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import track_utc_time_change
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE, ATTR_FAN_MODE, ATTR_OPERATION_MODE,
    ATTR_SWING_MODE, PLATFORM_SCHEMA, STATE_AUTO, STATE_COOL, STATE_DRY,
    STATE_FAN_ONLY, STATE_HEAT, ClimateDevice)
from homeassistant.util.temperature import convert
from homeassistant.const import (ATTR_TEMPERATURE, CONF_HOST, CONF_NAME, TEMP_CELSIUS)
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
    """Set up the conadapter platform."""

    time_init = 0
    unsub_listen_init = None

    climates = []

    if discovery_info is not None:
        inner_list = discovery_info['inner_list']
        if inner_list is not None:
            for inner in inner_list:
                device = {'name': discovery_info['name'] + inner, 'mac': discovery_info['mac']}
                climates.append(PolyConAdapter(hass, device, config, '1-' + inner))
            # print('1-----------1 climates.len == ' + str(len(climates)))
        else:
            climates_init = discovery_info['mac']
            # print('2-----------2 climates_init_mac == ' + discovery_info['mac'])
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            climates.append(PolyConAdapter(hass, device, config, ''))
            # print('3-----------3 climates_init_mac == ' + mac)


    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
        
        if pack_list[0] == '0xa0' and pack_list[5] == '0x15' and pack_list[8] == '0x70':
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            # dev = next((dev for dev in climates if dev.mac == mac_str), None)
            # for dev in climates:
            #     if dev is not None and dev.mac == mac_str:
            # dev.set_available(True)
            # dev.heart_beat()
        if pack_list[0] == '0xc0' and pack_list[6] == '0x40':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            # 这里处理子设备状态
        if pack_list[0] == '0xc0' and pack_list[6] == '0x41':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in climates if dev.mac == mac_str), None)
            for dev in climates:
                if dev is not None and dev.mac == mac_str:
                    dev.set_available(False)
        if pack_list[0] == '0xa0' and pack_list[5] == '0x15' and pack_list[8] == '0xcc':
            """heart beat"""
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            # dev = next((dev for dev in climates if dev.mac == mac_str), None)
            # for dev in climates:
            #     if dev is not None and dev.mac == mac_str:
            #         dev.set_available(True)
            #         dev.heart_beat()
        if pack_list[0] == '0xa0' and pack_list[5] == '0x15' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            # print('状态包')
            # dev = next((dev for dev in climates if dev.mac == mac_str), None)
            # for dev in climates:
            #     if dev is not None and dev.mac == mac_str:
            #         dev.set_available(True)
            #         dev.heart_beat()
        """ 这里处理艾瑞柯的上报命令 """
        if pack_list[0] == '0xa0' and pack_list[8] == '0x74' and pack_list[9] == '0x1' and pack_list[10] == '0x4':
            #0xa0 0xaa 0x9 0xcc 0xb 0x55 0x9 0xcc 0x74 0x1 0x4 0x2 0x0 0x1 0x78 0xf0 0xae
            if pack_list[11] != 0:
                mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
                mac_str = mac_l + '#' + mac_h
                dev = next((dev for dev in climates if dev.mac == mac_str), None)
                if dev is not None:
                    addr, count = int(pack_list[9], 16), int(pack_list[11], 16)
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
                        # print('con1 == ' + con1)
                        dev.handle_connect_status(con1)
 
                    # update_inner_connect_dev(mac_str, '1110000000000000')
                    # update_inner_connect_dev(mac_str, con1)
                elif count == 12 and len(data) == 12:
                    dev = next((dev for dev in climates if dev.mac == mac_str and dev.is_read), None)
                    if dev is None:
                        return
                    dev.set_read(False)
                    dev.heart_beat()
                    print('读状态返回')
                    # read_current_state_back(dev, data, count)

        if pack_list[0] == '0xa0' and pack_list[8] == '0x74' and pack_list[9] == '0x1' and pack_list[10] == '0x6':
            # 写回包
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in climates if dev.mac == mac_str and dev.is_control), None)
            if dev is None:
                return
            dev.set_control(False)
            dev.heart_beat()
            # print('写回包')
            # if dev.inner_addr is not None:
            #     data = pack_list[11:13]
            #     data[0] = int(data[0], 16)
            #     data[1] = int(data[1], 16)
            #     inneraddrint = sDaiKinInnerControlMap.get(dev.inner_addr)
            #     if (data[0] * 256 + data[1] + 40001) - inneraddrint <= 2:
            #         dev.back_inner_control_data(dev.inner_addr)

    def read_current_state_back(dev, data, count):
        """空调转接器read state data回包"""
        if dev.inner_addr is not None:
            for i in range(count):
                data[i] = int(data[i], 16)
            # "10" / "20" / "30" / "40" / "50"
            air_vol = hex(data[0] & 0xf0).replace('0x', '')
            # "0" / "1"
            run_state = hex(data[1] & 0x01).replace('0x', '')
            # "0" / "1" / "2" / "3" / "7"
            mode_state = hex(data[3] & 0x0f).replace('0x', '')
            # 设定温度
            operation_temp = str((data[4] * 256 + data[5]) // 10)
            # 室内温度
            indoor_temp = str((data[8] * 256 + data[9]) // 10)
            # 传感器是否正常 '0' / '1'
            sensor_normal = '1' if ((data[10] * 256 + data[11]) == 0x8000) else '0'
            dev.back_inner_current_state_data(run_state, air_vol, mode_state, operation_temp,
                                                indoor_temp, sensor_normal, dev.inner_addr)

    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)

    def time_changed_read_status(now):
        nonlocal time_init
        time_init += 1
        if time_init == 8:
            for device in climates:
                device.read_connect_status()
        if time_init == 12:
            for device in climates:
                if device.state:
                    device.read_climate_connect_inner()
                else:
                    print('%s Adapter is OffLine', device.mac)
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

    def __init__(self, hass, device, dev_conf, inner_addr):
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
        # print('Adapter Status: {%s}', state)
        self._state = state

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

    def read_inner_connect_state_command(self, addr):
        """发送读取室内机连接状态命令"""
        # print('update inner_addr == '+self.inner_addr)
        mac = self._mac.split('#')
        addr = int(addr, 16)
        CMD_READ[2], CMD_READ[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_READ[6], CMD_READ[7] = int(mac[0], 16), int(mac[1], 16)
        listraddr = strswitch(30002 - 30001)
        count = 4
        data = READ.copy()
        data[0], data[2], data[3], data[-1] = addr, listraddr[0], listraddr[1], count
        liscrc = crcmod(data)
        CMD_READ[-9:-1] = liscrc
        time.sleep(0.15)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_READ})

    def handle_connect_status(self, connect_count):
        """动态添加和删除室内机"""
        print('handle_connect_status')
        connect_count = '1110000000000000'
        if connect_count == '0000000000000000':
            print('No connect device')
        else:
            print('has some connect inner')
            for key in range(16):
                if connect_count[key] == '1':
                    entity_id = 'climate.climate' + self._mac.replace('#', '') + str(key)
                    friendly_name = '艾瑞柯'
                    component = 'climate'
                    platform = 'polyaricc'
                    data = {'devices': {self._mac: {'name': 'climate' + self._mac.replace('#', '') + str(key)}}, 'platform': platform}
                    pack = {'plugin_type': component, 'entity_id': entity_id, 'plugin_info': data}
                    discovery.load_platform(self._hass, component, data['platform'], {'name': data['devices'][self._mac]['name'], 'mac': self._mac, 'index': key})
                    name_mgr = FriendlyNameManager(self._hass, self._config)
                    name_mgr.edit_friendly_name(entity_id, friendly_name + str(key))

    def heart_beat(self):
        self._heart_time_stamp = time.time()
