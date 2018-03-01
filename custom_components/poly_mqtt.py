#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
import json

import polyhome.util.macaddr as mac_util
from polyhome.helper.contant import (
    MQTT_TOPIC_BIND_CLIENT, MQTT_TOPIC_BIND_HOST,
    MQTT_TOPIC_UNBIND_CLIENT, MQTT_TOPIC_UNBIND_HOST,
    MQTT_TOPIC_UPDATE, MQTT_TOPIC_CALL_SERVICE,MQTT_TOPIC_PUB_ACK) 

import homeassistant.loader as loader

DEPENDENCIES = ['mqtt']

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'poly_mqtt'


def setup(hass, config):
    """polyhome mqtt component"""

    mqtt = loader.get_component('mqtt')
    
    def mqtt_call_services_handler(topic, payload, qos):
        try:
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

    def mqtt_publish_service(call):
        msg = call.data.get('data')
        # new notify api
        pub_topic = MQTT_TOPIC_PUB_ACK.format(uuid_str)
        mqtt.publish(hass, pub_topic, msg)

    def mqtt_pub_state_change_service(call):
        msg = call.data.get('data')
        pub_topic = '/v1/polyhome-ha/host/{}/state_change/'.format(uuid_str)
        mqtt.publish(hass, pub_topic, msg)

    def mqtt_pub_device_into_net_service(call):
        msg = call.data.get('data')
        pub_topic = '/v1/polyhome-ha/host/{}/dev_into_zigbee/'.format(uuid_str)
        mqtt.publish(hass, pub_topic, msg)

    # 订阅监听主题
    dev_uuid = mac_util.get_uuid(hass.config.config_dir)
    uuid_str = str(dev_uuid)
    mqtt.subscribe(hass, MQTT_TOPIC_BIND_HOST + uuid_str, message_recv_bind)
    mqtt.subscribe(hass, MQTT_TOPIC_UNBIND_HOST + uuid_str, message_recv_unbind)
    mqtt.subscribe(hass, MQTT_TOPIC_UPDATE + uuid_str, message_recv_update)
    if mac_util.device_is_bind(hass.config.config_dir):
        mqtt.subscribe(hass, MQTT_TOPIC_CALL_SERVICE.format(uuid_str, '+'), mqtt_call_services_handler)

    def host_bind_id(family_id):  
        dev_uuid = mac_util.get_uuid(hass.config.config_dir)
        uuid_str = str(dev_uuid)
        if mac_util.device_is_bind(hass.config.config_dir):
            data_obj = {'status':'ERROR', 'type': 'bind', 'data': {'has_bind': 'true'}}
            data_str = json.dumps(data_obj)
            mqtt.publish(hass, MQTT_TOPIC_BIND_CLIENT + uuid_str, data_str)
            return
        mqtt.subscribe(hass, MQTT_TOPIC_CALL_SERVICE.format(uuid_str, '+'), mqtt_call_services_handler)
        mac_util.update_bind_state(hass.config.config_dir, 'true')
        data_obj = {'status':'OK', 'type': 'bind', 'data': {}}
        data_str = json.dumps(data_obj)
        mqtt.publish(hass, MQTT_TOPIC_BIND_CLIENT + dev_uuid, data_str)
        
    def host_unbind():
        mac_util.update_bind_state(hass.config.config_dir, 'false')
        data_obj = {'status':'OK', 'type': 'unbind', 'data': {}}
        data_str = json.dumps(data_obj)
        mqtt.publish(hass, MQTT_TOPIC_UNBIND_CLIENT + uuid_str, data_str)
        hass.services.call('homeassistant', 'restart')

    hass.services.register(DOMAIN, 'pub_data', mqtt_publish_service)
    hass.services.register(DOMAIN, 'mqtt_pub_state_change', mqtt_pub_state_change_service)
    hass.services.register(DOMAIN, 'mqtt_pub_device_into_net', mqtt_pub_device_into_net_service)
    
    return True



    