"""
Support for MQTT message handling.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/mqtt/
"""
import asyncio
from itertools import groupby
from typing import Optional, Any, Union, Callable, List, cast  # noqa: F401
from operator import attrgetter
import logging
import os
import socket
import time
import ssl
import re
import requests.certs
import attr
import json

import voluptuous as vol

from homeassistant.helpers.typing import HomeAssistantType, ConfigType, \
    ServiceDataType
from homeassistant.core import callback, Event, ServiceCall
from homeassistant.setup import async_prepare_setup_platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.loader import bind_hass
from homeassistant.helpers import template, config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util.async_ import (
    run_coroutine_threadsafe, run_callback_threadsafe)
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP, CONF_VALUE_TEMPLATE, CONF_USERNAME,
    CONF_PASSWORD, CONF_PORT, CONF_PROTOCOL, CONF_PAYLOAD)
from homeassistant.components.mqtt.server import HBMQTT_CONFIG_SCHEMA

REQUIREMENTS = ['paho-mqtt==1.3.1']

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'polylocalmqtt'

DATA_MQTT = 'poly_local_mqtt'

SERVICE_PUBLISH = 'publish'

CONF_EMBEDDED = 'embedded'
CONF_BROKER = 'broker'
CONF_CLIENT_ID = 'client_id'
CONF_DISCOVERY = 'discovery'
CONF_DISCOVERY_PREFIX = 'discovery_prefix'
CONF_KEEPALIVE = 'keepalive'
CONF_CERTIFICATE = 'certificate'
CONF_CLIENT_KEY = 'client_key'
CONF_CLIENT_CERT = 'client_cert'
CONF_TLS_INSECURE = 'tls_insecure'
CONF_TLS_VERSION = 'tls_version'

CONF_BIRTH_MESSAGE = 'birth_message'
CONF_WILL_MESSAGE = 'will_message'

CONF_STATE_TOPIC = 'state_topic'
CONF_COMMAND_TOPIC = 'command_topic'
CONF_AVAILABILITY_TOPIC = 'availability_topic'
CONF_PAYLOAD_AVAILABLE = 'payload_available'
CONF_PAYLOAD_NOT_AVAILABLE = 'payload_not_available'
CONF_QOS = 'qos'
CONF_RETAIN = 'retain'

PROTOCOL_31 = '3.1'
PROTOCOL_311 = '3.1.1'

DEFAULT_PORT = 1883
DEFAULT_KEEPALIVE = 60
DEFAULT_QOS = 0
DEFAULT_RETAIN = False
DEFAULT_PROTOCOL = PROTOCOL_311
DEFAULT_DISCOVERY = False
DEFAULT_DISCOVERY_PREFIX = 'homeassistant'
DEFAULT_TLS_PROTOCOL = 'auto'
DEFAULT_PAYLOAD_AVAILABLE = 'online'
DEFAULT_PAYLOAD_NOT_AVAILABLE = 'offline'

ATTR_TOPIC = 'topic'
ATTR_PAYLOAD = 'payload'
ATTR_PAYLOAD_TEMPLATE = 'payload_template'
ATTR_QOS = CONF_QOS
ATTR_RETAIN = CONF_RETAIN

MAX_RECONNECT_WAIT = 300  # seconds

import polyhome.util.macaddr as mac_util
from polyhome.helper.contant import (
    MQTT_TOPIC_BIND_CLIENT, MQTT_TOPIC_BIND_HOST,
    MQTT_TOPIC_UNBIND_CLIENT, MQTT_TOPIC_UNBIND_HOST,
    MQTT_TOPIC_UPDATE, MQTT_TOPIC_CALL_SERVICE, MQTT_TOPIC_PUB_ACK) 

def valid_subscribe_topic(value: Any, invalid_chars='\0') -> str:
    """Validate that we can subscribe using this MQTT topic."""
    value = cv.string(value)
    if all(c not in value for c in invalid_chars):
        return vol.Length(min=1, max=65535)(value)
    raise vol.Invalid('Invalid MQTT topic name')


def valid_publish_topic(value: Any) -> str:
    """Validate that we can publish using this MQTT topic."""
    return valid_subscribe_topic(value, invalid_chars='#+\0')


