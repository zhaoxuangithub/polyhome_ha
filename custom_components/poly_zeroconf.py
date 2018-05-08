"""
This module exposes Home Assistant via Zeroconf.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/zeroconf/
"""
import logging
import socket

import voluptuous as vol

from zeroconf import ServiceBrowser, ServiceStateChange

import polyhome.util.macaddr as uuid_util
from polyhome.helper.const import CUR_VERSION

from homeassistant import util
from homeassistant.const import EVENT_HOMEASSISTANT_STOP

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['api']
DOMAIN = 'poly_zeroconf'

REQUIREMENTS = ['zeroconf==0.19.1']

ZEROCONF_TYPE = '_polyhome._tcp.local.'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({}),
}, extra=vol.ALLOW_EXTRA)


def setup(hass, config):
    """Set up Zeroconf and make Home Assistant discoverable."""
    from zeroconf import Zeroconf, ServiceInfo

    zeroconf = Zeroconf()

    zeroconf_name = '{}.{}'.format(uuid_util.get_mac_address(), ZEROCONF_TYPE)

    dev_uuid = uuid_util.get_uuid(hass.config.config_dir)
    params = {
        'version': CUR_VERSION,
        'uuid': dev_uuid
    }

    host_ip = util.get_local_ip()

    try:
        host_ip_pton = socket.inet_pton(socket.AF_INET, host_ip)
    except socket.error:
        host_ip_pton = socket.inet_pton(socket.AF_INET6, host_ip)

    info = ServiceInfo(ZEROCONF_TYPE, zeroconf_name, host_ip_pton,
                       hass.http.server_port, 0, 0, params)

    zeroconf.register_service(info)

    def stop_zeroconf(event):
        """Stop Zeroconf."""
        zeroconf.unregister_service(info)
        zeroconf.close()

    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, stop_zeroconf)

    # def on_service_state_change(zeroconf, service_type, name, state_change):
    #     info = zeroconf.get_service_info(service_type, name)
    #     if info:
    #         print("Address: %s:%d" % (socket.inet_ntoa(info.address), info.port))
    #         if info.properties:
    #             for key, value in info.properties.items():
    #                 print("%s:  %s" % (key, value))

    # ServiceBrowser(zeroconf, '_polyhome._tcp.local.', handlers=[on_service_state_change])
    
    return True
