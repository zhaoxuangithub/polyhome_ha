import logging
import asyncio
import voluptuous as vol
import json
import time

import homeassistant.helpers.config_validation as cv
from homeassistant.components.cover import (PLATFORM_SCHEMA, CoverDevice, SUPPORT_OPEN, SUPPORT_CLOSE)

import polyhome.util.algorithm as checkcrc

DOMAIN = 'polysccurtain2'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

CMD_OPEN = [0x80, 0x00, 0xb4, 0x53, 0x6, 0x44, 0xb4, 0x53, 0x60, 0x1, 0x1, 0xff]
CMD_CLOSE = [0x80, 0x00, 0xb4, 0x53, 0x6, 0x44, 0xb4, 0x53, 0x60, 0x0, 0x0, 0xff]

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional('name'): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Polyhome CoverDevice platform."""

    sccurtains = []
    if discovery_info is not None:
        # Not using hostname, as it seems to vary.
        device = {'name': discovery_info['name'] + '1', 'mac': discovery_info['mac'], 'way': '1'}
        device1 = {'name': discovery_info['name'] + '2', 'mac': discovery_info['mac'], 'way': '2'}
        sccurtains.append(RMCover(hass, device, None))
        sccurtains.append(RMCover(hass, device1, None))
    else:
        for mac, device_config in config['devices'].items():
            device = {'name': device_config['name'] + '1', 'mac': mac, 'way': '1'}
            device1 = {'name': device_config['name'] + '2', 'mac': mac, 'way': '2'}
            sccurtains.append(RMCover(hass, device, device_config))
            sccurtains.append(RMCover(hass, device1, device_config))

    add_devices(sccurtains, True)

    def event_zigbee_msg_handle(event):
        """Listener to handle fired events."""
        bytearr = event.data.get('data')
        if bytearr[0] == '0xa0' and bytearr[5] == '0x63':
            mac_1 = bytearr[6].replace('0x', '')
            mac_h = bytearr[7].replace('0x', '')
            mac_str = mac_1 + "#" + mac_h
            for dev in sccurtains:
                if dev.mac == mac_str:
                    dev.set_available(True)
                    if bytearr[8] == '0x70':
                        # 一路开
                        if bytearr[9] == '0x1' and bytearr[10] == '0x0':
                            if dev.way == '1':
                                dev.set_state(True)
                        # 一路关
                        elif bytearr[9] == '0x0' and bytearr[10] == '0x1':
                            if dev.way == '1':
                                dev.set_state(False)
                        # 一路停
                        elif bytearr[9] == '0x0' and bytearr[10] == '0x0':
                            if dev.way == '1':
                                dev.set_state(False)
                        # 二路开
                        if bytearr[11] == '0x1' and bytearr[12] == '0x0':
                            if dev.way == '2':
                                dev.set_state(False)
                        # 二路关
                        elif bytearr[11] == '0x0' and bytearr[12] == '0x1':
                            if dev.way == '2':
                                dev.set_state(False)
                        # 二路停
                        elif bytearr[11] == '0x0' and bytearr[12] == '0x0':
                            if dev.way == '2':
                                dev.set_state(True)
                    if bytearr[8] == '0xcc':
                        """heart beat"""
                        # 一路开
                        if bytearr[9] == '0x1' and bytearr[10] == '0x0':
                            if dev.way == '1':
                                dev.set_state(True)
                        # 一路关
                        elif bytearr[9] == '0x0' and bytearr[10] == '0x1':
                            if dev.way == '1':
                                dev.set_state(False)
                        # 一路停
                        elif bytearr[9] == '0x0' and bytearr[10] == '0x0':
                            if dev.way == '1':
                                dev.set_state(False)
                        # 二路开
                        if bytearr[11] == '0x1' and bytearr[12] == '0x0':
                            if dev.way == '2':
                                dev.set_state(True)
                        # 二路关
                        elif bytearr[11] == '0x0' and bytearr[12] == '0x1':
                            if dev.way == '2':
                                dev.set_state(False)
                        # 二路停
                        elif bytearr[11] == '0x0' and bytearr[12] == '0x0':
                            if dev.way == '2':
                                dev.set_state(False)
                        dev.heart_beat()
                    if bytearr[8] == '0x77':
                        """device status"""
                        # 一路开
                        if bytearr[9] == '0x1' and bytearr[10] == '0x0':
                            if dev.way == '1':
                                dev.set_state(True)
                        # 一路关
                        elif bytearr[9] == '0x0' and bytearr[10] == '0x1':
                            if dev.way == '1':
                                dev.set_state(False)
                        # 一路停
                        elif bytearr[9] == '0x0' and bytearr[10] == '0x0':
                            if dev.way == '1':
                                dev.set_state(False)
                        # 二路开
                        if bytearr[11] == '0x1' and bytearr[12] == '0x0':
                            if dev.way == '2':
                                dev.set_state(True)
                        # 二路关
                        elif bytearr[11] == '0x0' and bytearr[12] == '0x1':
                            if dev.way == '2':
                                dev.set_state(False)
                        # 二路停
                        elif bytearr[11] == '0x0' and bytearr[12] == '0x0':
                            if dev.way == '2':
                                dev.set_state(False)

                        if not bytearr[22] == '0xff':
                            hass.bus.fire('event_zigbee_device_status', {'router': bytearr[2:4], 'device': bytearr[22:27]})
                        if not bytearr[27] == '0xff':
                            hass.bus.fire('event_zigbee_device_status', {'router': bytearr[2:4], 'device': bytearr[27:32]})
                        if not bytearr[32] == '0xff':
                            hass.bus.fire('event_zigbee_device_status', {'router': bytearr[2:4], 'device': bytearr[32:37]})
                        if not bytearr[37] == '0xff':
                            hass.bus.fire('event_zigbee_device_status', {'router': bytearr[2:4], 'device': bytearr[37:42]})
                        if not bytearr[42] == '0xff':
                            hass.bus.fire('event_zigbee_device_status', {'router': bytearr[2:4], 'device': bytearr[42:47]})
                        if not bytearr[47] == '0xff':
                            hass.bus.fire('event_zigbee_device_status', {'router': bytearr[2:4], 'device': bytearr[47:52]})
                        if not bytearr[52] == '0xff':
                            hass.bus.fire('event_zigbee_device_status', {'router': bytearr[2:4], 'device': bytearr[52:57]})
        if bytearr[0] == '0xc0':
            mac_l, mac_h = bytearr[2].replace('0x', ''), bytearr[3].replace('0x', '')
            mac_str = mac_l + '#' + mac_h
            dev = next((dev for dev in sccurtains if dev.mac == mac_str), None)
            for dev in sccurtains:
                if dev.mac == mac_str:
                    if bytearr[6] == '0x41':
                        dev.set_available(False)
                    if bytearr[6] == '0x40':
                        dev.set_available(True)
            
    # Listen for when zigbee_data_event is fired
    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_msg_handle)

    # device online check
    def handle_time_changed_event(call):
        now = time.time()
        for device in sccurtains:
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
        self._way = device['way']
        self._config = dev_conf
        self._state = None
        self._available = True
        self._closed = True
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
    def way(self):
        return self._way

    @property
    def is_closed(self):
        return self._closed

    @property
    def available(self):
        """Return if bulb is available."""
        return self._available
    
    @property
    def heart_time_stamp(self):
        return self._heart_timestamp

    def set_available(self, available):
        self._available = available
        self.schedule_update_ha_state()

    def set_state(self, state):
        self._closed = state
        self.schedule_update_ha_state()

    def close_cover(self, **kwargs):
        """Close the cover."""
        if self._way == '1':
            self._closed = True
            mac = self._mac.split('#')
            CMD_CLOSE[2], CMD_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
            CMD_CLOSE[6], CMD_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
            CMD_CLOSE[-3] = 0x2
            CMD_CLOSE[-2] = 0x1
            resu_crc = checkcrc.xorcrc_hex(CMD_CLOSE)
            CMD_CLOSE[-1] = resu_crc
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {
                "data": CMD_CLOSE
            })
        if self._way == '2':
            self._closed = True
            mac = self._mac.split('#')
            CMD_CLOSE[2], CMD_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
            CMD_CLOSE[6], CMD_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
            CMD_CLOSE[-3] = 0x4
            CMD_CLOSE[-2] = 0x1
            resu_crc = checkcrc.xorcrc_hex(CMD_CLOSE)
            CMD_CLOSE[-1] = resu_crc
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {
                "data": CMD_CLOSE
            })

    def open_cover(self, **kwargs):
        """Open the cover."""
        if self._way == '1':
            self._closed = False
            mac = self._mac.split('#')
            CMD_OPEN[2], CMD_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
            CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
            CMD_OPEN[-2] = 0x1
            CMD_OPEN[-3] = 0x1
            resu_crc = checkcrc.xorcrc_hex(CMD_OPEN)
            CMD_OPEN[-1] = resu_crc
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {
                "data": CMD_OPEN
            })
        elif self._way == '2':
            self._closed = False
            mac = self._mac.split('#')
            CMD_OPEN[2], CMD_OPEN[3] = int(mac[0], 16), int(mac[1], 16)
            CMD_OPEN[6], CMD_OPEN[7] = int(mac[0], 16), int(mac[1], 16)
            CMD_OPEN[-3] = 0x3
            CMD_OPEN[-2] = 0x1
            resu_crc = checkcrc.xorcrc_hex(CMD_OPEN)
            CMD_OPEN[-1] = resu_crc
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {
                "data": CMD_OPEN
            })

    def stop_cover(self, **kwargs):
        """Stop the cover."""
        mac = self._mac.split('#')
        if self._way == '1':
            CMD_CLOSE[2], CMD_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
            CMD_CLOSE[6], CMD_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
            CMD_CLOSE[-3] = 0x1
            CMD_CLOSE[-2] = 0x0
            resu_crc = checkcrc.xorcrc_hex(CMD_CLOSE)
            CMD_CLOSE[-1] = resu_crc
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {
                "data": CMD_CLOSE
            })
        elif self._way == '2':
            CMD_CLOSE[2], CMD_CLOSE[3] = int(mac[0], 16), int(mac[1], 16)
            CMD_CLOSE[6], CMD_CLOSE[7] = int(mac[0], 16), int(mac[1], 16)
            CMD_CLOSE[-3] = 0x3
            CMD_CLOSE[-2] = 0x0
            resu_crc = checkcrc.xorcrc_hex(CMD_CLOSE)
            CMD_CLOSE[-1] = resu_crc
            self._hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {
                "data": CMD_CLOSE
            })

    def update(self):
        """update status"""
        self._state = self.is_closed

    def heart_beat(self):
        self._heart_timestamp = time.time()
        entity_id = 'cover.' + self.name
        self._hass.services.call('gateway', 'publish_heart_beat', {'entity_id': entity_id})