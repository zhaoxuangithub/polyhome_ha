import logging
import asyncio
import voluptuous as vol
import json
import time

import homeassistant.helpers.config_validation as cv
from homeassistant.components.cover import (PLATFORM_SCHEMA, CoverDevice, SUPPORT_OPEN, SUPPORT_CLOSE, SUPPORT_STOP, \
                                            SUPPORT_SET_POSITION)
from homeassistant.const import (STATE_CLOSED, STATE_UNKNOWN, STATE_OPEN)
from homeassistant.helpers.event import track_utc_time_change

import polyhome.util.algorithm as checkcrc

DOMAIN = 'dooya'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

CMD_COVER_OPEN = [0x80, 0x00, 0x14, 0x42, 0xb, 0x44, 0x14, 0x42, 0x63, \
                    0x55, 0xFE, 0xFE, 0x3, 0x1, 0xB9, 0x24, 0x14]
CMD_COVER_CLOSE = [0x80, 0x00, 0x14, 0x42, 0xb, 0x44, 0x14, 0x42, 0x63, \
                    0x55, 0xFE, 0xFE, 0x3, 0x2, 0xF9, 0x25, 0x14]
CMD_COVER_STOP = [0x80, 0x00, 0x14, 0x42, 0xb, 0x44, 0x14, 0x42, 0x63, \
                    0x55, 0xFE, 0xFE, 0x3, 0x3, 0x38, 0xE5, 0x14]
CMD_COVER_POS =  [0x80, 0x00, 0x14, 0x42, 0xc, 0x44, 0x14, 0x42, 0x63, \
                    0x55, 0xfe, 0xfe, 0x3, 0x4, 0x1E, 0x66, 0xEA, 0x31]   
CMD_COVER_R_POS = [0x80, 0x00, 0x14, 0x42, 0xc, 0x44, 0x14, 0x42, 0x63, \
                    0x55, 0xfe, 0xfe, 0x1, 0x2, 0x01, 0x85, 0x42, 0x31]

