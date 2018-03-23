import logging
import voluptuous as vol
import time

from homeassistant.components.light import Light, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polynightlight'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

CMD_SET_TIME = [0x80, 0x00, 0xff, 0xff, 0x5, 0x44, 0xff, 0xff, 0x91, 0xff, 0xa2]

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
        pack_list = event.data.get('data')
        if pack_list[0] == '0xa0' and pack_list[5] == '0xf0':
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(True)
                if pack_list[9] == '0x1':
                    dev.set_state(True)
                elif pack_list[9] == '0x0':
                    dev.set_state(False)
        if pack_list[0] == '0xc0' and pack_list[6] == '0x41':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(False)
        if pack_list[0] == '0xa0' and pack_list[5] == '0xf0' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in lights if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()
            if pack_list[9] == '0x1':
                dev.set_state(True)
            elif pack_list[9] == '0x0':
                dev.set_state(False)
        
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

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in lights:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')


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
        self._available = True
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
    def is_on(self):
        """Return true if light is on."""
        return self._state
    
    @property
    def dev_id(self):
        return self._id

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    @property
    def heart_time_stamp(self):
        """heart timestamp"""
        return self._heart_timestamp

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polynightlight'}

    def set_state(self, state):
        self._state = state
        self.schedule_update_ha_state()

    def set_available(self, availible):
        self._available = availible

    def turn_on(self, **kwargs):
        """turn on"""
        self._state = True

    def turn_off(self, **kwargs):
        """turn off."""
        self._state = False

    def set_close_time(self, time):
        mac = self._mac.split('#')
        CMD_SET_TIME[2], CMD_SET_TIME[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_SET_TIME[6], CMD_SET_TIME[7] = int(mac[0], 16), int(mac[1], 16)
        CMD_SET_TIME[9] = time
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_SET_TIME})

    def heart_beat(self):
        self._heart_timestamp = time.time()
        entity_id = 'light.' + self.name
        self._hass.services.call('gateway', 'publish_heart_beat', {'entity_id': entity_id})