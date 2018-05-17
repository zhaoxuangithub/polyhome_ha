import logging
import json
import voluptuous as vol
import asyncio
import time
import socket
import select
import threading

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
from homeassistant.helpers import discovery

MUSIC_PLAYER_SUPPORT = \
    SUPPORT_PAUSE | SUPPORT_VOLUME_SET | SUPPORT_VOLUME_MUTE | \
    SUPPORT_TURN_ON | SUPPORT_TURN_OFF | SUPPORT_SELECT_SOURCE | \
    SUPPORT_PLAY | SUPPORT_NEXT_TRACK | SUPPORT_PREVIOUS_TRACK

SOURCES = {0: 'AUX',
           1: 'FM'}

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polybackaudio'
DISCOVERY_PORT = 18090
media_players = []

# Search Host
# {"sendId":"BA500000BDIDOH3JP3QJ",
# "arg":{"deviceName":"channelX","devType":"50","resultCode":0,"deviceId":"BA500000BDIDOH3JP3QJ"},
# "cmd":"SearchHost",
# "recvId":"BAC1EC00112233445566",
# "direction":"response"}
CMD_SEARCH_HOST = {
    "arg": {
        "version": "1.0.3"
    },
    "cmd": "SearchHost",
    "direction": "request",
    "recvId": "FFFFFFFFFFFFFFFFFFFF",
    "sendId": "BAC1EC00112233445566"
}


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome Socket platform."""

    udpserver = UdpServerThread(hass, DISCOVERY_PORT)
    udpserver.start()

    def close_udp_server(call):
        udpserver.stop()

    hass.bus.async_listen_once('homeassistant_stop', close_udp_server)

    """addr=('192.168.3.51', 49798),
    {'cmd': 'SearchHost', 'recvId': 'FFFFFFFFFFFFFFFFFFFF', 'direction': 'request', 'arg': {'version': '1.0.3'}, 'sendId': 'BAC1EC00112233445566'}
    {'arg': {'deviceId': 'BAE3040042ae6a2f1c92', 'deviceName': 'BAE3Server', 'deviceType': 'BaServer', 'deviceVersion': '1.6.2.01', 'resultCode': 0}, 'cmd': 'SearchHost', 'direct': 'response', 'recvId': 'BAC1EC00112233445566', 'sendId': 'BAE3040042ae6a2f1c92'}
    """
    def event_tcp_backaudio_recv_handle(call):
        addr = call.data.get('addr')
        json_data = call.data.get('json_data')
        try:
            if json_data['cmd'] == 'SearchHost':
                if json_data['arg']['resultCode'] == 0:
                    ip = addr[0]
                    devicename = json_data['arg']['deviceName']
                    device_id = json_data['arg']['deviceId']
                    device_type = json_data['arg']['deviceType']
                    player = {'ip': ip, 'devicename': devicename, 'device_id': device_id, 'device_type': device_type}
                    if len(media_players) == 0:
                        media_players.append(player)
                        discovery.load_platform(hass, 'media_player', 'polybackaudio_bae3', player)
                    flag = False
                    for device in media_players:
                        if device['device_id'] == player['device_id']:
                            flag =True
                            break
                    if flag is False:
                        media_players.append(player)
                        discovery.load_platform(hass, 'media_player', 'polybackaudio_e7', player)
        except:
            pass

    hass.bus.listen('event_tcp_backaudio_recv', event_tcp_backaudio_recv_handle)

    # device online check
    def handle_time_changed_event(call):
        print('===scan===')
        print(media_players)
        hass.add_job(udpserver.scan)
        hass.loop.call_later(10, handle_time_changed_event, '')
        
    hass.loop.call_later(10, handle_time_changed_event, '')

    udpserver.scan()
    return True


class UdpServerThread(threading.Thread):
    """Handle responding to Udp Command requests."""

    _interrupted = False
    
    def __init__(self, hass, listen_port):
        """Initialize the class."""
        threading.Thread.__init__(self)

        self._hass = hass
        self.listen_port = listen_port
        self._sock = None

    def run(self):
        """Run the server."""
        # Listen for UDP port 18090 packets sent to Udp multicast address
        
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(('', self.listen_port))
        self._sock.setblocking(False)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        cmd_search_host = CMD_SEARCH_HOST
        str_data = json.dumps(cmd_search_host).replace(' ', '')
        len_cmd = len(str_data)
        msg = len_cmd.to_bytes(4, byteorder='little')
        msg += str_data.encode('utf-8')
        # self._sock.sendto(msg, ('<broadcast>', self.listen_port))

        while True:
            if self._interrupted:
                clean_socket_close(self._sock)
                return

            try:
                read, _, _ = select.select(
                    [self._sock], [],
                    [self._sock], 2)

                if self._sock in read:
                    recv_data, addr = self._sock.recvfrom(1024)
                else:
                    # most likely the timeout, so check for interrupt
                    continue
            except socket.error as ex:
                if self._interrupted:
                    clean_socket_close(self._sock)
                    return

                _LOGGER.error("Udp Responder socket exception occurred: %s", ex.__str__)
                # without the following continue, a second exception occurs
                # because the data object has not been initialized
                continue
            
            if recv_data == None:
                continue
            if recv_data == msg:
                continue

            str_data = str(recv_data[4:].decode('utf-8'))
            json_data = json.loads(str_data)
            self._hass.bus.fire('event_tcp_backaudio_recv', {'addr': addr, 'json_data': json_data})

    def stop(self):
        """Stop the server."""
        self._interrupted = True
        self.join()

    def scan(self):
        data = CMD_SEARCH_HOST
        str_data = json.dumps(data).replace(' ', '')
        msg = bytes([len(str_data), 0, 0, 0])
        msg += str_data.encode('utf-8')
        self._sock.sendto(msg, ('<broadcast>', self.listen_port))


def clean_socket_close(sock):
    """Close a socket connection and logs its closure."""
    _LOGGER.info("Music Udp shutting down.")

    sock.close()
    