SUPPORT_FEATURES = SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_SET_POSITION | SUPPORT_STOP

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome CoverDevice platform."""

    curtains = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        curtains.append(DooYaCover(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            curtains.append(DooYaCover(hass, device, device_config, 50))

    add_devices(curtains, True)

    def event_zigbee_msg_handle(event):
        """Listener to handle fired events."""
        pack_list = event.data.get('data')
        if pack_list[0] == '0xa0' and pack_list[8] == '0x74':
            mac_1 = pack_list[6].replace('0x', '')
            mac_h = pack_list[7].replace('0x', '')
            mac_str = mac_1 + "#" + mac_h
            dev = next((dev for dev in curtains if dev.mac == mac_str), None)
            if dev is not None and pack_list[9] == '0x55':
                dev.set_available(True)
                if pack_list[12] == '0x3' and pack_list[13] == '0x1':
                    dev.set_closed(False)
                if pack_list[12] == '0x3' and pack_list[13] == '0x2':
                    dev.set_closed(True)   
        if pack_list[0] == '0xc0':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            for dev in curtains:
                if dev.mac == mac_str:
                    if pack_list[6] == '0x41':
                        dev.set_available(False)
                    if pack_list[6] == '0x40':
                        dev.set_available(True)
        if pack_list[0] == '0xa0' and pack_list[8] == '0xcc':
            """heart beat"""
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in curtains if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()
        if pack_list[0] == '0xa0' and pack_list[5] == '0x1e' and pack_list[8] == '0x77':
            # device status
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
            if not pack_list[22] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[22:27]})
            if not pack_list[27] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[27:32]})
            if not pack_list[32] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[32:37]})
            if not pack_list[37] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[37:42]})
            if not pack_list[42] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[42:47]})
            if not pack_list[47] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[47:52]})
            if not pack_list[52] == '0xff':
                hass.bus.fire('event_zigbee_device_status', {'router': pack_list[2:4], 'device': pack_list[52:57]})
               
    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_msg_handle)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in curtains:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')
    
    return True


class DooYaCover(CoverDevice):
    """Representation of a cover"""

    def __init__(self, hass, device, dev_conf, position=None):
        """Initialize the cover."""
        self._hass = hass
        self._name = device['name']
        self._mac = device['mac']
        self._config = dev_conf
        self._position = position
        self._supported_features = SUPPORT_FEATURES
        self._device_class = 'window'
        self._set_position = None
        self._requested_closing = True
        self._requested_closing_tilt = True
        self._unsub_listener_cover = None
        self._unsub_listener_cover_tilt = None
        self._closed = True
        self._available = True
        self._heart_timestamp = time.time()

    @property
    def mac(self):
        """Return the display mac of this curtain."""
        return self._mac
    
    @property
    def name(self):
        """Return the name of the cover."""
        return self._name

    @property
    def should_poll(self):
        """No polling needed for a demo cover."""
        return False

    @property
    def current_cover_position(self):
        """Return the current position of the cover."""
        return self._position

    @property
    def is_closed(self):
        """Return if the cover is closed."""
        return self._closed

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._device_class

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available

    @property
    def heart_time_stamp(self):
        """heart timestamp"""
        return self._heart_timestamp

    def close_cover(self, **kwargs):
        """Close the cover."""
        if self._position == 0:
            return
        elif self._position is None:
            self._closed = True
            self.schedule_update_ha_state()
            return

        self._listen_cover()
        self._requested_closing = True
        self.schedule_update_ha_state()

        mac = self._mac.split('#')
        CMD_COVER_CLOSE[2], CMD_COVER_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_COVER_CLOSE[6], CMD_COVER_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        resu_crc = checkcrc.xorcrc_hex(CMD_COVER_CLOSE)
        CMD_COVER_CLOSE[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_COVER_CLOSE})

    def open_cover(self, **kwargs):
        """Open the cover."""
        if self._position == 100:
            return
        elif self._position is None:
            self._closed = False
            self.schedule_update_ha_state()
            return

        self._listen_cover()
        self._requested_closing = False
        self.schedule_update_ha_state()

        mac = self._mac.split('#')
        CMD_COVER_OPEN[2], CMD_COVER_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_COVER_OPEN[6], CMD_COVER_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        resu_crc = checkcrc.xorcrc_hex(CMD_COVER_OPEN)
        CMD_COVER_OPEN[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_COVER_OPEN})

    def set_cover_position(self, position, **kwargs):
        """Move the cover to a specific position."""
        if self._position == position:
            return
        self._position = position
        self.schedule_update_ha_state()

        mac = self._mac.split('#')
        CMD_COVER_POS[2], CMD_COVER_POS[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_COVER_POS[6], CMD_COVER_POS[7] = int(mac[0], 16), int(mac[1], 16)
        CMD_COVER_POS[14] = position
        crc16 = checkcrc.calculateCRC(CMD_COVER_POS[9:15])
        crc16_h = eval(hex(crc16)[0:4])
        crc16_l = '0x{}'.format(hex(crc16)[4:6])
        crc16_l = eval(crc16_l)
        CMD_COVER_POS[15] = crc16_l
        CMD_COVER_POS[16] = crc16_h
        resu_crc = checkcrc.xorcrc_hex(CMD_COVER_POS)
        CMD_COVER_POS[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_COVER_POS})
        
    def stop_cover(self, **kwargs):
        """Stop the cover."""
        mac = self._mac.split('#')
        CMD_COVER_STOP[2], CMD_COVER_STOP[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_COVER_STOP[6], CMD_COVER_STOP[7] = int(mac[0], 16), int(mac[1], 16)
        resu_crc = checkcrc.xorcrc_hex(CMD_COVER_STOP)
        CMD_COVER_STOP[-1] = resu_crc
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_COVER_STOP})

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def set_closed(self, state):
        self._closed = state
        self.schedule_update_ha_state()

    def _listen_cover(self):
        """Listen for changes in cover."""
        if self._unsub_listener_cover is None:
            self._unsub_listener_cover = track_utc_time_change(
                self._hass, self._time_changed_cover)

    def _time_changed_cover(self, now):
        """Track time changes."""
        if self._requested_closing:
            self._reset_ui()
            self._closed = True
            self._position = 0
            self.schedule_update_ha_state()
        else:
            self._reset_ui()
            self._closed = False
            self._position = 100
            self.schedule_update_ha_state()

    def _reset_ui(self):
        if self._position is None:
            return
        if self._unsub_listener_cover is not None:
            self._unsub_listener_cover()
            self._unsub_listener_cover = None
            self._set_position = None

    def heart_beat(self):
        self._heart_timestamp = time.time()
        entity_id = 'cover.' + self.name
        self._hass.services.call('gateway', 'publish_heart_beat', {'entity_id': entity_id})