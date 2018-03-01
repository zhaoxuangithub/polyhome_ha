import logging
import voluptuous as vol

# Import the device class from the component that you want to support
from homeassistant.components.light import ATTR_BRIGHTNESS, Light, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
import polyhome.util.algorithm as checkcrc

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polylight2'
EVENT_MQTT_RECV = 'poly_mqtt_json'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

# 0x80,0x0,0xb4,0x53,0x6,0x44,0xb4,0x53,0x60,0x1,0x1,0xa2
BYTES_OPEN = [0x80, 0x00, 0x46, 0xb1, 0x7, 0x44, 0xd, 0x7, 0x61, 0x0, 0x1, 0x1, 0xa2]
BYTES_CLOSE = [0x80, 0x00, 0x46, 0xb1, 0x7, 0x44, 0xd, 0x7, 0x61, 0x0, 0x1, 0x0, 0xa3]

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome Light platform."""

    lights = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'] + '1', 'mac': discovery_info['mac'], 'way': 1}
        lights.append(PolyLight(hass, device, None))
        device = {'name': discovery_info['name'] + '2', 'mac': discovery_info['mac'], 'way': 2}
        lights.append(PolyLight(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'] + '1', 'mac': mac, 'way': 1}
            lights.append(PolyLight(hass, device, device_config))
            device = {'name': device_config['name'] + '2', 'mac': mac, 'way': 2}
            lights.append(PolyLight(hass, device, device_config))

    add_devices(lights, True)

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        bytearr = event.data.get('data')

        if bytearr[0] == '0xa0' and bytearr[8] == '0x73' and bytearr[9] == '0x21':
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

    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)

    def event_zigbee_device_status_handler(event):
        router = event.data.get('router')
        device = event.data.get('device')
        if device[2] == '0x21':
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
                    if dev.way == 1 and bin(s_int)[-1] == '1':
                        dev.set_state(True)
                    if dev.way == 1 and bin(s_int)[-1] == '0':
                        dev.set_state(False)
                    if dev.way == 2 and bin(s_int)[-2] == '1':
                        dev.set_state(True)
                    if dev.way == 2 and bin(s_int)[-2] == '0':
                        dev.set_state(False)
                    
    # Listen Device Status Event
    hass.bus.listen('event_zigbee_device_status', event_zigbee_device_status_handler)


class PolyLight(Light):
    """Representation of an Polyhome Light."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an AwesomeLight."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._way = device['way']
        self._config = dev_conf
        self._state = True
        self._available = True
        self._router = '46#b1'

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
        BYTES_OPEN[2], BYTES_OPEN[3] = int(router_mac[0], 16), int(router_mac[1], 16)
        mac = self._mac.split('#')
        BYTES_OPEN[6], BYTES_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        BYTES_OPEN[-3] = self._way
        resu_crc = checkcrc.xorcrc_hex(BYTES_OPEN)
        BYTES_OPEN[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": BYTES_OPEN})
        self._state = True

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        router_mac = self._router.split('#')
        BYTES_CLOSE[2], BYTES_CLOSE[3] = int(router_mac[0], 16), int(router_mac[1], 16)
        mac = self._mac.split('#')
        BYTES_CLOSE[6], BYTES_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        BYTES_CLOSE[-3] = self._way
        resu_crc = checkcrc.xorcrc_hex(BYTES_CLOSE)
        BYTES_CLOSE[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": BYTES_CLOSE})
        self._state = False

    def update(self):
        self._state = self.is_on
