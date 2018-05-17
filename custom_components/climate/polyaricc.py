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
SUPPORT_TARGET_TEMPERATURE_HIGH = 2
SUPPORT_TARGET_TEMPERATURE_LOW = 4
SUPPORT_TARGET_HUMIDITY = 8
SUPPORT_TARGET_HUMIDITY_HIGH = 16
SUPPORT_TARGET_HUMIDITY_LOW = 32
SUPPORT_FAN_MODE = 64
SUPPORT_OPERATION_MODE = 128
SUPPORT_HOLD_MODE = 256
SUPPORT_SWING_MODE = 512
SUPPORT_AWAY_MODE = 1024
SUPPORT_AUX_HEAT = 2048
SUPPORT_ON_OFF = 4096

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

    climates = []

    if discovery_info is not None:
        print(discovery_info)
        b_find = False
        for state in hass.states.async_all():
            state_dict = state.as_dict()
            entity_id = 'climate.' + discovery_info['name']
            if entity_id == state_dict['entity_id']:
                b_find = True
        if b_find == False:
            device = {'name': discovery_info['name'], 'mac': discovery_info['mac'], 'index': discovery_info['index']}
            climates.append(PolyAraccClimate(hass, device, None, ''))
            
    add_devices(climates, True)

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
        
        # if pack_list[0] == '0xc0' and pack_list[6] == '0x40':
        #     mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
        #     mac_str = mac_l + '#' + mac_h
        #     # 这里处理子设备状态
        # if pack_list[0] == '0xc0' and pack_list[6] == '0x41':
        #     mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
        #     mac_str = mac_l + '#' + mac_h
        #     dev = next((dev for dev in climates if dev.mac == mac_str), None)
        #     for dev in climates:
        #         if dev is not None and dev.mac == mac_str:
        #             dev.set_available(False)
        """ 这里处理艾瑞柯的上报命令 """
        if pack_list[0] == '0xa0' and pack_list[8] == '0x74':
            # '0xa0', '0xbb', '0x9', '0xcc', '0x15', '0x55', '0x9', '0xcc', '0x74', '0x1', '0x4', '0xc', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x95', '0xb7', '0x4'
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in climates if dev.mac == mac_str), None)
            if dev is not None:
                if pack_list[9] == '0x1' and pack_list[10] == '0x4':
                    addr, count = int(pack_list[9], 16), int(pack_list[11], 16)
                    data = pack_list[12:12 + count]
                    if count == 12 and len(data) == 12:
                        # dev.set_read(False)
                        print('读状态返回')
                        dev.read_current_state_back(data, count)
                        if hass.data['arric']['mac'] == dev.mac:
                            hass.data['arric']['index'] = hass['data']['arric']['index'] + 1
                            hass.services.call('aricc', 'read_arric_device_state', {'mac': hass['data']['arric']['mac'], 'index': hass['data']['arric']['index']})

        if pack_list[0] == '0xa0' and pack_list[8] == '0x74' and pack_list[9] == '0x1' and pack_list[10] == '0x6':
            # 写回包
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in climates if dev.mac == mac_str and dev.is_control), None)
            if dev is None:
                return
            dev.set_control(False)
            dev.heart_beat()
            print('写回包')
            # if dev.inner_addr is not None:
            #     data = pack_list[11:13]
            #     data[0] = int(data[0], 16)
            #     data[1] = int(data[1], 16)
            #     inneraddrint = sDaiKinInnerControlMap.get(dev.inner_addr)
            #     if (data[0] * 256 + data[1] + 40001) - inneraddrint <= 2:
            #         dev.back_inner_control_data(dev.inner_addr)

    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)

    def read_arric_device_state_service(call):
        print('3')
        index = call.data.get('index')
        mac = call.data.get('mac')
        for climate in climates:
            if climate.mac == mac and climate.inner_addr == index:
                climate.read_inner_state_command()

    hass.services.register('aricc', 'read_arric_device_state', read_arric_device_state_service)

    # device online check
    def handle_time_changed_event(call):
        for climate in climates:
            if climate.inner_addr == 0:
                print('1')
                hass.add_job(climate.read_inner_state_command)
        hass.loop.call_later(15, handle_time_changed_event, '')
        
    hass.loop.call_later(15, handle_time_changed_event, '')