def valid_discovery_topic(value: Any) -> str:
    """Validate a discovery topic."""
    return valid_subscribe_topic(value, invalid_chars='#+\0/')


_VALID_QOS_SCHEMA = vol.All(vol.Coerce(int), vol.In([0, 1, 2]))

CLIENT_KEY_AUTH_MSG = 'client_key and client_cert must both be present in ' \
                      'the MQTT broker configuration'

MQTT_WILL_BIRTH_SCHEMA = vol.Schema({
    vol.Required(ATTR_TOPIC): valid_publish_topic,
    vol.Required(ATTR_PAYLOAD, CONF_PAYLOAD): cv.string,
    vol.Optional(ATTR_QOS, default=DEFAULT_QOS): _VALID_QOS_SCHEMA,
    vol.Optional(ATTR_RETAIN, default=DEFAULT_RETAIN): cv.boolean,
}, required=True)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_CLIENT_ID): cv.string,
        vol.Optional(CONF_KEEPALIVE, default=DEFAULT_KEEPALIVE):
            vol.All(vol.Coerce(int), vol.Range(min=15)),
        vol.Optional(CONF_BROKER): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_CERTIFICATE): vol.Any('auto', cv.isfile),
        vol.Inclusive(CONF_CLIENT_KEY, 'client_key_auth',
                      msg=CLIENT_KEY_AUTH_MSG): cv.isfile,
        vol.Inclusive(CONF_CLIENT_CERT, 'client_key_auth',
                      msg=CLIENT_KEY_AUTH_MSG): cv.isfile,
        vol.Optional(CONF_TLS_INSECURE): cv.boolean,
        vol.Optional(CONF_TLS_VERSION, default=DEFAULT_TLS_PROTOCOL):
            vol.Any('auto', '1.0', '1.1', '1.2'),
        vol.Optional(CONF_PROTOCOL, default=DEFAULT_PROTOCOL):
            vol.All(cv.string, vol.In([PROTOCOL_31, PROTOCOL_311])),
        vol.Optional(CONF_EMBEDDED): HBMQTT_CONFIG_SCHEMA,
        vol.Optional(CONF_WILL_MESSAGE): MQTT_WILL_BIRTH_SCHEMA,
        vol.Optional(CONF_BIRTH_MESSAGE): MQTT_WILL_BIRTH_SCHEMA,
        vol.Optional(CONF_DISCOVERY, default=DEFAULT_DISCOVERY): cv.boolean,
        vol.Optional(CONF_DISCOVERY_PREFIX,
                     default=DEFAULT_DISCOVERY_PREFIX): valid_discovery_topic,
    }),
}, extra=vol.ALLOW_EXTRA)

SCHEMA_BASE = {
    vol.Optional(CONF_QOS, default=DEFAULT_QOS): _VALID_QOS_SCHEMA,
}

MQTT_AVAILABILITY_SCHEMA = vol.Schema({
    vol.Optional(CONF_AVAILABILITY_TOPIC): valid_subscribe_topic,
    vol.Optional(CONF_PAYLOAD_AVAILABLE,
                 default=DEFAULT_PAYLOAD_AVAILABLE): cv.string,
    vol.Optional(CONF_PAYLOAD_NOT_AVAILABLE,
                 default=DEFAULT_PAYLOAD_NOT_AVAILABLE): cv.string,
})

MQTT_BASE_PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(SCHEMA_BASE)

# Sensor type platforms subscribe to MQTT events
MQTT_RO_PLATFORM_SCHEMA = MQTT_BASE_PLATFORM_SCHEMA.extend({
    vol.Required(CONF_STATE_TOPIC): valid_subscribe_topic,
    vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
})

# Switch type platforms publish to MQTT and may subscribe
MQTT_RW_PLATFORM_SCHEMA = MQTT_BASE_PLATFORM_SCHEMA.extend({
    vol.Required(CONF_COMMAND_TOPIC): valid_publish_topic,
    vol.Optional(CONF_RETAIN, default=DEFAULT_RETAIN): cv.boolean,
    vol.Optional(CONF_STATE_TOPIC): valid_subscribe_topic,
    vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
})

