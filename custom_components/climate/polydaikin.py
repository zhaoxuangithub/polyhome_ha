import logging
import time

from polyhome.util.crc16 import createarraymodbus as crcmod
from polyhome.util.misc import startaddrswitch as strswitch
from polyhome.util.misc import (sDaiKinInnerStateMap, inttobin16str_noreverse, sDaiKinInnerControlMap)
from homeassistant.components.climate import (PLATFORM_SCHEMA, ClimateDevice)
from homeassistant.util.temperature import convert
from homeassistant.const import (CONF_NAME, TEMP_CELSIUS)
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

DOMAIN = 'polydaikin'
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
    """Set up the polydaikin platform."""

    climates = []
    climates_new = []
    read_mac = None
    read_index = -1

    if discovery_info is not None:
        print(discovery_info)
        inner_list = discovery_info['inner_list']
        if inner_list is not None:
            for index in inner_list:
                b_find = False
                for state in hass.states.async_all():
                    state_dict = state.as_dict()
                    entity_id = 'climate.' + discovery_info['name'] + str(index)
                    if entity_id == state_dict['entity_id']:
                        b_find = True
                        device = {'name': discovery_info['name'] + str(index), 'mac': discovery_info['mac'],
                                  'index': index}
                        climates.append(PolyDaiKinClimate(hass, device, None))
                if not b_find:
                    device = {'name': discovery_info['name'] + str(index), 'mac': discovery_info['mac'],
                              'index': index}
                    climates_new.append(PolyDaiKinClimate(hass, device, None))
    add_devices(climates_new, True)
    if len(climates_new) > 0:
        climates = climates + climates_new

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        nonlocal read_mac, read_index
        pack_list = event.data.get('data')
        """ 这里处理大金空调的上报命令 """
        if pack_list[0] == '0xa0' and pack_list[8] == '0x74':
            # '0xa0', '0xbb', '0x9', '0xcc', '0x15', '0x55', '0x9', '0xcc', '0x74', '0x1', '0x4', '0xc', '0x0', '0x0', \
            # '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x95', '0xb7', '0x4'
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in climates:
                if dev is not None and dev.mac == mac_str:
                    if pack_list[9] == '0x1' and pack_list[10] == '0x4':
                        addr, count = int((pack_list[9].replace('0x', '')), 16), int((pack_list[11].replace('0x', '')), 16)
                        data = pack_list[12:12 + count]
                        if count == 12 and len(data) == 12:
                            if read_mac == dev.mac and read_index == dev.index:
                                print('读回包')
                                dev.read_current_state_back(data, count)
                                read_index = dev.index + 1
                                for climate in climates:
                                    if climate is not None and climate.mac == read_mac and climate.index == read_index:
                                        climate.read_inner_state_command()
        if pack_list[0] == '0xa0' and pack_list[8] == '0x74' and pack_list[9] == '0x1' and pack_list[10] == '0x6':
            # 写回包
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in climates:
                if dev is not None and dev.mac == mac_str:
                    print('写回包')

    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)

    def service_climate_adapter_change_handler(service):
        state = service.data.get('daikin').get('state')
        mac = service.data.get('daikin').get('mac')
        for climate in climates:
            if climate.mac == mac:
                climate.set_state(state)
    hass.services.register('daikin', 'daikin_adapter_state_change', service_climate_adapter_change_handler)

    # device current state check
    def handle_time_changed_event(call):
        nonlocal read_mac, read_index
        for climate in climates:
            if climate is not None and climate.index == 0:
                read_mac, read_index = climate.mac, climate.index
                hass.add_job(climate.read_inner_state_command)
        hass.loop.call_later(33, handle_time_changed_event, '')

    hass.loop.call_later(33, handle_time_changed_event, '')


