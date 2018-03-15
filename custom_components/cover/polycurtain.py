import logging
import time
import voluptuous as vol

from homeassistant.components.cover import (PLATFORM_SCHEMA, CoverDevice,
                                            SUPPORT_OPEN, SUPPORT_CLOSE)
import homeassistant.helpers.config_validation as cv
from homeassistant.core import callback
import polyhome.util.algorithm as checkcrc
from homeassistant.helpers.event import track_utc_time_change

DOMAIN = 'polycurtain'
EVENT_MQTT_RECV = 'poly_mqtt_json'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

BYTES_OPEN = [
    0x80, 0x00, 0x1f, 0xa4, 0x10, 0x44, 0x1f, 0xa4, 0x60, 0x3, 0x0, 0x2, 0x0,
    0x7, 0x0, 0x6, 0x1, 0x5, 0x0, 0x4, 0x0, 0xb4
]
BYTES_CLOSE = [
    0x80, 0x00, 0x1f, 0xa4, 0x10, 0x44, 0x1f, 0xa4, 0x60, 0x3, 0x0, 0x2, 0x0,
    0x7, 0x0, 0x6, 0x0, 0x5, 0x1, 0x4, 0x0, 0xb4
]
BYTES_STOP = [
    0x80, 0x00, 0x1f, 0xa4, 0x10, 0x44, 0x1f, 0xa4, 0x60, 0x3, 0x0, 0x2, 0x0,
    0x7, 0x0, 0x6, 0x0, 0x5, 0x0, 0x4, 0x1, 0xb4
]

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome CoverDevice platform."""

    curtains = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        curtains.append(RMCover(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            curtains.append(RMCover(hass, device, device_config))

    add_devices(curtains, True)

    def handle_event(event):
        """Listener to handle fired events."""
        pack_list = event.data.get('data')
        if pack_list[0] == '0xa0' and pack_list[5] == '0x5':
            mac_1 = pack_list[6].replace('0x', '')
            mac_h = pack_list[7].replace('0x', '')
            mac_str = mac_1 + "#" + mac_h
            dev = next((dev for dev in curtains if dev.mac == mac_str), None)
            if dev is not None:
                # open
                if pack_list[9] == '0x1':
                    dev.set_closed(False)
                # close
                if pack_list[9] == '0x0':
                    dev.set_closed(True)
        # '0xa0', '0xd7', '0x10', '0x26', '0x34', '0x5', '0x10', '0x26', '0xcc', '0x0', '0x0', '0x0', '0x0', \
        # '0x1', '0x1', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0x0', '0xff', '0xff', '0xff', '0xff', '0xff', \
        # '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', \
        # '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', '0xff', \
        # '0xff', '0xff', '0xff', '0xff', '0x75'
        if pack_list[0] == '0xa0' and pack_list[5] == '0x5' and pack_list[8] == '0xcc':
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in curtains if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()
            if pack_list[13] == '0x1' and pack_list[14] == '0x0':
                dev.set_closed(False)
            if pack_list[13] == '0x1' and pack_list[14] == '0x1':
                dev.set_closed(True)
        if pack_list[0] == '0xc0':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in curtains if dev.mac == mac_str), None)
            if dev is None:
                return
            if pack_list[6] == '0x41':
                dev.set_available(False)
            if pack_list[6] == '0x40':
                dev.set_available(True)
        if pack_list[0] == '0xa0' and pack_list[5] == '0x5' and pack_list[8] == '0x77':
            # device status
            mac_l, mac_h = pack_list[6].replace('0x', ''), pack_list[7].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in curtains if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()
            
    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, handle_event)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in curtains:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')

    return True


class RMCover(CoverDevice):
    """Representation of a cover"""

    def __init__(self, hass, device, dev_conf):
        """Initialize the cover."""
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._state = None
        self._closed = True
        self._available = True
        self._heart_timestamp = time.time()

    @property
    def name(self):
        """Return the display name of this curtain."""
        return self._name

    @property
    def mac(self):
        """Return the display mac of this curtain."""
        return self._mac

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    @property
    def is_closed(self):
        """Return if the cover is closed."""
        return self._closed
    
    @property
    def heart_time_stamp(self):
        return self._heart_timestamp

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polycurtain'}

    def set_closed(self, value=True):
        self._closed = value
        self.schedule_update_ha_state()

    def close_cover(self, **kwargs):
        """Close the cover."""
        # 0x80, 0x00, 0x1f, 0xa4, 0x10, 0x44, 0x1f, 0xa4, 0x60, 0x3, 0x0, 0x2, 0x0,
        # 0x7, 0x0, 0x6, 0x0, 0x5, 0x1, 0x4, 0x0, 0xb4
        self._closed = True
        mac = self._mac.split('#')
        BYTES_CLOSE[2], BYTES_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
        BYTES_CLOSE[6], BYTES_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        BYTES_CLOSE[-3] = 0x1
        resu_crc = checkcrc.xorcrc_hex(BYTES_CLOSE)
        BYTES_CLOSE[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {
            "data": BYTES_CLOSE
        })
        time.sleep(0.4)
        BYTES_CLOSE[2], BYTES_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
        BYTES_CLOSE[6], BYTES_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        BYTES_CLOSE[-3] = 0x0
        resu_crc = checkcrc.xorcrc_hex(BYTES_CLOSE)
        BYTES_CLOSE[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {
            "data": BYTES_CLOSE
        })

    def open_cover(self, **kwargs):
        """Open the cover."""
        # 0x80, 0x00, 0x1f, 0xa4, 0x10, 0x44, 0x1f, 0xa4, 0x60, 0x3, 0x0, 0x2, 0x0,
        # 0x7, 0x0, 0x6, 0x1, 0x5, 0x0, 0x4, 0x0, 0xb4
        self._closed = False
        mac = self._mac.split('#')
        BYTES_OPEN[2], BYTES_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        BYTES_OPEN[6], BYTES_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        BYTES_OPEN[-5] = 0x1
        resu_crc = checkcrc.xorcrc_hex(BYTES_OPEN)
        BYTES_OPEN[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": BYTES_OPEN})
        time.sleep(0.4)
        BYTES_OPEN[2], BYTES_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        BYTES_OPEN[6], BYTES_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        BYTES_OPEN[-5] = 0x0
        resu_crc = checkcrc.xorcrc_hex(BYTES_OPEN)
        BYTES_OPEN[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": BYTES_OPEN})

    def stop_cover(self, **kwargs):
        """stop the cover."""
        # 0x80, 0x00, 0x1f, 0xa4, 0x10, 0x44, 0x1f, 0xa4, 0x60, 0x3, 0x0, 0x2, 0x0,
        # 0x7, 0x0, 0x6, 0x0, 0x5, 0x0, 0x4, 0x1, 0xb4
        self._closed = True
        mac = self._mac.split('#')
        BYTES_STOP[2], BYTES_STOP[3] = int(mac[0], 16), int(mac[1], 16)
        BYTES_STOP[6], BYTES_STOP[7] = int(mac[0], 16), int(mac[1], 16)
        BYTES_STOP[-2] = 0x1
        resu_crc = checkcrc.xorcrc_hex(BYTES_STOP)
        BYTES_STOP[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": BYTES_STOP})
        time.sleep(0.4)
        BYTES_STOP[2], BYTES_STOP[3] = int(mac[0], 16), int(mac[1], 16)
        BYTES_STOP[6], BYTES_STOP[7] = int(mac[0], 16), int(mac[1], 16)
        BYTES_STOP[-2] = 0x0
        resu_crc = checkcrc.xorcrc_hex(BYTES_STOP)
        BYTES_STOP[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": BYTES_STOP})

    def heart_beat(self):
        self._heart_timestamp = time.time()
        entity_id = 'cover.' + self.name
        self._hass.services.call('gateway', 'publish_heart_beat', {'entity_id': entity_id})
    