# Service call validation schema
MQTT_PUBLISH_SCHEMA = vol.Schema({
    vol.Required(ATTR_TOPIC): valid_publish_topic,
    vol.Exclusive(ATTR_PAYLOAD, CONF_PAYLOAD): object,
    vol.Exclusive(ATTR_PAYLOAD_TEMPLATE, CONF_PAYLOAD): cv.string,
    vol.Optional(ATTR_QOS, default=DEFAULT_QOS): _VALID_QOS_SCHEMA,
    vol.Optional(ATTR_RETAIN, default=DEFAULT_RETAIN): cv.boolean,
}, required=True)


# pylint: disable=invalid-name
PublishPayloadType = Union[str, bytes, int, float, None]
SubscribePayloadType = Union[str, bytes]  # Only bytes if encoding is None
MessageCallbackType = Callable[[str, SubscribePayloadType, int], None]


def _build_publish_data(topic: Any, qos: int, retain: bool) -> ServiceDataType:
    """Build the arguments for the publish service without the payload."""
    data = {ATTR_TOPIC: topic}
    if qos is not None:
        data[ATTR_QOS] = qos
    if retain is not None:
        data[ATTR_RETAIN] = retain
    return data


@bind_hass
def publish(hass: HomeAssistantType, topic, payload, qos=None,
            retain=None) -> None:
    """Publish message to an MQTT topic."""
    hass.add_job(async_publish, hass, topic, payload, qos, retain)


@callback
@bind_hass
def async_publish(hass: HomeAssistantType, topic: Any, payload, qos=None,
                  retain=None) -> None:
    """Publish message to an MQTT topic."""
    data = _build_publish_data(topic, qos, retain)
    data[ATTR_PAYLOAD] = payload
    hass.async_add_job(hass.services.async_call(DOMAIN, SERVICE_PUBLISH, data))


@bind_hass
def publish_template(hass: HomeAssistantType, topic, payload_template,
                     qos=None, retain=None) -> None:
    """Publish message to an MQTT topic using a template payload."""
    data = _build_publish_data(topic, qos, retain)
    data[ATTR_PAYLOAD_TEMPLATE] = payload_template
    hass.services.call(DOMAIN, SERVICE_PUBLISH, data)


@bind_hass
async def async_subscribe(hass: HomeAssistantType, topic: str,
                          msg_callback: MessageCallbackType,
                          qos: int = DEFAULT_QOS,
                          encoding: str = 'utf-8'):
    """Subscribe to an MQTT topic.

    Call the return value to unsubscribe.
    """
    async_remove = await hass.data[DATA_MQTT].async_subscribe(
        topic, msg_callback, qos, encoding)
    return async_remove


@bind_hass
def subscribe(hass: HomeAssistantType, topic: str,
              msg_callback: MessageCallbackType, qos: int = DEFAULT_QOS,
              encoding: str = 'utf-8') -> Callable[[], None]:
    """Subscribe to an MQTT topic."""
    async_remove = run_coroutine_threadsafe(
        async_subscribe(hass, topic, msg_callback, qos, encoding), hass.loop
    ).result()

    def remove():
        """Remove listener convert."""
        run_callback_threadsafe(hass.loop, async_remove).result()

    return remove


async def _async_setup_server(hass: HomeAssistantType,
                              config: ConfigType):
    """Try to start embedded MQTT broker.

    This method is a coroutine.
    """
    conf = config.get(DOMAIN, {})  # type: ConfigType

    server = await async_prepare_setup_platform(
        hass, config, DOMAIN, 'server')

    if server is None:
        _LOGGER.error("Unable to load embedded server")
        return None

    success, broker_config = \
        await server.async_start(hass, conf.get(CONF_EMBEDDED))

    if not success:
        return None
    return broker_config


async def _async_setup_discovery(hass: HomeAssistantType,
                                 config: ConfigType) -> bool:
    """Try to start the discovery of MQTT devices.

    This method is a coroutine.
    """
    conf = config.get(DOMAIN, {})  # type: ConfigType

    discovery = await async_prepare_setup_platform(
        hass, config, DOMAIN, 'discovery')

    if discovery is None:
        _LOGGER.error("Unable to load MQTT discovery")
        return False

    success = await discovery.async_start(
        hass, conf[CONF_DISCOVERY_PREFIX], config)  # type: bool

    return success


