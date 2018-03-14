import logging
import json
import voluptuous as vol
import asyncio
import time

from homeassistant.components.media_player import (
    MEDIA_TYPE_MUSIC, MEDIA_TYPE_TVSHOW, MEDIA_TYPE_VIDEO, SUPPORT_NEXT_TRACK,
    SUPPORT_PAUSE, SUPPORT_PLAY_MEDIA, SUPPORT_PREVIOUS_TRACK,
    SUPPORT_TURN_OFF, SUPPORT_TURN_ON, SUPPORT_VOLUME_MUTE, SUPPORT_VOLUME_SET,
    SUPPORT_SELECT_SOURCE, SUPPORT_CLEAR_PLAYLIST, SUPPORT_PLAY,
    SUPPORT_SHUFFLE_SET, MediaPlayerDevice)
from homeassistant.const import (
    CONF_NAME, CONF_HOST, CONF_PORT, STATE_OFF, STATE_ON,
    EVENT_HOMEASSISTANT_STOP)
from homeassistant.const import STATE_OFF, STATE_PAUSED, STATE_PLAYING
import homeassistant.helpers.config_validation as cv

MUSIC_PLAYER_SUPPORT = \
    SUPPORT_PAUSE | SUPPORT_VOLUME_SET | SUPPORT_VOLUME_MUTE | \
    SUPPORT_TURN_ON | SUPPORT_TURN_OFF | SUPPORT_SELECT_SOURCE | \
    SUPPORT_PLAY | SUPPORT_NEXT_TRACK | SUPPORT_PREVIOUS_TRACK

SOURCES = {0: 'AUX1',
           1: 'FM',
           2: 'MP3',
           4: 'BLE'}

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polyyodari3'
POLY_MQTT_DOMAIN = 'poly_mqtt_json'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
ENENT_ZIGBEE_RECV = 'zigbee_data_event'

# 0x80,0x0,0x9,0x7f,0xa,0x44,0x9,0x7f,0x63,0xb9,0x0,0x3,0x0,0x3,0x14
CMD_OPEN  = [0x80, 0x00, 0x9, 0x7f, 0xa, 0x44, 0x9, 0x7f, 0x63, 0xb9, 0x0, 0x3, 0x0, 0x3, 0x14]
CMD_CLOSE = [0x80, 0x00, 0x9, 0x7f, 0xa, 0x44, 0x9, 0x7f, 0x63, 0xb9, 0x0, 0x4, 0x0, 0x4, 0x14]
# 0x80,0x0,0x9,0x7f,0xa,0x44,0x9,0x7f,0x63,0xa3,0x0,0x2,0x0,0x2,0xe
CMD_PLAY = [0x80, 0x00, 0x9, 0x7f, 0xa, 0x44, 0x9, 0x7f, 0x63, 0xa3, 0x0, 0x2, 0x0, 0x2, 0x14]
CMD_STOP = [0x80, 0x00, 0x9, 0x7f, 0xa, 0x44, 0x9, 0x7f, 0x63, 0xa3, 0x0, 0x2, 0x0, 0x2, 0x14]

CMD_NEXT = [0x80, 0x00, 0x9, 0x7f, 0xa, 0x44, 0x9, 0x7f, 0x63, 0xa3, 0x0, 0x5, 0x0, 0x5, 0x14]
CMD_UP = [0x80, 0x00, 0x9, 0x7f, 0xa, 0x44, 0x9, 0x7f, 0x63, 0xa3, 0x0, 0x9, 0x0, 0x9, 0x14]

# 0 - 31
CMD_VOL_SET = [0x80, 0x00, 0x9, 0x7f, 0xa, 0x44, 0x9, 0x7f, 0x63, 0xb9, 0x0, 0x7, 0x5, 0x2, 0xe]

CMD_MUTE = [0x80, 0x00, 0x9, 0x7f, 0xa, 0x44, 0x9, 0x7f, 0x63, 0xa3, 0x0, 0x4, 0x0, 0x4, 0x14]
CMD_SOURCE = [0x80, 0x00, 0x9, 0x7f, 0xa, 0x44, 0x9, 0x7f, 0x63, 0xb9, 0x0, 0x5, 0x0, 0x5, 0x14]