class PolyAraccClimate(ClimateDevice):
    """Polyhome AraccClimate."""

    def __init__(self, hass, device, dev_conf, inner_addr):
        """Initialize an PolyConAdapter."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._state = False
        self._on = True
        self._operation_temp = ''
        self._indoor_temp = '28'
        self._operation_mode = 'idle'
        self._fan_mode = '20'
        self._current_temperature = 30
        self._target_temperature = 15
        self._target_temperature_high = 32
        self._target_temperature_low = 18
        self._inner_addr = device['index']
        self._is_read = False
        self._is_control = False
        self._available = True
        self._addr = 1
        self._unit_of_measurement = '°C'

    @property
    def name(self):
        """Return the name of the thermostat, if any."""
        return self._name

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_ON_OFF | SUPPORT_OPERATION_MODE | SUPPORT_AUX_HEAT | SUPPORT_FAN_MODE | SUPPORT_TARGET_TEMPERATURE

    @property
    def mac(self):
        """Return the display mac of this light."""
        return self._mac

    @property
    def inner_addr(self):
        """当前室内机地址"""
        return self._inner_addr

    @property
    def state(self):
        """return current state"""
        return self._state

    @property
    def min_temp(self):
        """Return the minimum temperature.最小控制温度"""
        return convert(18, TEMP_CELSIUS, self.temperature_unit)

    @property
    def max_temp(self):
        """Return the maximum temperature.最大控制温度"""
        return convert(32, TEMP_CELSIUS, self.temperature_unit)

    @property
    def current_temperature(self):
        """Return the current temperature.室内温度"""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach.设定温度"""
        return self._target_temperature

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle.模式"""
        return self._operation_mode

    @property
    def current_fan_mode(self):
        """Return the fan setting.风速"""
        return self._fan_mode

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polycurtain2'}

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def target_temperature_high(self):
        """Return the highbound target temperature we try to reach."""
        return self._target_temperature_high

    @property
    def target_temperature_low(self):
        """Return the lowbound target temperature we try to reach."""
        return self._target_temperature_low

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        # 0: 通风 1: 制热 2: 制冷 3: 自动 4: 除湿
        return ['通风', '制热', '制冷', '自动', '除湿', '关机']

    @property
    def is_on(self):
        """Return true if the device is on."""
        return self._on

    @property
    def fan_list(self):
        """Return the list of available fan modes."""
        # 10 20 30 40 50
        return ['极低', '低', '中', '高', '极高']

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature.温度调节步长"""
        return 1

    def turn_aux_heat_on(self):
        """Turn auxiliary heater on."""
        self._aux = True
        self.schedule_update_ha_state()

    def turn_aux_heat_off(self):
        """Turn auxiliary heater off."""
        self._aux = False
        self.schedule_update_ha_state()

    def turn_on(self):
        """Turn on."""
        self._on = True
        self.schedule_update_ha_state()

    def turn_off(self):
        """Turn off."""
        self._on = False
        self.schedule_update_ha_state()

    def set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if kwargs.get('temperature') is not None:
            self._target_temperature = kwargs.get('temperature')
            self.control_inner_command(self._inner_addr, '4', self._target_temperature)
        self.schedule_update_ha_state()

    def set_operation_mode(self, operation_mode):
        """Set HVAC mode.模式"""
        print('operation_mode == ' + operation_mode)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CONTROL})
        self._operation_mode = operation_mode
        self.schedule_update_ha_state()

    def set_fan_mode(self, fan_mode):
        """Set fan mode.风速"""
        print('fan_mode == '+fan_mode)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CONTROL})
        self._fan_mode = fan_mode
        self.schedule_update_ha_state()

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def update(self):
        """Retrieve latest state."""
        return self._state

    def read_inner_state_command(self):
        """发送读取某个室内机状态命令"""
        mac = self._mac.split('#')
        CMD_READ[2], CMD_READ[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_READ[6], CMD_READ[7] = int(mac[0], 16), int(mac[1], 16)
        print(str(self._addr) + '-' + str(self._inner_addr))
        inneraddrint = sDaiKinInnerStateMap.get(str(self._addr) + '-' + str(self._inner_addr))
        print('inneraddrint read == ' + str(inneraddrint))
        listraddr = strswitch(inneraddrint - 30001)
        count = 6
        data = READ.copy()
        data[0], data[2], data[3], data[-1] = self._addr, listraddr[0], listraddr[1], count
        liscrc = crcmod(data)
        CMD_READ[-9:-1] = liscrc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_READ})

        if self.inner_addr == 0:
            self._hass.data = {'arric': {'mac': self._mac, 'index': self._inner_addr}}
            print('2')

    def read_current_state_back(self, data, count):
        """空调转接器read state data回包"""
        for i in range(count):
            data[i] = int(data[i], 16)
        # "10" / "20" / "30" / "40" / "50"
        air_vol = hex(data[0] & 0xf0).replace('0x', '')
        # "0" / "1"
        run_state = hex(data[1] & 0x01).replace('0x', '')
        # "0" / "1" / "2" / "3" / "7"
        mode_state = hex(data[3] & 0x0f).replace('0x', '')
        # 设定温度
        operation_temp = (data[4] * 256 + data[5]) // 10
        # 室内温度
        indoor_temp = (data[8] * 256 + data[9]) // 10
        # 传感器是否正常 '0' / '1'
        sensor_normal = '1' if ((data[10] * 256 + data[11]) == 0x8000) else '0'
        # set value
        self._fan_mode = air_vol
        self._on = run_state
        self._operation_mode = mode_state
        self._current_temperature = indoor_temp
        self._target_temperature = operation_temp
        self.schedule_update_ha_state()

    def heart_beat(self):
        self._heart_time_stamp = time.time()
        entity_id = 'climae.' + self.name
        self._hass.services.call('gateway', 'publish_heart_beat', {'entity_id': entity_id})

    def control_inner_command(self, inneraddr, type, value):
        """发送功能控制数据"""
        mac = self._mac.split('#')
        addr = self._addr
        CMD_CONTROL[2], CMD_CONTROL[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_CONTROL[6], CMD_CONTROL[7] = int(mac[0], 16), int(mac[1], 16)
        inneraddrint = sDaiKinInnerControlMap.get(str(self._addr) + '-' + str(self.inner_addr))
        print('inneraddrint control == ' + str(inneraddrint))
        if type == '1':
            #on/off
            lis = [0xff, 0xff]
            state = None
            if value == '0':
                lis[1] = 0x60
                state = False
            elif value == '1':
                lis[1] = 0x61
                state = True
            listraddr = strswitch(inneraddrint - 40001)
            data = CONTROL.copy()
            data[0], data[2], data[3] = addr, listraddr[0], listraddr[1]
            data[4], data[5] = lis[0], lis[1]
            liscrc = crcmod(data)
            CMD_CONTROL[-9:-1] = liscrc
            if state is not None:
                self.set_state(state)
        if type == '2':
            #10/20/30/40/50风速LL/L/M/H/HH
            lis = [0xff, 0xff]
            lis[0] = int(value, 16)
            listraddr = strswitch(inneraddrint - 40001)
            data = CONTROL.copy()
            data[0], data[2], data[3] = addr, listraddr[0], listraddr[1]
            data[4], data[5] = lis[0], lis[1]
            liscrc = crcmod(data)
            CMD_CONTROL[-9:-1] = liscrc
            self.set_fan_mode(value)
        if type == '3':
            # 0/1/2/3/7模式通风/制热/制冷/自动/除湿
            lis = [0x0, 0xff]
            lis[1] = int(value, 16)
            listraddr = strswitch(inneraddrint + 1 - 40001)
            data = CONTROL.copy()
            data[0], data[2], data[3] = addr, listraddr[0], listraddr[1]
            data[4], data[5] = lis[0], lis[1]
            liscrc = crcmod(data)
            CMD_CONTROL[-9:-1] = liscrc
            self.set_operation_mode(value)
        if type == '4':
            #温度18-32
            lis = [0xff, 0xff]
            inttobinstr = inttobin16str_noreverse(int(value)*10)
            lis[0] = int(inttobinstr[0:8], 2)
            lis[1] = int(inttobinstr[8:], 2)
            listraddr = strswitch(inneraddrint + 2 - 40001)
            data = CONTROL.copy()
            data[0], data[2], data[3] = addr, listraddr[0], listraddr[1]
            data[4], data[5] = lis[0], lis[1]
            liscrc = crcmod(data)
            CMD_CONTROL[-9:-1] = liscrc