class PolyDaiKinClimate(ClimateDevice):
    """Polyhome DaiKinClimate."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an PolyDaiKinClimate."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._state = True
        self._on = True
        self._operation_mode = '3'
        self._fan_mode = '30'
        self._current_temperature = 30
        self._target_temperature = 27
        self._target_temperature_high = 32
        self._target_temperature_low = 18
        self._index = device['index']
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
    def index(self):
        """当前室内机地址"""
        return self._index

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
        return {'platform': 'polydaikin', 'run_state': self._on, 'operation_mode': self._operation_mode, \
                'fan_mode': self._fan_mode, 'current_temperature': self._current_temperature, 'index': self._index}

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
        # 0:通风 1:制热 2:制冷 3:自动 7:除湿 off:关机
        return ['off', '0', '1', '2', '3', '7']

    @property
    def is_on(self):
        """Return true if the device is on."""
        return self._on

    @property
    def fan_list(self):
        """Return the list of available fan modes."""
        # 10:极低 20:低 30:中 40:高 50:极高
        return ['10', '20', '30', '40', '50']

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature.温度调节步长"""
        return 1

    def turn_on(self):
        """Turn on."""
        print('turn on')
        self._on = True
        self.control_inner_command(self._index, '1', '1')
        self.schedule_update_ha_state()

    def turn_off(self):
        """Turn off."""
        print('turn off')
        self._on = False
        self.control_inner_command(self._index, '1', '0')
        self.schedule_update_ha_state()

    def set_temperature(self, **kwargs):
        """Set new target temperatures.
        {'temperature': 28.0, 'entity_id': ['climate.climate9cc0']}
        """
        if kwargs.get('temperature') is not None:
            temperature = round(kwargs.get('temperature'))
            print('temperature == ' + str(temperature))
            self._target_temperature = temperature
            self.control_inner_command(self._index, '4', self._target_temperature)
        self.schedule_update_ha_state()

    def set_operation_mode(self, operation_mode):
        """Set mode.模式"""
        print('operation_mode == ' + operation_mode)
        if operation_mode == 'off':
            self.turn_off()
        else:
            if not self._on:
                self.turn_on()
                time.sleep(0.15)
            self._operation_mode = operation_mode
            self.control_inner_command(self._index, '3', self._operation_mode)
            self.schedule_update_ha_state()


    def set_fan_mode(self, fan_mode):
        """Set fan mode.风速"""
        print('fan_mode == ' + fan_mode)
        self._fan_mode = fan_mode
        self.control_inner_command(self._index, '2', self._fan_mode)
        self.schedule_update_ha_state()

    def set_state(self, state):
        self._state = state
        self.schedule_update_ha_state()

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def update(self):
        """Retrieve latest state."""
        return self._on

    def read_inner_state_command(self):
        """发送读取某个室内机状态命令"""
        mac = self._mac.split('#')
        CMD_READ[2], CMD_READ[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_READ[6], CMD_READ[7] = int(mac[0], 16), int(mac[1], 16)
        inneraddrint = sDaiKinInnerStateMap.get(str(self._addr) + '-' + str(self._index))
        listraddr = strswitch(inneraddrint - 30001)
        count = 6
        data = READ.copy()
        data[0], data[2], data[3], data[-1] = self._addr, listraddr[0], listraddr[1], count
        liscrc = crcmod(data)
        CMD_READ[-9:-1] = liscrc
        time.sleep(0.15)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_READ})

    def read_current_state_back(self, data, count):
        """读室内机状态read state data回包"""
        for i in range(count):
            data[i] = int((data[i].replace('0x', '')), 16)
        # "10" / "20" / "30" / "40" / "50"
        fan_mode = hex(data[0] & 0xf0).replace('0x', '')
        # "0" / "1"
        run_state = hex(data[1] & 0x01).replace('0x', '')
        # "0" / "1" / "2" / "3" / "7"
        mode_state = hex(data[3] & 0x0f).replace('0x', '')
        # 设定温度
        temperature = (data[4] * 256 + data[5]) // 10
        # 室内温度
        if data[8] >= 0x80:
            current_temperature = -(((data[8] & 0x0f) * 256 + data[9]) // 10)
        else:
            current_temperature = (data[8] * 256 + data[9]) // 10
        # 传感器是否正常 '0' / '1'
        # sensor_normal = '1' if ((data[10] * 256 + data[11]) == 0x8000) else '0'

        # set value test value
        self._fan_mode = '30' if fan_mode == '0' else fan_mode
        self._on = True if run_state == '0' else False
        self._operation_mode = '3' if mode_state == '0' else mode_state
        self._current_temperature = 30 if current_temperature == 0 else current_temperature
        self._target_temperature = 27 if temperature == 0 else temperature
        self.schedule_update_ha_state()

    def heart_beat(self):
        self._heart_time_stamp = time.time()
        entity_id = 'climae.' + self.name
        self._hass.services.call('gateway', 'publish_heart_beat', {'entity_id': entity_id})

    def control_inner_command(self, index, type, value):
        """发送功能控制数据"""
        mac = self._mac.split('#')
        addr = self._addr
        CMD_CONTROL[2], CMD_CONTROL[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_CONTROL[6], CMD_CONTROL[7] = int(mac[0], 16), int(mac[1], 16)
        inneraddrint = sDaiKinInnerControlMap.get(str(self._addr) + '-' + str(index))
        print('inneraddrint control == ' + str(inneraddrint))
        if type == '1':
            #on/off
            lis = [0xff, 0xff]
            state = None
            if value == '0':
                lis[1] = 0x60
            elif value == '1':
                lis[1] = 0x61
            listraddr = strswitch(inneraddrint - 40001)
            data = CONTROL.copy()
            data[0], data[2], data[3] = addr, listraddr[0], listraddr[1]
            data[4], data[5] = lis[0], lis[1]
            liscrc = crcmod(data)
            CMD_CONTROL[-9:-1] = liscrc
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CONTROL})
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
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CONTROL})
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
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CONTROL})
        if type == '4':
            #温度18-32
            lis = [0xff, 0xff]
            inttobinstr = inttobin16str_noreverse(value*10)
            lis[0] = int(inttobinstr[0:8], 2)
            lis[1] = int(inttobinstr[8:], 2)
            listraddr = strswitch(inneraddrint + 2 - 40001)
            data = CONTROL.copy()
            data[0], data[2], data[3] = addr, listraddr[0], listraddr[1]
            data[4], data[5] = lis[0], lis[1]
            liscrc = crcmod(data)
            CMD_CONTROL[-9:-1] = liscrc
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CONTROL})