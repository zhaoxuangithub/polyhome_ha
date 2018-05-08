import logging
import json
import voluptuous as vol
import asyncio
import time
import socket
import select
import threading
import re
import types
import homeassistant.util.dt as dt_util
from homeassistant.helpers.event import track_utc_time_change

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

SOURCES = {0: 'AUX',
           1: 'FM',
           2: '本地',
           3: '云音乐'}

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polybackaudio'
DISCOVERY_PORT = 18090

# E7: recvId: BA520000DPCC7O6DUQTJ
CMD_SEARCH_HOST = {
    "arg": {
        "version": "1.0.3"
    },
    "cmd": "SearchHost",
    "direction": "request",
    "recvId": "FFFFFFFFFFFFFFFFFFFF",
    "sendId": "BAC1EC00112233445566"
}

CMD_GET_HOST_ROOM_LIST = {
    "arg": {
        "hostId": "BA520000DPCC7O6DUQTJ"
    },
    "cmd": "GetHostRoomList",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BAC1EC00112233445566"
}

CMD_OPEN  = {
    "arg": {
        "devStat": "open"
    },
    "cmd": "SetDevStat",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_CLOSE = {
    "arg": {
        "devStat": "close"
    },
    "cmd": "SetDevStat",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_MUTE_MUTE = {
    "arg": {
        "muteStat": "mute"
    },
    "cmd": "SetMute",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_SET_VOLUME = {
    "arg": {
        "volume": "20"
    },
    "cmd": "SetVolume",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_PLAY_PAUSE = {
    "arg": {
        "playCmd": "pause"
    },
    "cmd": "PlayCmd",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_PLAY_RESUME = {
    "arg": {
        "playCmd": "resume"
    },
    "cmd": "PlayCmd",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_PLAY_NEXT = {
    "arg": {
        "playCmd": "next"
    },
    "cmd": "PlayCmd",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_PLAY_PREV = {
    "arg": {
        "playCmd": "prev"
    },
    "cmd": "PlayCmd",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_SWITCH_TO_AUX = {
    "arg": {
        "auxId": "0"
    },
    "cmd": "SwitchToAux",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_SWITCH_TO_FM = {
    "arg": {
        "fmId": "0"
    },
    "cmd": "SwitchToFm",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_PLAY_LOCAL_MUSIC = {
    "arg": {
        "media": {
            "albumId": "",
            "albumMid": "",
            "albumName": "",
            "mediaSrc": "localMusic",
            "singer": [{
                "id": "",
                "mid": "",
                "name": ""
            }],
            "songId": "",
            "songMid": "L3N0b3JhZ2Uvc2RjYXJkMS/mnY7lnKPmnbAgLSDkvaDpgqPkuYjniLHlpbkubXAz\n",
            "songName": "你那么爱她"
        }
    },
    "cmd": "PlayLocalMusic",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_CHANGE_SOURCE = {
    "arg": {
        "audioSource": "localMusic",
        "id": 1
    },
    "cmd": "SetAudioSource",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_MEDIA_PLAYLIST = {
    "arg": {
        "pageNum": 0,
        "pageSize": 50
    },
    "cmd": "GetCurrentPlayList",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_ROOM_CURRENT_STATE = {
    "arg": {
    },
    "cmd": "GetRoomStatInfo",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_DEVICE_STATE = {
    "arg": {
    },
    "cmd": "GetDevStat",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_CURRENT_PLAY_STATE = {
    "arg": {
    },
    "cmd": "GetPlayStat",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_GET_PLAYING_INFO = {
    "arg": {
    },
    "cmd": "GetPlayingInfo",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_SET_PLAYING_TIME = {
    "arg": {
        "playTime": 0
    },
    "cmd": "SetPlayTime",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}

CMD_GET_PLAYING_TIME = {
    "arg": {
    },
    "cmd": "GetPlayTime",
    "direction": "request",
    "recvId": "BA520000DPCC7O6DUQTJ",
    "sendId": "BA76EC00112233445566"
}


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome Socket platform."""

    media_players = []
    if discovery_info is not None:
        print(discovery_info)
        media_players.append(BackAudio(hass, discovery_info['ip'], 20090, discovery_info['devicename'], discovery_info['device_type'], discovery_info['device_id']))

    def event_tcp_backaudio_recv_handle(call):
        addr = call.data.get('addr')
        json_data = call.data.get('json_data')
        if json_data['cmd'] == 'NotifyDevStat':
            # {'sendId': 'BA520000DPCC7O6DUQTJ', 'arg': {'devStat': 'close'}, 'cmd': 'NotifyDevStat', 'recvId': 'FFFFFFFFFF', 'direction': 'request'}
            for player in media_players:
                if player.device_id == json_data['sendId']:
                    if json_data['arg']['devStat'] == 'open':
                        player.set_state(STATE_ON)
                    else:
                        player.set_state(STATE_OFF)
        if json_data['cmd'] == 'GetPlayStat' or json_data['cmd'] == 'NotifyPlayStat' and json_data['direction'] == 'request':
            for player in media_players:
                if player.device_id == json_data['sendId']:
                    if json_data['arg']['playStat'] == 'resume':
                        player.set_state(STATE_PLAYING)
                    elif json_data['arg']['playStat'] == 'pause':
                        player.set_state(STATE_PAUSED)
                    elif json_data['arg']['playStat'] == 'playing':
                        player.set_state(STATE_PLAYING)
        if json_data['cmd'] == 'NotifyPlayingInfo' and json_data['direction'] == 'request':
            for player in media_players:
                if player.device_id == json_data['sendId']:
                    print('当前歌曲:'+ str(json_data))
                    player.set_media_title(json_data['arg']['media']['songName'])
                    player.set_media_artist(json_data['arg']['media']['singer'][0]['name'])
                    player.set_media_album_name(json_data['arg']['media']['albumName'])
                    # player.set_media_image_url(json_data['arg']['media']['picUrl'])
        if json_data['cmd'] == 'NotifyPlayingMediaDuration' and json_data['direction'] == 'request':
            for player in media_players:
                if player.device_id == json_data['sendId']:
                    duration = json_data['arg']['duration']
                    print('下一首duration:'+ str(duration))
                    player.set_media_duration(duration)
        if json_data['cmd'] == 'NotifyPlayTime' and json_data['direction'] == 'request':
            for player in media_players:
                if player.device_id == json_data['sendId']:
                    playTime = json_data['arg']['playTime']
                    print('playTime:'+ str(playTime))
                    player.set_playing_time(playTime)
                    
    hass.bus.listen('event_tcp_backaudio_recv', event_tcp_backaudio_recv_handle)

    add_devices(media_players, True)

    for player in media_players:
        player.get_device_state()

    return True


class BackAudio(MediaPlayerDevice):
    """Entity reading values from Anthem AVR protocol."""

    def __init__(self, hass, ip, port, name, type, device_id):
        """Initialize entity with transport."""
        super().__init__()
        
        self._hass = hass
        self._device_id = device_id
        self._ip = ip
        self._port = port
        self._name = name
        self._device_id = device_id
        self._type = type
        self._available = True
        self._player_state = STATE_OFF
        self._volume_level = 1.0
        self._volume_muted = False
        self._cur_track = 0
        self._media_playlist = None
        self._source = None
        self._media_album_name = None
        self._media_artist = None
        self._media_title = None
        self._media_image_url = None
        self._tracks = []
        self._duration = 0
        self._progress = 0
        self._progress_updated_at = dt_util.utcnow()
        self._playTime = None
        self._source_list = list(SOURCES.values())

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return MUSIC_PLAYER_SUPPORT

    @property
    def should_poll(self):
        """No polling needed."""
        return False
    
    @property
    def device_id(self):
        """mac node"""
        return self._device_id

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
    def media_duration(self):
        """Return the duration of current playing media in seconds."""
        return self._duration

    def set_media_duration(self, duration):
        self._duration = duration
        self.schedule_update_ha_state()

    # @property
    # def media_image_url(self):
    #     return 'https://graph.facebook.com/v2.5/107771475912710/' \
    #         'picture?type=large'

    @property
    def media_position(self):
        """Position of current playing media in seconds."""
        if self._progress is None:
            return None
        return self._progress

    @property
    def media_position_updated_at(self):
        """When was the position of the current playing media valid.

        Returns value from homeassistant.util.dt.utcnow().
        """
        if self._player_state == STATE_PLAYING:
            return self._progress_updated_at

    def set_playing_time(self, playtime):
        self._progress = playtime
        self.schedule_update_ha_state()
    
    def get_playing_time(self):
        """Return the playTime of current playing media in seconds."""
        data = self._send_cmd(CMD_GET_PLAYING_TIME)
        data_l = str(data[4:], 'utf-8')
        data_d = json.loads(data_l)
        self._progress = data_d['arg']['playTime']

    def set_media_image_url(self, media_image_url):
        self._media_image_url = media_image_url
        self.schedule_update_ha_state()

    @property
    def media_title(self):
        return self._media_title

    def set_media_title(self, media_title):
        self._media_title = media_title
        self.schedule_update_ha_state()

    @property
    def media_artist(self):
        return self._media_artist
    
    def set_media_artist(self, media_artist):
        self._media_artist = media_artist
        print(self._media_artist)
        self.schedule_update_ha_state()
        
    @property
    def media_album_name(self):
        """Return the album of current playing media (Music track only)."""
        return self._media_album_name
    
    def set_media_album_name(self, media_album_name):
        """Return the album of current playing media (Music track only)."""
        self._media_album_name = media_album_name
        print(self._media_album_name)
        return self._media_album_name

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
    def source(self):
        """Name of the current input source."""
        return self._source

    @property
    def media_playlist(self):
        """Return the media_playlist."""
        return self._media_playlist
    
    def set_media_playlist(self):
        
        data= self._send_cmd(CMD_MEDIA_PLAYLIST)
        data_l = str(data[4:], 'utf-8')
        self._media_playlist = data_l
        data_d = json.loads(data_l)
        mediaList = data_d['arg']['mediaList']
        for media in mediaList:
            media_single = []
            media_single.append(media['albumName'])
            media_single.append(media['songName'])
            media_single.append(media['singer'][0]['name'])
            media_single.append(media['songMid'])
            self._tracks.append(tuple(media_single))
        print(str(self._tracks))
        self.play_local_music()

    @property
    def device_state_attributes(self):
        return {'platform': 'polybackaudio'}

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def set_state(self, state):
        self._player_state = state
        self.schedule_update_ha_state()

    def get_current_play_state(self):
        data = self._send_cmd(CMD_CURRENT_PLAY_STATE)
        data_l = str(data[4:], 'utf-8')
        print('获取当前播放状态:' + str(data))
        data_d = json.loads(data_l)
        if data_d['arg']['playStat'] == 'resume':
            self.set_state(STATE_PLAYING)
        elif data_d['arg']['playStat'] == 'pause':
            self.set_state(STATE_PAUSED)
        elif data_d['arg']['playStat'] == 'playing':
            self.set_state(STATE_PLAYING)
        self.get_playing_info()

    def get_playing_info(self):
        data = self._send_cmd(CMD_GET_PLAYING_INFO)
        data_l = str(data[4:], 'utf-8')
        print('获取当前歌曲:' + str(data))
        data_d = json.loads(data_l)
        if data_d['arg']['roomStat'] == 'inClosed':
            self.set_state(STATE_OFF)
        else:
            self.set_media_duration(data_d['arg']['media']['duration'])
            self.set_media_title(data_d['arg']['media']['songName'])
            self.set_media_artist(data_d['arg']['media']['singer'][0]['name'])
            
        self.schedule_update_ha_state()

    def get_room_current_state(self):
        self._send_cmd(CMD_ROOM_CURRENT_STATE)
        self.schedule_update_ha_state()

    def set_volume_muted(self, muted):
        if muted:
            CMD_MUTE_MUTE['arg']['muteStat'] = 'mute'
            self._send_cmd(CMD_MUTE_MUTE)
            print('静音')
        else:
            CMD_MUTE_MUTE['arg']['muteStat'] = 'normal'
            self._send_cmd(CMD_MUTE_MUTE)
            print('音量正常')
        self._volume_muted = muted
        self.schedule_update_ha_state()

    def update_volume_level(self, vol_level):
        self._volume_level = round((vol_level * (100 / 31)) / 100, 2)
        self.schedule_update_ha_state()

    def get_device_state(self):
        data = self._send_cmd(CMD_DEVICE_STATE)
        data_l = str(data[4:], 'utf-8')
        print('获取设备开关机状态:' + str(data))
        data_d = json.loads(data_l)
        if data_d['sendId'] == self.device_id:
            if data_d['arg']['resultCode'] == 0:
                if data_d['arg']['devStat'] == 'open':
                    self.get_current_play_state()
                else:
                    self.set_state(STATE_OFF)

    def turn_on(self):
        """turn on"""
        self._send_cmd(CMD_OPEN)
        self._player_state = STATE_PLAYING
        self.schedule_update_ha_state()

    def turn_off(self):
        """turn off"""
        self._send_cmd(CMD_CLOSE)
        self._player_state = STATE_OFF
        self.schedule_update_ha_state()

    def mute_volume(self, mute):
        """Mute the volume."""
        self._volume_muted = mute
        self.set_volume_muted(mute)
        self.schedule_update_ha_state()

    def set_volume_level(self, volume):
        """Set the volume level, range 0..1."""
        if volume < 0: 
            return
        vol_real = int(volume * 100 * (31 / 100))
        self._volume_level = volume
        CMD_SET_VOLUME['arg']['volume'] = str(vol_real)
        self._send_cmd(CMD_SET_VOLUME)
        self.schedule_update_ha_state()

    def media_play(self):
        """Send play command."""
        print('play')
        self._send_cmd(CMD_PLAY_RESUME)
        self._player_state = STATE_PLAYING
        self._progress = self.media_position
        self._progress_updated_at = dt_util.utcnow()
        self.schedule_update_ha_state()
    
    def media_pause(self):
        """Send pause command."""
        print('paused')
        self._send_cmd(CMD_PLAY_PAUSE)
        self._player_state = STATE_PAUSED
        self._progress = self.media_position
        self._progress_updated_at = dt_util.utcnow()
        self.schedule_update_ha_state()
    def media_previous_track(self):
        """previous song"""
        print('media_previous_track')
        self._send_cmd(CMD_PLAY_PREV)
        self._progress = 0
        self._progress_updated_at = dt_util.utcnow()
        self.schedule_update_ha_state()

    def media_next_track(self):
        """next song"""
        print('media_next_track')
        self._send_cmd(CMD_PLAY_NEXT)
        self._progress = 0
        self._progress_updated_at = dt_util.utcnow()
        self.schedule_update_ha_state()

    def select_source(self, source):
        """Set the input source."""
        for key, value in SOURCES.items():
            if source == value:
                if key == 0: # AUX 模块不支持 9 
                    print('AUX')
                    self._send_cmd(CMD_SWITCH_TO_AUX)
                if key == 1: # FM  模块不支持 9 
                    print('FM')
                    self._send_cmd(CMD_SWITCH_TO_FM)
                if key == 2: # 本地
                    print('LOCAL')
                    CMD_CHANGE_SOURCE['arg']['audioSource'] = 'localMusic'
                    self._send_cmd(CMD_CHANGE_SOURCE)
                    self._source = '本地'
                    self.schedule_update_ha_state()
                if key == 3: # 云音乐
                    print('云音乐')
                    CMD_CHANGE_SOURCE['arg']['audioSource'] = 'cloudMusic'
                    self._send_cmd(CMD_CHANGE_SOURCE)
                    self._source = '云音乐'
                    self.schedule_update_ha_state()

    def play_local_music(self):
        """播放本地音乐"""
        print('正在播放:' + self._tracks[0][1])
        CMD_PLAY_LOCAL_MUSIC['arg']['media']['songMid'] = self._tracks[0][3]
        CMD_PLAY_LOCAL_MUSIC['arg']['media']['songName'] = self._tracks[0][1]
        self._send_cmd(CMD_PLAY_LOCAL_MUSIC)
        self.schedule_update_ha_state()
        
    def _send_cmd(self, data):
        """send control json data"""
        _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _socket.connect((self._ip, self._port))
        str_data = json.dumps(data).replace(' ', '')
        len_cmd = len(str_data)
        msg = len_cmd.to_bytes(4, byteorder='little')
        msg += str_data.encode('utf-8')
        _socket.send(msg)
        _socket.settimeout(2)
        try:
            time.sleep(1)
            buf = _socket.recv(10240)
        except socket.timeout:
            buf = None
        finally:
            _socket.close()
        return buf