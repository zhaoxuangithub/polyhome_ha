import logging
import voluptuous as vol

# Import the device class from the component that you want to support
from homeassistant.components.light import ATTR_BRIGHTNESS, Light, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
import custom_components.polyhome.util.algorithm as checkcrc

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polynightlight'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

CMD_SET_TIME = [0x80, 0x00, 0xff, 0xff, 0x5, 0x44, 0xff, 0xff, 0x91, 0xff, 0xa2]

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string,
    vol.Optional('type'): cv.string
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
        if (bytearr[0] == '0xa0') and (bytearr[5] == '0xf0'):
            mac_l, mac_h = bytearr[6].replace('0x', ''), bytearr[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_availible(True)
                if bytearr[9] == '0x1':
                    dev.set_state(True)
                elif bytearr[9] == '0x0':
                    dev.set_state(False)
        if bytearr[0] == '0xc0' and bytearr[6] == '0x41':
            mac_l, mac_h = bytearr[2].replace('0x', ''), bytearr[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_availible(False)

    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)

    def set_close_time_service(call):
        entity_id = call.data.get('entity_id')
        time = call.data.get('time')
        dev = next((dev for dev in lights if dev.dev_id == entity_id), None)
        if dev is not None:
            t_close = int(time)
            if t_close < 0 or t_close > 255:
                return 
            dev.set_close_time(t_close)

    hass.services.register('light', 'set_close_time', set_close_time_service)


class PolyLight(Light):
    """Representation of an Polyhome Light."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an AwesomeLight."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._id = 'light.' + self._name
        self._config = dev_conf
        self._state = None
        self._availible = None

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
    def dev_id(self):
        return self._id

    def set_state(self, state):
        self._state = state
        self.schedule_update_ha_state()

    def set_availible(self, availible):
        self._availible = True

    def set_close_time(self, time):
        mac = self._mac.split('#')
        CMD_SET_TIME[2], CMD_SET_TIME[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_SET_TIME[6], CMD_SET_TIME[7] = int(mac[0], 16), int(mac[1], 16)
        CMD_SET_TIME[9] = time
        resu_crc = checkcrc.xorcrc_hex(CMD_SET_TIME)
        CMD_SET_TIME[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_SET_TIME})