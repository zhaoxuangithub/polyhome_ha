import logging
import json
import voluptuous as vol
import asyncio
import time
import socket
import select
import threading

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polylocaludp'
DISCOVERY_PORT = 8628


def setup(hass, config):
    """Setup the Polyhome Socket platform."""

    udpserver = UdpServerThread(hass, DISCOVERY_PORT)
    udpserver.start()

    def close_udp_server(call):
        udpserver.stop()

    hass.bus.async_listen_once('homeassistant_stop', close_udp_server)

    def event_gateway_udp_recv_handle(call):
        # addr = call.data.get('addr')
        json_data = call.data.get('data')
        try:
            print(json_data)
            hass.bus.fire(json_data['data'])
        except:
            pass

    hass.bus.listen('event_gateway_udp_recv', event_gateway_udp_recv_handle)

    def fire_system_event_service(call):
        event_id = call.data.get('id')
        udpserver.broadcast_system_event(event_id)

    hass.services.async_register('gateway', 'fire_system_event', fire_system_event_service)

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
                print("Udp Responder socket exception occurred: %s", ex.__str__)
                continue
            
            if recv_data == None:
                continue

            json_data = json.loads(recv_data)
            self._hass.bus.fire('event_gateway_udp_recv', {'sn': addr, 'data': json_data})

    def stop(self):
        """Stop the server."""
        self._interrupted = True
        self.join()

    def broadcast_system_event(self, event_id):
        import polyhome.util.macaddr as uuid_util

        data = {'sn': uuid_util.get_uuid(self._hass.config.config_dir), 'data': 'event_sys_' + str(event_id) + '_fire'}
        str_data = json.dumps(data).replace(' ', '')
        msg = str_data.encode('utf-8')
        self._sock.sendto(msg, ('<broadcast>', self.listen_port))


def clean_socket_close(sock):
    """Close a socket connection and logs its closure."""
    _LOGGER.info("Music Udp shutting down.")

    sock.close()
    