# Validation of the user's configuration
# PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
#     vol.Optional('name'): cv.string,
# })


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome Socket platform."""

    sockets = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'], 'mac': discovery_info['mac']}
        sockets.append(Yodar(hass, device, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'], 'mac': mac}
            sockets.append(Yodar(hass, device, device_config))

    add_devices(sockets, True)
    
    def event_zigbee_msg_handle(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
        
        if pack_list[0] == '0xa0' and pack_list[5] == '0x55' and pack_list[8] == '0x74':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in sockets if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            """local trigger"""
            if pack_list[-4] == '0x2':
                if pack_list[-3] == '0x1':
                    dev.set_player_state(STATE_PAUSED)
                elif pack_list[-3] == '0x0':
                    dev.set_player_state(STATE_PLAYING)
            if pack_list[-3] == '0x80' and pack_list[-4] == '0x4':
                dev.set_player_state(STATE_OFF)
            if pack_list[-3] == '0x80' and pack_list[-4] == '0x3':
                dev.set_player_state(STATE_ON)
            if pack_list[-3] == '0x1' and pack_list[-4] == '0x4':
                dev.set_volume_muted(True)
            if pack_list[-3] == '0x0' and pack_list[-4] == '0x4':
                dev.set_volume_muted(False)
            if pack_list[-4] == '0x7':
                device_vol = int(pack_list[-3].replace('0x',  ''), 16) - 0x80
                dev.update_volume_level(device_vol)
        if pack_list[0] == '0xc0':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in sockets if dev.mac == mac_str), None)
            if dev is None:
                return
            if pack_list[6] == '0x41':
                dev.set_available(False)
            if pack_list[6] == '0x40':
                dev.set_available(True)
        if pack_list[0] == '0xa0' and pack_list[5] == '0x10' and pack_list[8] == '0xcc':
            mac_l, mac_h = pack_list[2].replace('0x', ''), pack_list[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in sockets if dev.mac == mac_str), None)
            if dev is None:
                return
            dev.set_available(True)
            dev.heart_beat()

    hass.bus.listen(ENENT_ZIGBEE_RECV, event_zigbee_msg_handle)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in sockets:
            if round(now - device.heart_time_stamp) > 60 * 30:
                device.set_available(False)
        hass.loop.call_later(60, handle_time_changed_event, '')
        
    hass.loop.call_later(60, handle_time_changed_event, '')


class Yodar(MediaPlayerDevice):
    """Entity reading values from Anthem AVR protocol."""

    def __init__(self, hass, device, config):
        """Initialize entity with transport."""
        super().__init__()
        self._hass = hass
        self._device = device
        self._name = device['name']
        self._mac = device['mac']
        self._config = config
        self._available = True
        self._player_state = STATE_OFF
        self._volume_level = 1.0
        self._volume_muted = False
        self._source_list = list(SOURCES.values())
        self._heart_timestamp = time.time()

    def _lookup(self, propname, dval=None):
        return getattr(self.avr.protocol, propname, dval)

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return MUSIC_PLAYER_SUPPORT

    @property
    def should_poll(self):
        """No polling needed."""
        return False
    
    @property
    def mac(self):
        """mac node"""
        return self._mac

    @property
    def is_on(self):
        """return current state"""
        return self._player_state

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available
    
    @property
    def name(self):
        """Return name of device."""
        return self._name

    @property
    def state(self):
        """Return state of power on/off."""
        return self._player_state

    @property
    def dump_avrdata(self):
        """Return state of avr object for debugging forensics."""
        attrs = vars(self)
        return('dump_avrdata: ' + ', '.join('%s: %s' % item for item in attrs.items()))

    @property
    def volume_level(self):
        """Return the volume level of the media player (0..1)."""
        return self._volume_level

    @property
    def is_volume_muted(self):
        """Return boolean if volume is currently muted."""
        return self._volume_muted

    @property
    def source_list(self):
        """Return the source list."""
        return self._source_list

    @property
    def heart_time_stamp(self):
        return self._heart_timestamp

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {'platform': 'polyyodar_i3'}

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()
    
    def set_player_state(self, state):
        self._player_state = state
        self.schedule_update_ha_state()
    
    def set_volume_muted(self, muted):
        self._volume_muted = muted

    def update_volume_level(self, vol_level):
        self._volume_level = round((vol_level * (100 / 31)) / 100, 2)
        self.schedule_update_ha_state()

    def turn_on(self):
        """turn on"""
        mac = self._mac.split('#')
        CMD_OPEN[2], CMD_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OPEN})
        self._player_state = STATE_ON
        self.schedule_update_ha_state()
        self._player_state = STATE_PLAYING
        self.schedule_update_ha_state()

    def turn_off(self):
        """turn off"""
        mac = self._mac.split('#')
        CMD_CLOSE[2], CMD_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_CLOSE[6], CMD_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_CLOSE})
        self._player_state = STATE_OFF
        self.schedule_update_ha_state()

    def mute_volume(self, mute):
        """Mute the volume."""
        mac = self._mac.split('#')
        CMD_MUTE[2], CMD_MUTE[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_MUTE[6], CMD_MUTE[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_MUTE})
        self._volume_muted = mute
        self.schedule_update_ha_state()

    def set_volume_level(self, volume):
        """Set the volume level, range 0..1."""
        if volume < 0: 
            return
        vol_real = int(volume * 100 * (31 / 100))
        mac = self._mac.split('#')
        CMD_VOL_SET[2], CMD_VOL_SET[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_VOL_SET[6], CMD_VOL_SET[7] = int(mac[0], 16), int(mac[1], 16)
        CMD_VOL_SET[-3] = vol_real
        CMD_VOL_SET[-2] = self.check_sum(CMD_VOL_SET[10:13])
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_VOL_SET})
        self._volume_level = volume
        self.schedule_update_ha_state()

    def media_play(self):
        """Send play command."""
        mac = self._mac.split('#')
        CMD_PLAY[2], CMD_PLAY[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_PLAY[6], CMD_PLAY[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_PLAY})
        self._player_state = STATE_PLAYING
        self.schedule_update_ha_state()

    def media_pause(self):
        """Send pause command."""
        mac = self._mac.split('#')
        CMD_STOP[2], CMD_STOP[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_STOP[6], CMD_STOP[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_STOP})
        self._player_state = STATE_PAUSED
        self.schedule_update_ha_state()

    def media_previous_track(self):
        """previous song"""
        mac = self._mac.split('#')
        CMD_UP[2], CMD_UP[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_UP[6], CMD_UP[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_UP})

    def media_next_track(self):
        """next song"""
        mac = self._mac.split('#')
        CMD_NEXT[2], CMD_NEXT[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_NEXT[6], CMD_NEXT[7] = int(mac[0], 16), int(mac[1], 16)
        self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_NEXT})

    def select_source(self, source):
        """Set the input source."""
        mac = self._mac.split('#')
        CMD_SOURCE[2], CMD_SOURCE[3] = int(mac[0], 16), int(mac[1], 16)
        CMD_SOURCE[6], CMD_SOURCE[7] = int(mac[0], 16), int(mac[1], 16)
        for key, value in SOURCES.items():
            if source == value:
                if key == 0: # AUX1
                    CMD_SOURCE[-3] = 0x0
                    CMD_SOURCE[-2] = 0x5
                    self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_SOURCE})
                if key == 1: # SD
                    CMD_SOURCE[-3] = 0x1
                    CMD_SOURCE[-2] = 0x4
                    self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_SOURCE})
                if key == 2: # FM
                    CMD_SOURCE[-3] = 0x2
                    CMD_SOURCE[-2] = 0x7
                    self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_SOURCE})
                if key == 4: # BLE
                    CMD_SOURCE[-3] = 0x4
                    CMD_SOURCE[-2] = 0x1
                    self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_SOURCE})
                
    def check_sum(self, data):
        result = 0
        for value in data:
            result ^= value
        return result

    def heart_beat(self):
        self._heart_timestamp = time.time()