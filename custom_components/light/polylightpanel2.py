import logging
import json
import voluptuous as vol

# Import the device class from the component that you want to support
from homeassistant.components.light import Light, PLATFORM_SCHEMA
from polyhome import JSONEncoder
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polylightpanel2'
EVENT_MQTT_RECV = 'poly_mqtt_json'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

# 0x80,0x0,0xb4,0x53,0x6,0x44,0xb4,0x53,0x60,0x1,0x1,0xa2
CMD_OPEN = [0x80, 0x00, 0x46, 0xb1, 0x7, 0x44, 0xd, 0x7, 0x61, 0x0, 0x1, 0x1, 0xa2]
CMD_CLOSE = [0x80, 0x00, 0x46, 0xb1, 0x7, 0x44, 0xd, 0x7, 0x61, 0x0, 0x1, 0x0, 0xa3]

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome LightPanel2 platform."""

    lights = []
    if discovery_info is not None:
        device = {'name': discovery_info['name'] + '1', 'mac': discovery_info['mac'], 'way': 1}
        lights.append(PolyLightPanel(hass, device, None))
        device = {'name': discovery_info['name'] + '2', 'mac': discovery_info['mac'], 'way': 2}
        lights.append(PolyLightPanel(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device1 = {'name': device_config['name'] + '1', 'mac': mac, 'way': 1}
            lights.append(PolyLightPanel(hass, device1, device_config))
            device2 = {'name': device_config['name'] + '2', 'mac': mac, 'way': 2}
            lights.append(PolyLightPanel(hass, device2, device_config))

    add_devices(lights, True)

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        bytearr = event.data.get('data')

        if bytearr[0] == '0xa0' and bytearr[8] == '0x73' and bytearr[9] == '0x25':
            """
            '0xa0', '0xbc', '0x1a', '0x62', '0xa', '0x31', '0x1a', '0x62', '0x73', 
            '0x21', '0xd', '0x1', '0x0', '0x0', '0x0', '0x79'
            """ 
            mac_l, mac_h = bytearr[10].replace('0x', ''), bytearr[11].replace('0x', '')
            dev_mac = mac_l + '#' + mac_h
            for dev in lights:
                if dev_mac in dev.mac:
                    mac_l, mac_h = bytearr[2].replace('0x', ''), bytearr[3].replace('0x', '')
                    mac_str = mac_l + '#' + mac_h
                    dev.set_router(mac_str)
                    dev.set_available(True)
                    if dev.way == 1 and bytearr[-4] == '0x1':
                        dev.set_state(True)
                    if dev.way == 1 and bytearr[-4] == '0x0':
                        dev.set_state(False)
                    if dev.way == 2 and bytearr[-3] == '0x1':
                        dev.set_state(True)
                    if dev.way == 2 and bytearr[-3] == '0x0':
                        dev.set_state(False)
        if bytearr[0] == '0xa0' and bytearr[8] == '0x72':
            """0xa0', '0xc7', '0x46', '0xb1', '0x7', '0x53', '0xd', 
            '0x7', '0x72', '0x0', '0x1', '0x1', '0xbc'
            """
            mac_l, mac_h = bytearr[6].replace('0x', ''), bytearr[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in lights:
                if mac_str in dev.mac:
                    dev.set_available(False)
        if bytearr[0] == '0xa0' and bytearr[5] == '0x25' and bytearr[8] == '0x79':
            """panel trigger"""
            mac_l, mac_h = bytearr[6].replace('0x',''), bytearr[7].replace('0x','')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(True)
                if bytearr[9] == '0x1':
                    dev.trigger('1')
                if bytearr[9] == '0x2':
                    dev.trigger('2')

    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)

    def event_zigbee_device_status_handler(event):
        router = event.data.get('router')
        device = event.data.get('device')
        if device[2] == '0x25':
            """ 0x0 -> 0000 0000 The last three is light status
            '0xfe', '0xc5', '0x22', '0x0', '0xff', '0xff'
            """
            mac_l, mac_h = device[0].replace('0x', ''), device[1].replace('0x', '')
            dev_mac = mac_l + '#' + mac_h
            for dev in lights:
                if dev_mac in dev.mac:
                    mac_l, mac_h = router[0].replace('0x', ''), router[1].replace('0x', '')
                    mac_str = mac_l + '#' + mac_h
                    dev.set_router(mac_str)
                    s_int = int(device[3], 16)
                    s_str = bin(s_int).replace('0b', '')
                    s_str = "{:0>2}".format(s_str)
                    if dev.way == 1 and s_str[-1] == '1':
                        dev.set_state(True)
                    if dev.way == 1 and s_str[-1] == '0':
                        dev.set_state(False)
                    if dev.way == 2 and s_str[-2] == '1':
                        dev.set_state(True)
                    if dev.way == 2 and s_str[-2] == '0':
                        dev.set_state(False)
                    
    # Listen Device Status Event
    hass.bus.listen('event_zigbee_device_status', event_zigbee_device_status_handler)


class PolyLightPanel(Light):
    """Representation of an Polyhome LightPanel2 Class."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an Light."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._way = device['way']
        self._config = dev_conf
        self._state = True
        self._router = 'ff#fe'
        self._available = True
        self._keys = ['1', '2']

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
    def supported_features(self):
        """Flag Light features that are supported."""
        return 0
        
    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polylightpanel2'}

    def set_state(self, state):
        self._state = state
        self.schedule_update_ha_state()

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def set_router(self, router):
        self._router = router

    def turn_on(self, **kwargs):
        """turn on"""
        router_mac = self._router.split('#')
        CMD_OPEN[2], CMD_OPEN[3] = int(router_mac[0], 16), int(router_mac[1], 16)
        mac = self._mac.split('#')
        CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[-3] = self._way
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OPEN})
        self._state = True

    def turn_off(self, **kwargs):
        """turn off."""
        router_mac = self._router.split('#')
        CMD_CLOSE[2], CMD_CLOSE[3] = int(router_mac[0], 16), int(router_mac[1], 16)
        mac = self._mac.split('#')
        CMD_CLOSE[6], CMD_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        CMD_CLOSE[-3] = self._way
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CLOSE})
        self._state = False

    def trigger(self, key_id):
        if key_id in self._keys:
            self._hass.bus.fire('binary_sensor.' + self._name  + '_' + key_id + '_pressed')
            for state in self._hass.states.async_all():
                state_dict = state.as_dict()
                if state_dict['entity_id'] == 'binary_sensor.' + self.name:
                    new_state = state
                    msg = json.dumps(new_state, sort_keys=True, cls=JSONEncoder)
                    json_msg = json.loads(msg)
                    json_msg['attributes']['button'] = key_id
                    pub_obj = {'status':'OK', 'data': json_msg, 'type': 'state_change'}
                    data_str = {'data': json.dumps(pub_obj)}
                    self._hass.services.call('poly_mqtt', 'mqtt_pub_state_change', data_str)

    def update(self):
        self._state = self.is_on
