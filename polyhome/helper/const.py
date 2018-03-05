"""defined some const var"""

CUR_VERSION = '0.0.3_beta'

DEFAULT_TOPIC_SUB = '/v1/polyhome-ha/host/house/1/family/unkown'
DEFAULT_TOPIC_PUB = '/v1/polyhome-ha/client/house/1/family/unkown'

ATTR_DATA = 'data'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'

DEFAULT_UARTPATH = '/dev/tty.usbserial'
DEFAULT_BAUDRATE = '57600'

MQTT_TOPIC_BIND_HOST = '/v1/polyhome-ha/host/bind/'
MQTT_TOPIC_BIND_CLIENT = '/v1/polyhome-ha/client/bind/'
MQTT_TOPIC_UNBIND_HOST = '/v1/polyhome-ha/host/unbind/'
MQTT_TOPIC_UNBIND_CLIENT = '/v1/polyhome-ha/client/unbind/'
MQTT_TOPIC_UPDATE = '/v1/polyhome-ha/host/update/'
MQTT_TOPIC_CALL_SERVICE = '/v1/polyhome-ha/host/{}/user_id/{}/call_service/'

CONTANT_SUPPORT = ['sensor', 'binary_sensor', 'light', 'switch', 'lock', 'zwave', \
                    'cover', 'media_player', 'climate']
