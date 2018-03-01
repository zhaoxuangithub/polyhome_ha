import logging
import voluptuous as vol

# Import the device class from the component that you want to support
from homeassistant.components.light import ATTR_BRIGHTNESS, Light, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
import util.algorithm as checkcrc

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polywalllight'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

BYTES_OPEN = [0x80, 0x00, 0xb4, 0x53, 0x5, 0x44, 0xb4, 0x53, 0x92, 0x1, 0xa2]
BYTES_CLOSE = [0x80, 0x00, 0xb4, 0x53, 0x5, 0x44, 0xb4, 0x53, 0x92, 0x0, 0xa3]

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome Light platform."""

    lights = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        lights.append(PolyLight(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            lights.append(PolyLight(hass, device, device_config))

    add_devices(lights, True)

    def handle_event(event):
        """Listener to handle fired events"""
        bytearr = event.data.get('data')
        if (bytearr[0] == '0xa0') and (bytearr[5] == '0xf1'):
            mac_l, mac_h = bytearr[6].replace('0x', ''), bytearr[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                if bytearr[9] == '0x1':
                    hass.states.set('light.' + dev.name, 'on')
                    hass.services.call("poly_mqtt", "pub_data", {"data": "walllight close"})
                elif bytearr[9] == '0x0':
                    hass.states.set('light.' + dev.name, 'off')
                    hass.services.call("poly_mqtt", "pub_data", {"data": "walllight open"})
        if bytearr[0] == '0xc0' and bytearr[6] == '0x41':
            mac_l, mac_h = bytearr[2].replace('0x', ''), bytearr[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                hass.states.set('light.' + dev.name, 'unavailable')
        
    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, handle_event)


class PolyLight(Light):
    """Representation of an Polyhome Light."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an AwesomeLight."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._state = None

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def mac(self):
        """Return the display mac of this light."""
        return self._mac

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

    def turn_on(self, **kwargs):
        """turn on"""
        mac = self._mac.split('#')
        BYTES_OPEN[2], BYTES_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        BYTES_OPEN[6], BYTES_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        resu_crc = checkcrc.xorcrc_hex(BYTES_OPEN)
        BYTES_OPEN[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": BYTES_OPEN})
        self._state = True

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        mac = self._mac.split('#')
        BYTES_CLOSE[2], BYTES_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
        BYTES_CLOSE[6], BYTES_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        resu_crc = checkcrc.xorcrc_hex(BYTES_CLOSE)
        BYTES_CLOSE[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": BYTES_CLOSE})
        self._state = False

    def update(self):
        self._state = self.is_on