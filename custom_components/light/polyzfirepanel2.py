import logging
import json
import voluptuous as vol
import time

# Import the device class from the component that you want to support
from homeassistant.components.light import Light, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from polyhome import JSONEncoder

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polyzfirepanel2'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

# 0x80,0x0,0xb4,0x53,0x6,0x44,0xb4,0x53,0x60,0x1,0x1,0xa2
CMD_OPEN = [0x80, 0x00, 0xb4, 0x53, 0x6,
            0x44, 0xb4, 0x53, 0x60, 0x1, 0x1, 0xa2]
CMD_CLOSE = [0x80, 0x00, 0xb4, 0x53, 0x6,
             0x44, 0xb4, 0x53, 0x60, 0x1, 0x0, 0xa3]

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome light platform."""

    panels = []
    if discovery_info is not None:
        device = {'name': discovery_info['name'] +
                  '1', 'mac': discovery_info['mac'], 'way': 1}
        device1 = {'name': discovery_info['name'] +
                   '2', 'mac': discovery_info['mac'], 'way': 2}
        panels.append(PolyZfirePanel2(hass, device, None))
        panels.append(PolyZfirePanel2(hass, device1, None))
    else:
        for mac, device_config in config['devices'].items():
            device_1 = {
                'name': device_config['name'] + '1', 'mac': mac, 'way': 1}
            device_2 = {
                'name': device_config['name'] + '2', 'mac': mac, 'way': 2}
            panels.append(PolyZfirePanel2(hass, device_1, device_config))
            panels.append(PolyZfirePanel2(hass, device_2, device_config))

    add_devices(panels, True)

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')

        if pack_list[0] == '0xa0' and pack_list[5] == '0x3D':
            mac_l, mac_h = pack_list[6].replace(
                '0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in panels if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(True)
                if pack_list[9] == '0x1':
                    dev.trigger('1')
                if pack_list[9] == '0x2':
                    dev.trigger('2')
        if pack_list[0] == '0xa0' and pack_list[5] == '0x3d' and pack_list[8] == '0x70':
            """'0xa0', '0xc9', '0x28', '0xd8', '0x11', '0x3d', '0x28', '0xd8', '0x70', '0x0', '0x1', '0x0',
            '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x34'
            """
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in panels:
                if mac_str in dev.mac:
                    mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
                    mac_str = mac_l + '#' + mac_h
                    dev.set_available(True)
                    if dev.way == 1 and pack_list[9] == '0x1':
                        dev.set_state(True)
                    if dev.way == 1 and pack_list[9] == '0x0':
                        dev.set_state(False)
                    if dev.way == 2 and pack_list[10] == '0x1':
                        dev.set_state(True)
                    if dev.way == 2 and pack_list[10] == '0x0':
                        dev.set_state(False)
        if pack_list[0] == '0xa0' and pack_list[5] == '0x3d' and pack_list[8] == '0xcc':
            # '0xa0', '0xd6', '0x4e', '0x41', '0x34', '0x31', '0x4e', '0x41', '0xcc', '0x0', '0x1', '0x0', \
            # '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0x41'
            mac_l, mac_h = pack_list[6].replace(
                '0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in panels:
                if mac_str in dev.mac:
                    mac_l, mac_h = pack_list[6].replace(
                        '0x', ''), pack_list[7].replace('0x', '')
                    mac_str = mac_l + '#' + mac_h
                    dev.set_available(True)
                    dev.heart_beat()
                    if dev.way == 1 and pack_list[9] == '0x1':
                        dev.set_state(True)
                    if dev.way == 1 and pack_list[9] == '0x0':
                        dev.set_state(False)
                    if dev.way == 2 and pack_list[10] == '0x1':
                        dev.set_state(True)
                    if dev.way == 2 and pack_list[10] == '0x0':
                        dev.set_state(False)
        if pack_list[0] == '0xa0' and pack_list[5] == '0x3d' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in panels:
                if mac_str in dev.mac:
                    mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
                    mac_str = mac_l + '#' + mac_h
                    dev.set_available(True)
                    dev.heart_beat()
                    if dev.way == 1 and pack_list[9] == '0x1':
                        dev.set_state(True)
                    if dev.way == 1 and pack_list[9] == '0x0':
                        dev.set_state(False)
                    if dev.way == 2 and pack_list[10] == '0x1':
                        dev.set_state(True)
                    if dev.way == 2 and pack_list[10] == '0x0':
                        dev.set_state(False)

    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in panels:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')

    hass.loop.call_later(60, handle_time_changed_event, '')


class PolyZfirePanel2(Light):
    """Representation of an Polyhome ZfirePanel2 Class."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an PolyZfirePanel2."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._way = device['way']
        self._config = dev_conf
        self._state = False
        self._available = True
        self._keys = ['1', '2']
        self._heart_timestamp = time.time()

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def mac(self):
        """Return the display mac of this light."""
        return self._mac

    @property
    def way(self):
        """Return the display mac of this light."""
        return self._way

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    @property
    def supported_features(self):
        """Flag Light features that are supported."""
        return 0

    @property
    def heart_time_stamp(self):
        return self._heart_timestamp

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polyzfirepanel2'}

    def set_state(self, state):
        self._state = state
        self.schedule_update_ha_state()

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def turn_on(self, **kwargs):
        """turn on"""
        mac = self._mac.split('#')
        CMD_OPEN[2], CMD_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[-3] = self._way
        CMD_OPEN[-2] = 0x1
        self._hass.services.call(
            POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OPEN})
        self._state = True

    def turn_off(self, **kwargs):
        """turn off"""
        mac = self._mac.split('#')
        CMD_CLOSE[2], CMD_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_CLOSE[6], CMD_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        CMD_CLOSE[-3] = self._way
        CMD_CLOSE[-2] = 0x0
        self._hass.services.call(
            POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CLOSE})
        self._state = False

    def trigger(self, key_id):
        if key_id in self._keys:
            self._hass.bus.fire('light.' + self._name + '_' + key_id + '_pressed')
            for state in self._hass.states.async_all():
                state_dict = state.as_dict()
                if state_dict['entity_id'] == 'light.' + self.name:
                    new_state = state
                    msg = json.dumps(new_state, sort_keys=True, cls=JSONEncoder)
                    json_msg = json.loads(msg)
                    json_msg['attributes']['button'] = key_id
                    pub_obj = {'status': 'OK', 'data': json_msg, 'type': 'state_change'}
                    data_str = {'data': json.dumps(pub_obj)}
                    self._hass.services.call('poly_mqtt', 'mqtt_pub_state_change', data_str)

    def update(self):
        self._state = self.is_on

    def heart_beat(self):
        self._heart_timestamp = time.time()
