import asyncio
import logging

from . import uart

class PHEZSP(object):
    """PolyHome Ember Zigbee Serial Port"""

    def __init__(self):
        self._callbacks = {}
        self._gw = None

    @asyncio.coroutine
    def connect(self, device, baudrate):
        assert self._gw is None
        self._gw = yield from uart.connect(device, baudrate, self)    

    def reset(self):
        return self._gw.reset()

    def close(self):
        return self._gw.close()

    def send(self, data):
        self._gw.data(data)

    def frame_received(self, data):
        """Handle a received Zigbee Dongle frame"""
        self.handle_callback(data)

    def add_callback(self, cb):
        id_ = hash(cb)
        while id_ in self._callbacks:
            id_ += 1
        self._callbacks[id_] = cb
        return id_

    def remove_callback(self, id_):
        return self._callbacks.pop(id_)

    def handle_callback(self, *args):
        for callback_id, handler in self._callbacks.items():
            try:
                handler(*args)
            except Exception as e:
                LOGGER.exception("Exception running handler", exc_info=e)

