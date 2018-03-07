import asyncio
import binascii
import logging
import serial
import serial_asyncio

import pyzigbee.algorithm as checkcrc

_LOGGER = logging.getLogger(__name__)

# '0xc0', '0x0', '0x2b', '0x17', '0x2', '0xff', '0x40', '0x41'
RESULT_TIME_OUT = ['0xc0', '0x0', '0x0', '0x0', '0x2', '0xff', '0x39', '0x39']
RESULT_UNKOWN = ['0xc0', '0x0', '0x0', '0x0', '0x2', '0xff', '0x42', '0x39']

class Gateway(asyncio.Protocol):
    """Polyhome Zigbee Uart."""

    # 0xA0
    A0FLAG = 160
    # 0xC0
    C0FLAG = 192
    
    class Terminator:
        pass

    def __init__(self, application, connected_future=None, loop=None):
        self._application = application
        self._loop = loop
        self._send_seq = 0
        self._rec_seq = 0
        # recv buffer
        self._buffer = []
        self.stepindex = 0
        self._framelen = 0
        self._framecurlen = 0
        # send data queue
        self._sendq = asyncio.Queue()
        self._connected_future = connected_future
        self._pending = (-1, None)
        self._callback = None

    def connection_made(self, transport):
        """Callback when the uart is connected"""
        self._transport = transport
        if self._connected_future is not None:
            self._connected_future.set_result(True)
            asyncio.async(self._send_task())

    def data_received(self, data):
        """Callback when there is data received from the uart"""
        # print(binascii.hexlify(data))
        #_LOGGER.debug(data)
        for byte in data:
            self._extract_frame(byte)

    def data(self, data):
        """Send a data frame"""
        seq = self._send_seq
        self._send_seq = (seq + 1) % 8
        self._sendq.put_nowait((data, seq))

    def write(self, data):
        """Send data to the uart"""
        _LOGGER.debug("Sending: %s", data)
        self._transport.write(data)

    def close(self):
        self._sendq.put_nowait(self.Terminator)
        self._transport.close()

    def _extract_frame(self, data):
        """a frame data of Socket
        eg: 0xa0 0xad 0x2b 0x2f 0x11 0x0 0x2b 0x2f 0x70 0x1 0x0 0x0 0x0 0x0 0x0 0x$
        """
        if (data == self.A0FLAG or data == self.C0FLAG) and (self.stepindex == 0):
            # print("Head: ", hex(data))
            self.stepindex += 1
            self._buffer.append(hex(data))
        elif self.stepindex < 4 and self.stepindex >= 1:
            self.stepindex += 1
            self._buffer.append(hex(data))
        elif self.stepindex == 4:
            self.stepindex += 1
            self._framelen = int(data)
            # print("length: ", self._framelen)
            self._buffer.append(hex(data))
        elif self.stepindex == 5:
            if self._framecurlen < self._framelen:
                self._buffer.append(hex(data))
                self._framecurlen += 1
            elif self._framecurlen == self._framelen:
                self._buffer.append(hex(data))
                resu_crc = checkcrc.xorcrc_str(self._buffer)
                if data == resu_crc:
                    self.frame_received(self._buffer)
                self.reset()
    
    def reset(self):
        """reset all var"""
        self._buffer = []
        self._framecurlen = 0
        self._framelen = 0
        self.stepindex = 0

    def frame_received(self, data):
        """Frame receive handler
        39: TIMEOUT | 40: OK | 41: ERROR | 42: UNKOWN
        """
        # print(data)
        self._application.frame_received(data)

        if data[0] == '0xc0':
            pending, self._pending = self._pending, (-1, None)
            if data[-2] == '0x40':
                pending[1].set_result(True)
            elif data[-2] == '0x41':
                pending[1].set_result(True)
            else:
                pending[1].set_result(True)
                self._application.frame_received(RESULT_UNKOWN)

    @asyncio.coroutine
    def _send_task(self):
        from async_timeout import timeout
        """Send queue handler"""
        while True:
            item = yield from self._sendq.get()
            if item is self.Terminator:
                break
            data, seq = item
            try:
                self._pending = (seq, asyncio.Future())
                self.write(data)
                with timeout(2, loop=self._loop):
                    success = yield from self._pending[1]
            except asyncio.TimeoutError:
                self._application.frame_received(RESULT_TIME_OUT)

    def connection_lost(self, exc):
        self._sendq.put_nowait(self.Terminator)

@asyncio.coroutine
def connect(port, baudrate, application, loop=None):

    if loop is None:
        loop = asyncio.get_event_loop()

    connection_future = asyncio.Future()
    protocol = Gateway(application, connection_future, loop)

    transport, protocol = yield from serial_asyncio.create_serial_connection(
        loop,
        lambda:protocol,
        port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=False,
    )

    yield from connection_future

    return protocol