#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
import asyncio

import polyhome.util.algorithm as checkcrc

from polyhome.helper.const import (
    POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE,
    DEFAULT_UARTPATH, DEFAULT_BAUDRATE)

from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect, dispatcher_send)

DOMAIN = 'poly_zigbee'
SIGNAL_ZIGBEE_FRAME_RECEIVED = 'signal_zigbee_frame_recv'
CMD_DEVICES_STATUS = [0x80, 0x00, 0xFF, 0xFF, 0x04, 0x44, 0xFF, 0xFF, 0x67, 0xA7]

@asyncio.coroutine
def async_setup(hass, config):
    """Set up Zigbee component."""
    import polyhome.phezsp
    
    uartpath = config[DOMAIN].get('uartpath', DEFAULT_UARTPATH)
    baudbrate = config[DOMAIN].get('baudbrate', DEFAULT_BAUDRATE)
    
    phezsp_ = polyhome.phezsp.PHEZSP()
    yield from phezsp_.connect(uartpath, baudbrate)

    def callback_data_recv(frame):
        hass.bus.fire('zigbee_data_event', {'data': frame })
        # dispatcher_send(hass, SIGNAL_ZIGBEE_FRAME_RECEIVED, frame)

    phezsp_.add_callback(callback_data_recv)
    
    def send_data_service(call):
        phezsp_.send(call.data.get('data'))
    
    hass.services.async_register(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, send_data_service)

    def close_serial_port(call):
        phezsp_.close()

    hass.bus.async_listen_once('homeassistant_stop', close_serial_port)

    # Routing and Non-routing binding
    # 3 times to ensure reliable communication
    for i in range(0,3):
        phezsp_.send(CMD_DEVICES_STATUS)
    
    return True
    