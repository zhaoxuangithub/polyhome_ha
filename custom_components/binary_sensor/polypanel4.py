import logging
import json
import voluptuous as vol
import time

# Import the device class from the component that you want to support
from homeassistant.components.switch import SwitchDevice, PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

from polyhome import JSONEncoder

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polypanel4'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome Light platform."""

    panels = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        panels.append(PolyPanel(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            panels.append(PolyPanel(hass, device, device_config))

    add_devices(panels, True)

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
        if pack_list[0] == '0xa0' and pack_list[5] == '0x43':
            mac_l, mac_h = pack_list[6].replace('0x',''), pack_list[7].replace('0x','')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in panels if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(True)
                if pack_list[9] == '0x1':
                    dev.trigger('3')
                if pack_list[9] == '0x2':
                    dev.trigger('4')
                if pack_list[9] == '0x6':
                    dev.trigger('2')
                if pack_list[9] == '0x7':
                    dev.trigger('1')
        if pack_list[0] == '0xa0' and pack_list[5] == '0x43' and pack_list[8] == '0x78':
            # '0xa0', '0xc1', '0x4', '0xa0', '0x13', '0x43', '0x4', '0xa0', '0x78', '0x0', '0x0', '0x0', \
            # '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x6', '0x9e', '0xd1'
            mac_l, mac_h = pack_list[6].replace('0x',''), pack_list[7].replace('0x','')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in panels if dev.mac == mac_str), None)
            if dev is not None:
                dev.heart_beat()
                dev.set_available(True)           
                               
    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in panels:
            # print(device.entity_id)
            # print(round(now - device.heart_time_stamp))
            if round(now - device.heart_time_stamp) > 60 * 40:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')


class PolyPanel(Entity):
    """Representation of an Polyhome SencePanel4."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an PolySocket."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._keys = ['1', '2', '3', '4']
        self._available = True
        self._heart_timestamp = time.time()

    @property
    def name(self):
        return self._name

    @property
    def mac(self):
        return self._mac

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    @property
    def heart_time_stamp(self):
        """heart beat time stamp"""
        return self._heart_timestamp
    
    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

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

    def heart_beat(self):
        self._heart_timestamp = time.time()