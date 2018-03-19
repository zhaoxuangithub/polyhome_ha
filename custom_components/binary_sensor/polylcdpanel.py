import logging
import json
import voluptuous as vol
import time

from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polylcdpanel'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'

SENCE_NAME_CMD = [0x80, 0x00, 0x00, 0x2F, 0x0D, 0x44, 0x00, 0x2F, 0x69, 0x00, \
                    0xA1, 0xA1, 0xA1, 0xA1, 0xA1, 0xA1, 0xA1, 0xA1, 0xFF]


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome LCD platform."""

    panels = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        panels.append(PolyLcdPanel(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            panels.append(PolyLcdPanel(hass, device, device_config))

    add_devices(panels, True)

    def event_zigbee_recv_handler(event):
        """Listener to handle fired events"""
        # '0xa0', '0xba', '0x51', '0x47', '0x5', '0xf3', '0x51', '0x47', '0x79', '0x0', '0x95'
        pack_list = event.data.get('data')
        if pack_list[0] == '0xa0' and pack_list[5] == '0xf3':
            mac_l, mac_h = pack_list[6].replace('0x',''), pack_list[7].replace('0x','')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in panels if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(True)
                triger_key = pack_list[9].replace('0x', '')
                triger_key = str(int(triger_key, 16))
                dev.trigger(triger_key)
        if pack_list[0] == '0xa0' and pack_list[5] == '0xf3' and pack_list[8] == '0xcc':
            mac_l, mac_h = pack_list[6].replace('0x',''), pack_list[7].replace('0x','')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in panels if dev.mac == mac_str), None)
            if dev is not None:
                dev.set_available(True)
                dev.heart_beat()
        if pack_list[0] == '0xa0' and pack_list[5] == '0xf3' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in panels if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()

    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_recv_handler)

    def edit_sence_name_service(call):
        # 80 00 00 2F 0D 44 00 2F 69 00 C7 E9 BE B0 D2 BB A1 A1 SUM
        try:
            entity_id = call.data.get('entity_id')
            sence_id = call.data.get('sence_id')
            sence_name = call.data.get('sence_name')
            dev_name = entity_id.replace('binary_sensor.', '')
            dev = next((dev for dev in panels if dev.name == dev_name), None)
            if dev is not None:
                dev.edit_sence_name(sence_id, sence_name)
        except Exception as e:
            pass

    hass.services.register('binary_sensor', 'edit_sence_name', edit_sence_name_service)

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


class PolyLcdPanel(Entity):
    """Representation of an Polyhome SencePanel4."""

    def __init__(self, hass, device, dev_conf):
        """Initialize an PolySocket."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._keys = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12']
        self._available = True
        self._state = True
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
        return self._heart_timestamp

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polylcdpanel'}
    
    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def trigger(self, key_id):
        """trigger one sence"""
        if key_id in self._keys:
            self._hass.bus.fire('binary_sensor.' + self._name  + '_' + key_id + '_pressed')

    def edit_sence_name(self, sence_id, name):
        """edit sence name"""
        try:
            encode_name = name.encode('gbk')
            mac = self._mac.split('#')
            SENCE_NAME_CMD[2], SENCE_NAME_CMD[3] = int(mac[0], 16), int(mac[1], 16)
            SENCE_NAME_CMD[6], SENCE_NAME_CMD[7] = int(mac[0], 16), int(mac[1], 16)
            SENCE_NAME_CMD[9] = int(sence_id)
            for list_no in range(8):
                if list_no < len(encode_name):
                    SENCE_NAME_CMD[10 + list_no] = encode_name[list_no]
                else:
                    SENCE_NAME_CMD[10 + list_no] = 0xA1
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": SENCE_NAME_CMD})
        except UnicodeError as e:
            pass

    def heart_beat(self):
        """update heart beat"""
        self._heart_timestamp = time.time()