async def async_setup(hass: HomeAssistantType, config: ConfigType) -> bool:
    """Start the MQTT protocol service."""
    conf = config.get(DOMAIN)  # type: Optional[ConfigType]
    
    if conf is None:
        conf = CONFIG_SCHEMA({DOMAIN: {}})[DOMAIN]
    conf = cast(ConfigType, conf)

    client_id = conf.get(CONF_CLIENT_ID)  # type: Optional[str]
    keepalive = conf.get(CONF_KEEPALIVE)  # type: int

    # Only setup if embedded config passed in or no broker specified
    if CONF_EMBEDDED not in conf and CONF_BROKER in conf:
        broker_config = None
    else:
        broker_config = await _async_setup_server(hass, config)

    if CONF_BROKER in conf:
        broker = conf[CONF_BROKER]  # type: str
        port = conf[CONF_PORT]  # type: int
        username = conf.get(CONF_USERNAME)  # type: Optional[str]
        password = conf.get(CONF_PASSWORD)  # type: Optional[str]
        certificate = conf.get(CONF_CERTIFICATE)  # type: Optional[str]
        client_key = conf.get(CONF_CLIENT_KEY)  # type: Optional[str]
        client_cert = conf.get(CONF_CLIENT_CERT)  # type: Optional[str]
        tls_insecure = conf.get(CONF_TLS_INSECURE)  # type: Optional[bool]
        protocol = conf[CONF_PROTOCOL]  # type: str
    elif broker_config is not None:
        # If no broker passed in, auto config to internal server
        broker, port, username, password, certificate, protocol = broker_config
        # Embedded broker doesn't have some ssl variables
        client_key, client_cert, tls_insecure = None, None, None
        # hbmqtt requires a client id to be set.
        if client_id is None:
            client_id = 'home-assistant'
    else:
        err = "Unable to start MQTT broker."
        if conf.get(CONF_EMBEDDED) is not None:
            # Explicit embedded config, requires explicit broker config
            err += " (Broker configuration required.)"
        _LOGGER.error(err)
        return False

    # For cloudmqtt.com, secured connection, auto fill in certificate
    if (certificate is None and 19999 < port < 30000 and
            broker.endswith('.cloudmqtt.com')):
        certificate = os.path.join(os.path.dirname(__file__),
                                   'addtrustexternalcaroot.crt')

    # When the certificate is set to auto, use bundled certs from requests
    if certificate == 'auto':
        certificate = requests.certs.where()

    will_message = None  # type: Optional[Message]
    if conf.get(CONF_WILL_MESSAGE) is not None:
        will_message = Message(**conf.get(CONF_WILL_MESSAGE))
    birth_message = None  # type: Optional[Message]
    if conf.get(CONF_BIRTH_MESSAGE) is not None:
        birth_message = Message(**conf.get(CONF_BIRTH_MESSAGE))

    # Be able to override versions other than TLSv1.0 under Python3.6
    conf_tls_version = conf.get(CONF_TLS_VERSION)  # type: str
    if conf_tls_version == '1.2':
        tls_version = ssl.PROTOCOL_TLSv1_2
    elif conf_tls_version == '1.1':
        tls_version = ssl.PROTOCOL_TLSv1_1
    elif conf_tls_version == '1.0':
        tls_version = ssl.PROTOCOL_TLSv1
    else:
        import sys
        # Python3.6 supports automatic negotiation of highest TLS version
        if sys.hexversion >= 0x03060000:
            tls_version = ssl.PROTOCOL_TLS  # pylint: disable=no-member
        else:
            tls_version = ssl.PROTOCOL_TLSv1

    try:
        hass.data[DATA_MQTT] = MQTT(
            hass, broker, port, client_id, keepalive, username, password,
            certificate, client_key, client_cert, tls_insecure, protocol,
            will_message, birth_message, tls_version)
    except socket.error:
        _LOGGER.exception("Can't connect to the broker. "
                          "Please check your settings and the broker itself")
        return False

    async def async_stop_mqtt(event: Event):
        """Stop MQTT component."""
        await hass.data[DATA_MQTT].async_disconnect()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop_mqtt)

    success = await hass.data[DATA_MQTT].async_connect()  # type: bool
    if not success:
        return False

    def mqtt_publish_service(call):
        msg = call.data.get('data')
        # new notify api
        pub_topic = MQTT_TOPIC_PUB_ACK.format(uuid_str)
        hass.add_job(mqtt.async_publish, pub_topic, msg, 0, False)

    def mqtt_call_services_handler(topic, payload, qos):
        try:
            print(topic)
            data_json = json.loads(payload)
            domain = data_json.get('plugin')
            service = data_json.get('service')
            data = data_json.get('data')
            hass.services.call(domain, service, data)
        except Exception as e:
            print('mqtt message convert error')
        
    def message_recv_bind(topic, payload, qos):
        data_json = json.loads(payload)
        host_bind_id(data_json['id'])

    def message_recv_unbind(topic, payload, qos):
        host_unbind()

    def message_recv_update(topic, payload, qos):
        hass.services.call('gateway', 'host_update', '')

    def mqtt_pub_state_change_service(call):
        print('Local Mqtt State Change')
        msg = call.data.get('data')
        pub_topic = '/v1/polyhome-ha/host/{}/state_change/'.format(uuid_str)
        hass.async_add_job(hass.data[DATA_MQTT].async_publish, pub_topic, msg, 0, False)

    def mqtt_pub_device_into_net_service(call):
        msg = call.data.get('data')
        pub_topic = '/v1/polyhome-ha/host/{}/dev_into_zigbee/'.format(uuid_str)
        hass.async_add_job(hass.data[DATA_MQTT].async_publish, pub_topic, msg, 0, False)

    mqtt = hass.data[DATA_MQTT]
    # 订阅监听主题
    dev_uuid = mac_util.get_uuid(hass.config.config_dir)
    uuid_str = str(dev_uuid)
    await mqtt.async_subscribe(MQTT_TOPIC_BIND_HOST + uuid_str, message_recv_bind, 0, 'utf-8')
    await mqtt.async_subscribe(MQTT_TOPIC_UNBIND_HOST + uuid_str, message_recv_unbind, 0, 'utf-8')
    await mqtt.async_subscribe(MQTT_TOPIC_UPDATE + uuid_str, message_recv_update, 0, 'utf-8')
    if mac_util.device_is_bind(hass.config.config_dir):
        await mqtt.async_subscribe(MQTT_TOPIC_CALL_SERVICE.format(uuid_str, '+'), mqtt_call_services_handler, 0, 'utf-8')

    def host_bind_id(family_id):  
        dev_uuid = mac_util.get_uuid(hass.config.config_dir)
        uuid_str = str(dev_uuid)
        if mac_util.device_is_bind(hass.config.config_dir):
            data_obj = {'status':'ERROR', 'type': 'bind', 'data': {'has_bind': 'true'}}
            data_str = json.dumps(data_obj)
            mqtt.async_publish(MQTT_TOPIC_BIND_CLIENT + uuid_str, data_str, 0, False)
            return
        mqtt.async_subscribe(MQTT_TOPIC_CALL_SERVICE.format(uuid_str, '+'), mqtt_call_services_handler, 0, 'utf-8')
        mac_util.update_bind_state(hass.config.config_dir, 'true')
        data_obj = {'status':'OK', 'type': 'bind', 'data': {}}
        data_str = json.dumps(data_obj)
        mqtt.async_subscribe(MQTT_TOPIC_BIND_CLIENT + dev_uuid, data_str, 0, 'utf-8')
        
    def host_unbind():
        mac_util.update_bind_state(hass.config.config_dir, 'false')
        data_obj = {'status':'OK', 'type': 'unbind', 'data': {}}
        data_str = json.dumps(data_obj)
        mqtt.async_publish(hass, MQTT_TOPIC_UNBIND_CLIENT + uuid_str, data_str, 0, False)
        hass.services.call('homeassistant', 'restart')

    hass.services.async_register(DOMAIN, 'pub_data', mqtt_publish_service)
    hass.services.async_register(DOMAIN, 'mqtt_pub_state_change', mqtt_pub_state_change_service)
    hass.services.async_register(DOMAIN, 'mqtt_pub_device_into_net', mqtt_pub_device_into_net_service)

    return True


