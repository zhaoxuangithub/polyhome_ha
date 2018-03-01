"""
Some of Msic Class
"""

class TopicConf(object):
    """Dongle Net Config"""
    def __init__(self):
        self._subtopic = ''
        self._pubtopic = ''

    def set_subtopic(self, topic):
        self._subtopic = topic

    def set_pubtopic(self, topic):
        self._pubtopic = topic
    
    def get_subtopic(self):
        return self._subtopic

    def get_pubtopic(self):
        return self._pubtopic


class DongleAttr(object):
    """Dongle Attr"""
    def __init__(self):
        self._channel = ''
        self._net_high = ''
        self._net_low = ''
        self._mode = 'channel'
        # disable / enable
        self._net_mode = 'disable'

    def set_channel(self, channel):
        self._channel = channel

    def set_net(self, net):
        net = net.split(':')
        self._net_high = net[0]
        self._net_low = net[1]
    
    def get_dongle_conf(self):
        net = self._net_high + ':' + self._net_low
        return {'channel': self._channel, 'net': net}

    def set_net_high(self, net_high):
        self._net_high = net_high

    def set_net_low(self, net_low):
        self._net_low = net_low

    def set_mode(self, mode):
        self._mode = mode

    def get_mode(self):
        return self._mode

    def set_network_mode(self, mode):
        self._net_mode = mode
    
    def get_network_mode(self):  
        return self._net_mode