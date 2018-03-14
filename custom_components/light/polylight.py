import logging
import voluptuous as vol

# Import the device class from the component that you want to support
from homeassistant.components.light import Light, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polylight'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

# 80 00 00 2F 07 44 00 2D 61 00 03 00 A3
CMD_OPEN = [0x80, 0x00, 0xFF, 0xFE, 0x7, 0x44, 0xd, 0x7, 0x61, 0x0, 0x1, 0x1, 0xa2]
CMD_CLOSE = [0x80, 0x00, 0xFF, 0xFE, 0x7, 0x44, 0xd, 0x7, 0x61, 0x0, 0x1, 0x0, 0xa3]

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome Light platform."""

    lights = []
    if discovery_info is not None:
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        lights.append(PolyLight(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            lights.append(PolyLight(hass, device, device_config))

    add_devices(lights, True)

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        bytearr = event.data.get('data')

        if bytearr[0] == '0xa0' and bytearr[8] == '0x73' and bytearr[9] == '0x20':
            """'0xa0', '0xc3', '0x46', '0xb1', '0xa', '0x53', '0x46', '0xb1', 
            '0x73', '0x21', '0xd', '0x7', '0x0', '0x0', '0x0', '0x62'
            """
            mac_l, mac_h = bytearr[10].replace('0x', ''), bytearr[11].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                mac_l, mac_h = bytearr[2].replace('0x', ''), bytearr[3].replace('0x', '')
                mac_str = mac_l + '#' + mac_h
                dev.set_router(mac_str)
                dev.set_available(True)
                if bytearr[-4] == '0x1':
                    dev.set_state(True)
                if bytearr[-4] == '0x0':
                    dev.set_state(False)
        if bytearr[0] == '0xa0' and bytearr[8] == '0x72':
            """ control timeout handle
            0xa0', '0xc7', '0x46', '0xb1', '0x7', '0x53', '0xd', '0x7', '0x72', '0x0', '0x1', '0x1', '0xbc'
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
        if device[2] == '0x20':
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
                    if bin(s_int)[-1] == '1':
                        dev.set_state(True)
                    if bin(s_int)[-1] == '0':
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
        self._config = dev_conf
        self._state = None
        self._router = '2b#2f'
        self._available = True

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
    
    @property
    def available(self):
        """Return if bulb is available."""
        return self._available
    
    @property
    def supported_features(self):
        """Flag Light features that are supported."""
        return 0

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polylight'}

    def set_state(self, state):
        self._state = state
        self.schedule_update_ha_state()

    def set_router(self, router):
        self._router = router

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def turn_on(self, **kwargs):
        """turn on"""
        router_mac = self._router.split('#')
        CMD_OPEN[2], CMD_OPEN[3] = int(router_mac[0], 16), int(router_mac[1], 16)
        mac = self._mac.split('#')
        CMD_OPEN[6], CMD_OPEN[7] = int(mac[0],16), int(mac[1],16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OPEN})
        self._state = True

    def turn_off(self, **kwargs):
        """turn off."""
        router_mac = self._router.split('#')
        CMD_CLOSE[2], CMD_CLOSE[3] = int(router_mac[0], 16), int(router_mac[1], 16)
        mac = self._mac.split('#')
        CMD_CLOSE[6], CMD_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CLOSE})
        self._state = False

    def update(self):
        self._state = self.is_on