@attr.s(slots=True, frozen=True)
class Subscription(object):
    """Class to hold data about an active subscription."""

    topic = attr.ib(type=str)
    callback = attr.ib(type=MessageCallbackType)
    qos = attr.ib(type=int, default=0)
    encoding = attr.ib(type=str, default='utf-8')


@attr.s(slots=True, frozen=True)
class Message(object):
    """MQTT Message."""

    topic = attr.ib(type=str)
    payload = attr.ib(type=PublishPayloadType)
    qos = attr.ib(type=int, default=0)
    retain = attr.ib(type=bool, default=False)


class MQTT(object):
    """Home Assistant MQTT client."""

    def __init__(self, hass: HomeAssistantType, broker: str, port: int,
                 client_id: Optional[str], keepalive: Optional[int],
                 username: Optional[str], password: Optional[str],
                 certificate: Optional[str], client_key: Optional[str],
                 client_cert: Optional[str], tls_insecure: Optional[bool],
                 protocol: Optional[str], will_message: Optional[Message],
                 birth_message: Optional[Message], tls_version) -> None:
        """Initialize Home Assistant MQTT client."""
        import paho.mqtt.client as mqtt

        self.hass = hass
        self.broker = broker
        self.port = port
        self.keepalive = keepalive
        self.subscriptions = []  # type: List[Subscription]
        self.birth_message = birth_message
        self._mqttc = None  # type: mqtt.Client
        self._paho_lock = asyncio.Lock(loop=hass.loop)

        if protocol == PROTOCOL_31:
            proto = mqtt.MQTTv31  # type: int
        else:
            proto = mqtt.MQTTv311

        if client_id is None:
            self._mqttc = mqtt.Client(protocol=proto)
        else:
            self._mqttc = mqtt.Client(client_id, protocol=proto)

        if username is not None:
            self._mqttc.username_pw_set(username, password)

        if certificate is not None:
            self._mqttc.tls_set(
                certificate, certfile=client_cert,
                keyfile=client_key, tls_version=tls_version)

            if tls_insecure is not None:
                self._mqttc.tls_insecure_set(tls_insecure)

        self._mqttc.on_connect = self._mqtt_on_connect
        self._mqttc.on_disconnect = self._mqtt_on_disconnect
        self._mqttc.on_message = self._mqtt_on_message

        if will_message is not None:
            self._mqttc.will_set(*attr.astuple(will_message))

    async def async_publish(self, topic: str, payload: PublishPayloadType,
                            qos: int, retain: bool) -> None:
        """Publish a MQTT message.

        This method must be run in the event loop and returns a coroutine.
        """
        async with self._paho_lock:
            await self.hass.async_add_job(
                self._mqttc.publish, topic, payload, qos, retain)

    async def async_connect(self) -> bool:
        """Connect to the host. Does process messages yet.

        This method is a coroutine.
        """
        result = None  # type: int
        try:
            result = await self.hass.async_add_job(
                self._mqttc.connect, self.broker, self.port, self.keepalive)
        except OSError as err:
            _LOGGER.error('Failed to connect due to exception: %s', err)
            return False

        if result != 0:
            import paho.mqtt.client as mqtt
            _LOGGER.error('Failed to connect: %s', mqtt.error_string(result))
            return False

        self._mqttc.loop_start()
        return True

    @callback
    def async_disconnect(self):
        """Stop the MQTT client.

        This method must be run in the event loop and returns a coroutine.
        """
        def stop():
            """Stop the MQTT client."""
            self._mqttc.disconnect()
            self._mqttc.loop_stop()

        return self.hass.async_add_job(stop)

    async def async_subscribe(self, topic: str,
                              msg_callback: MessageCallbackType,
                              qos: int, encoding: str) -> Callable[[], None]:
        """Set up a subscription to a topic with the provided qos.

        This method is a coroutine.
        """
        if not isinstance(topic, str):
            raise HomeAssistantError("topic needs to be a string!")

        subscription = Subscription(topic, msg_callback, qos, encoding)
        self.subscriptions.append(subscription)

        await self._async_perform_subscription(topic, qos)

        @callback
        def async_remove() -> None:
            """Remove subscription."""
            if subscription not in self.subscriptions:
                raise HomeAssistantError("Can't remove subscription twice")
            self.subscriptions.remove(subscription)

            if any(other.topic == topic for other in self.subscriptions):
                # Other subscriptions on topic remaining - don't unsubscribe.
                return
            self.hass.async_add_job(self._async_unsubscribe(topic))

        return async_remove

    async def _async_unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic.

        This method is a coroutine.
        """
        async with self._paho_lock:
            result = None  # type: int
            result, _ = await self.hass.async_add_job(
                self._mqttc.unsubscribe, topic)
            _raise_on_error(result)

    async def _async_perform_subscription(self, topic: str, qos: int) -> None:
        """Perform a paho-mqtt subscription."""
        _LOGGER.debug("Subscribing to %s", topic)

        async with self._paho_lock:
            result = None  # type: int
            result, _ = await self.hass.async_add_job(
                self._mqttc.subscribe, topic, qos)
            _raise_on_error(result)

    def _mqtt_on_connect(self, _mqttc, _userdata, _flags,
                         result_code: int) -> None:
        """On connect callback.

        Resubscribe to all topics we were subscribed to and publish birth
        message.
        """
        import paho.mqtt.client as mqtt

        if result_code != mqtt.CONNACK_ACCEPTED:
            _LOGGER.error('Unable to connect to the MQTT broker: %s',
                          mqtt.connack_string(result_code))
            self._mqttc.disconnect()
            return

        # Group subscriptions to only re-subscribe once for each topic.
        keyfunc = attrgetter('topic')
        for topic, subs in groupby(sorted(self.subscriptions, key=keyfunc),
                                   keyfunc):
            # Re-subscribe with the highest requested qos
            max_qos = max(subscription.qos for subscription in subs)
            self.hass.add_job(self._async_perform_subscription, topic, max_qos)

        if self.birth_message:
            self.hass.add_job(
                self.async_publish(*attr.astuple(self.birth_message)))

    def _mqtt_on_message(self, _mqttc, _userdata, msg) -> None:
        """Message received callback."""
        self.hass.add_job(self._mqtt_handle_message, msg)

    @callback
    def _mqtt_handle_message(self, msg) -> None:
        _LOGGER.debug("Received message on %s: %s", msg.topic, msg.payload)

        for subscription in self.subscriptions:
            if not _match_topic(subscription.topic, msg.topic):
                continue

            payload = msg.payload  # type: SubscribePayloadType
            if subscription.encoding is not None:
                try:
                    payload = msg.payload.decode(subscription.encoding)
                except (AttributeError, UnicodeDecodeError):
                    _LOGGER.warning("Can't decode payload %s on %s "
                                    "with encoding %s",
                                    msg.payload, msg.topic,
                                    subscription.encoding)
                    continue

            self.hass.async_run_job(subscription.callback,
                                    msg.topic, payload, msg.qos)

    def _mqtt_on_disconnect(self, _mqttc, _userdata, result_code: int) -> None:
        """Disconnected callback."""
        # When disconnected because of calling disconnect()
        if result_code == 0:
            return

        tries = 0

        while True:
            try:
                if self._mqttc.reconnect() == 0:
                    _LOGGER.info("Successfully reconnected to the MQTT server")
                    break
            except socket.error:
                pass

            wait_time = min(2**tries, MAX_RECONNECT_WAIT)
            _LOGGER.warning(
                "Disconnected from MQTT (%s). Trying to reconnect in %s s",
                result_code, wait_time)
            # It is ok to sleep here as we are in the MQTT thread.
            time.sleep(wait_time)
            tries += 1


def _raise_on_error(result_code: int) -> None:
    """Raise error if error result."""
    if result_code != 0:
        import paho.mqtt.client as mqtt

        raise HomeAssistantError(
            'Error talking to MQTT: {}'.format(mqtt.error_string(result_code)))


def _match_topic(subscription: str, topic: str) -> bool:
    """Test if topic matches subscription."""
    reg_ex_parts = []  # type: List[str]
    suffix = ""
    if subscription.endswith('#'):
        subscription = subscription[:-2]
        suffix = "(.*)"
    sub_parts = subscription.split('/')
    for sub_part in sub_parts:
        if sub_part == "+":
            reg_ex_parts.append(r"([^\/]+)")
        else:
            reg_ex_parts.append(re.escape(sub_part))

    reg_ex = "^" + (r'\/'.join(reg_ex_parts)) + suffix + "$"

    reg = re.compile(reg_ex)

    return reg.match(topic) is not None

