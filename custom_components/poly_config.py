#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import sys
import json
import yaml
import logging
import enum
import uuid
import asyncio
import async_timeout
from datetime import datetime
from urllib import request

from homeassistant import setup as Setup
from homeassistant.helpers import discovery
from homeassistant.util.yaml import load_yaml, dump
from homeassistant.util import dt as date_util, location as loc_util
from homeassistant.const import (
    CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME, CONF_PACKAGES, CONF_UNIT_SYSTEM,
    CONF_TIME_ZONE, CONF_ELEVATION, CONF_UNIT_SYSTEM_METRIC,
    CONF_UNIT_SYSTEM_IMPERIAL, CONF_TEMPERATURE_UNIT, TEMP_CELSIUS, 
    CONF_CUSTOMIZE, CONF_CUSTOMIZE_DOMAIN, CONF_CUSTOMIZE_GLOB, CONF_WHITELIST_EXTERNAL_DIRS)

import polyhome.util.algorithm as checkcrc
import polyhome.util.macaddr as mac_util
from polyhome.util.yamlformat import FormatData, Loader
from polyhome import GroupsManager, DeviceManager, FriendlyNameManager, AutomationsManager, DevicePluginManager
from polyhome.helper.contant import DEFAULT_CONF_CONTENT, DEFAULT_EXISTS_FILE, POLY_MQTT_CONFIG, POLY_HOMEASSISTANT_CONFIG
from polyhome.misc import DongleAttr
from polyhome.util.zipfile import ZFile
from polyhome.helper.const import CUR_VERSION
from polyhome.helper.const import CONTANT_SUPPORT

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'poly_config'
POLY_ZIGBEE_DOMAIN = 'poly_zb_uart'
POLY_ZIGBEE_SERVICE = 'send_d'
EVENT_ZIGBEE_RECV = 'zigbee_data_event'

# /dev/tty.usbserial
UART_PATH = '/dev/tty.usbserial'

CMD_EDIT_DONGLE = [0x80, 0x0, 0x0, 0x0, 0x19, 0x44, 0x0, 0x0, 0xf, 0x0, 0x0, \
                    0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, \
                    0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0xe3]
CMD_INTO_NET = [0x80, 0x00, 0xFF, 0xFE, 0x02, 0xAD, 0x01, 0x2F]   
CMD_OUT_NET = [0x80, 0x00, 0xFF, 0xFE, 0x02, 0xAD, 0x00, 0x2E]
CMD_GET_DONGLE_NET_HIGH = [0x80, 0x00, 0xFF, 0xFE, 0x02, 0xa3, 0x6d, 0x4d]
CMD_GET_DONGLE_NET_LOW = [0x80, 0x00, 0xFF, 0xFE, 0x02, 0xa3, 0x6e, 0x4e]
CMD_GET_DONGLE_NET_CHANNEL = [0x80, 0x00, 0xFF, 0xFE, 0x02, 0xa3, 0x6c, 0x4c]


def setup(hass, config):
    """Set up polyhome config component"""

    # config dir : hass.config.config_dir
    mac_util._create_uuid(hass.config.config_dir)
    if mac_util.is_factory_reset(hass.config.config_dir):
        Loader.add_constructor('!include', Loader.include)
        y_loader = FormatData()
        y_loader.set_yaml_save_path(hass.config.config_dir, False)
        y_loader.set_homeassistant_config()
        y_loader.set_default_conf_content()
        y_loader.set_default_mqtt_config(mac_util.get_mac_address())
        mac_util.set_reset_flag(hass.config.config_dir)
        # reboot service after config
        hass.services.call('homeassistant', 'restart', '')
    else:
        print("PolyHome Config is Inited")

    def get_host_sn_service(call):
        mac = mac_util.get_mac_address()
        msg = {'type': 'get_host_sn', 'status': 'OK', 'data': {'sn': mac}}
        data_str = json.dumps(msg)
        pub_dict = {'data': data_str}
        hass.services.call('poly_mqtt', 'pub_data', pub_dict)

    hass.services.register(DOMAIN, 'get_host_sn', get_host_sn_service)


    """主机数据管理service
    """
    def ha_factory_reset_service(call):
        """recovery factory status"""
        try:
            os.remove(hass.config.config_dir + '/.reset')
        except:
            pass
        hass.services.call('homeassistant', 'restart', '')
    
    hass.services.register(DOMAIN, 'ha_factory_reset', ha_factory_reset_service)
    

    """设备管理service
    """
    device_mgr = DeviceManager(hass, config)
    def get_states_service(call):
        """return All entitys states"""
        try:
            json_data = device_mgr.get_devices()
            data_obj = {'status':'OK', 'data': json_data, 'type': 'all_states'}
            data_str = {'data': json.dumps(data_obj)}
            hass.services.call('poly_mqtt', 'pub_data', data_str)
        except Exception as e:
            data_obj = {'status':'OK', 'data': {'msg': 'Exception'}, 'type': 'all_states'}
            data_str = {'data': json.dumps(data_obj)}
            hass.services.call('poly_mqtt', 'pub_data', data_str)
    
    hass.services.register(DOMAIN, 'get_states', get_states_service)


    def edit_friendlyname_service(call):
        """Edit Device Automation Group Friendlyname"""
        try:
            id_dev = call.data.get('entity_id')
            name = call.data.get('friendly_name')
            name_mgr = FriendlyNameManager(hass, config)
            name_mgr.edit_friendly_name(id_dev, name)
            hass.add_job(async_reload_core_conf(hass))
            data_obj = {'status':'OK', 'data': {}, 'type': 'edit_friendlyname'}
            data_str = {'data': json.dumps(data_obj)}
            hass.services.call('poly_mqtt', 'pub_data', data_str)
        except Exception as e:
            data_obj = {'status':'ERROR', 'data': {'msg': 'Exception'}, 'type': 'edit_friendlyname'}
            data_str = {'data': json.dumps(data_obj)}
            hass.services.call('poly_mqtt', 'pub_data', data_str)

    hass.services.register(DOMAIN, 'edit_friendlyname', edit_friendlyname_service)


    """房间管理service
    """
    group_mgr = GroupsManager(hass, config)
    def get_groups_service(call):
        """return All group"""
        try:
            json_data = group_mgr.get_groups()
            data_obj = {'status':'OK', 'data': json_data, 'type': 'all_groups'}
            notity_client_data(data_obj)
        except Exception as e:
            data_obj = {'status':'ERROR', 'data': {[]}, 'type': 'all_groups'}
            notity_client_data(data_obj)

    def edit_group_service(call):
        """Edit group"""
        try:
            group_id = call.data.get('entity_id')
            atrributes = call.data.get('attributes')['entity_id']
            friendly_name = call.data.get('attributes')['friendly_name']
            if 'group.' in group_id:
                group_id = group_id.replace('group.', '')
            group_mgr.edit_group(group_id, atrributes, friendly_name)
            hass.services.call('group', 'reload')
            data_obj = {'status':'OK', 'data': {}, 'type': 'edit_group'}
            notity_client_data(data_obj)
        except Exception as e:
            data_obj = {'status':'ERROR', 'data': {'msg': 'Exception'}, 'type': 'edit_group'}
            notity_client_data(data_obj)

    def delete_group_service(call):
        """Delete group"""
        try:
            group_id = call.data.get('entity_id')
            if 'group.' in group_id:
                group_id = group_id.replace('group.', '')
            
            group_mgr.delete_group(group_id)
            hass.services.call('group', 'reload')
            data_obj = {'status':'OK', 'data': {}, 'type': 'delete_group'}
            notity_client_data(data_obj)
        except Exception as e:
            data_obj = {'status':'ERROR', 'data': {}, 'type': 'delete_group'}
            notity_client_data(data_obj)

    def device_edit_group_service(call):
        """edit device group id"""
        try:
            old_id = call.data.get('old_id')
            new_id = call.data.get('new_id')
            entity_ids = call.data.get('entity_id')
            for entity_id in entity_ids:
                group_mgr.del_group_device(entity_id)
            for entity_id in entity_ids:
                group_mgr.add_group_device(new_id, entity_id)
            hass.services.call('group', 'reload')
            data_obj = {'status':'OK', 'data': {}, 'type': 'device_edit_groups'}
            data_str = {'data': json.dumps(data_obj)}
            hass.services.call('poly_mqtt', 'pub_data', data_str)
        except Exception as e:
            data_obj = {'status':'ERROR', 'data': {'msg': e}, 'type': 'device_edit_groups'}
            data_str = {'data': json.dumps(data_obj)}
            hass.services.call('poly_mqtt', 'pub_data', data_str)

    hass.services.register(DOMAIN, 'get_groups', get_groups_service)
    hass.services.register(DOMAIN, 'edit_group', edit_group_service)
    hass.services.register(DOMAIN, 'delete_group', delete_group_service)
    hass.services.register(DOMAIN, 'device_edit_group', device_edit_group_service)
    
    """Dongle管理service
    """
    dongleattr = DongleAttr()
    def zigbee_network_service(call):
        status = call.data.get('status')
        if status == 'enable':
            hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_INTO_NET})
            dongleattr.set_network_mode('enable')
        else:
            hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_OUT_NET})
            dongleattr.set_network_mode('disable')
    
    def edit_dongle_conf_service(call):
        channel = call.data.get('channel')
        net = call.data.get('net')
        net_arry = net.split(':')
        CMD_EDIT_DONGLE[8] = int(channel, 10)
        CMD_EDIT_DONGLE[9] = int(net_arry[0], 16)
        CMD_EDIT_DONGLE[10] = int(net_arry[1], 16)
        resu_crc = checkcrc.xorcrc_hex(CMD_EDIT_DONGLE)
        CMD_EDIT_DONGLE[-1] = resu_crc
        hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_EDIT_DONGLE})

    def get_dongle_conf_net_info_h():
        hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_GET_DONGLE_NET_HIGH})
        dongleattr.set_mode('conf_high')

    def get_dongle_conf_net_info_l():
        hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_GET_DONGLE_NET_LOW})
        dongleattr.set_mode('conf_low')

    def get_dongle_conf_channel():
        hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": CMD_GET_DONGLE_NET_CHANNEL})
        dongleattr.set_mode('channel')

    def get_dongle_conf_service(call):
        get_dongle_conf_channel()

    hass.services.register(DOMAIN, 'zigbee_network', zigbee_network_service)
    hass.services.register(DOMAIN, 'edit_dongle_conf', edit_dongle_conf_service)
    hass.services.register(DOMAIN, 'get_dongle_conf', get_dongle_conf_service)

    # Broadcast Client some msg 
    def notity_client_data(data_obj):
        data_str = {'data': json.dumps(data_obj)}
        hass.services.call('poly_mqtt', 'pub_data', data_str)

    # Broadcast Client some msg 
    def notity_client_device_into_net(data_obj):
        data_str = {'data': json.dumps(data_obj)}
        hass.services.call('poly_mqtt', 'mqtt_pub_device_into_net', data_str)

    """Handler Zigbee Return Data
    """
    def event_zigbee_msg_handle(event):
        """Listener to handle fired events"""
        pack_list = event.data.get('data')
        if pack_list[0] == '0xc0':
            if pack_list[5] == '0xad':
                if dongleattr.get_network_mode() == 'enable':
                    data_obj = {'status':'OK', 'data': "enable", 'type': 'zigbee_network'}
                    data_str = {'data': json.dumps(data_obj)}
                else:
                    data_obj = {'status':'OK', 'data': "disable", 'type': 'zigbee_network'}
                    data_str = {'data': json.dumps(data_obj)}
                hass.services.call('poly_mqtt', 'pub_data', data_str)       
            elif pack_list[5] == '0xa3':
                # '0xc0', '0x0', '0x0', '0x0', '0x2', '0xa3', '0xf', '0x6e'
                if dongleattr.get_mode() == 'channel':
                    channel = pack_list[6].replace('0x', '')
                    dongleattr.set_channel(int(channel, 16))
                    get_dongle_conf_net_info_h()
                elif dongleattr.get_mode() == 'conf_high':
                    net = pack_list[6].replace('0x', '')
                    dongleattr.set_net_high(net)  
                    get_dongle_conf_net_info_l()
                elif dongleattr.get_mode() == 'conf_low':
                    net = pack_list[6].replace('0x', '')
                    dongleattr.set_net_low(net) 
                    dongleattr.set_mode('channel')
                    data_obj = {'status':'OK', 'data': dongleattr.get_dongle_conf(), 'type': 'get_dongle_attr'}
                    data_str = {'data': json.dumps(data_obj)}
                    hass.services.call('poly_mqtt', 'pub_data', data_str)
            elif pack_list[4] == '0x1' and pack_list[5] == '0x44':
                # '0xc0', '0x0', '0x0', '0x0', '0x1', '0x44', '0x85' 
                data_obj = {'status':'OK', 'data': "", 'type': 'edit_dongle'}
                data_str = {'data': json.dumps(data_obj)}
                hass.services.call('poly_mqtt', 'pub_data', data_str)
                
        if pack_list[0] == '0xa0' and len(pack_list) > 8 and pack_list[8] == '0x7a':
            """Smart Device Into Net"""
            if pack_list[5] == '0x0':
                # 0xa0 0xc8 0xe 0xf7 0x4 0x0 0xe 0xf7 0x7a 0x36
                friendly_name = '插座'
                platform = 'polysocket'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'socket' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': 'switch', 'entity_id': 'switch.socket' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                name_mgr = FriendlyNameManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, 'switch', data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name, "device_type": platform}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x30':
                # 0xa0', '0xc6', '0x4', '0xa0', '0x4', '0x30', '0x4', '0xa0', '0x7a', '0x5b
                friendly_name = '一路零火灯'
                component = 'light'
                platform = 'polylnlight'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'lnlight' + mac.replace('#', '')}}, 'platform': 'polylnlight'}
                pack = {'plugin_type': component, 'entity_id': 'light.lnlight' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                name_mgr = FriendlyNameManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device', 'device_type': platform}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x31':
                # 0xa0', '0xc6', '0x4', '0xa0', '0x4', '0x31', '0x4', '0xa0', '0x7a', '0x5b
                friendly_name = '二路零火灯'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'lnlight' + mac.replace('#', '')}}, 'platform': 'polylnlight2'}
                pack = {'plugin_type': 'light', 'entity_id': 'light.lnlight' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                name_mgr = FriendlyNameManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, 'light', data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr.edit_friendly_name(pack['entity_id'] + '1', friendly_name + '1')
                name_mgr.edit_friendly_name(pack['entity_id'] + '2', friendly_name + '2')
                data = {'entity_id': pack['entity_id'] + '1', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
                data = {'entity_id': pack['entity_id'] + '2', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x32':
                # 0xa0', '0xc6', '0x4', '0xa0', '0x4', '0x32', '0x4', '0xa0', '0x7a', '0x5b
                friendly_name = '三路零火灯'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'lnlight' + mac.replace('#', '')}}, 'platform': 'polylnlight3'}
                pack = {'plugin_type': 'light', 'entity_id': 'light.lnlight' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                name_mgr = FriendlyNameManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, 'light', data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr.edit_friendly_name(pack['entity_id'] + '1', friendly_name + '1')
                name_mgr.edit_friendly_name(pack['entity_id'] + '2', friendly_name + '2')
                name_mgr.edit_friendly_name(pack['entity_id'] + '3', friendly_name + '3')
                data = {'entity_id': pack['entity_id'] + '1', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
                data = {'entity_id': pack['entity_id'] + '2', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
                data = {'entity_id': pack['entity_id'] + '3', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x20':
                # 0xa0', '0xc6', '0x4', '0xa0', '0x4', '0x43', '0x4', '0xa0', '0x7a', '0x5b
                friendly_name = '一路单火灯'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'light' + mac.replace('#', '')}}, 'platform': 'polylight'}
                pack = {'plugin_type': 'light', 'entity_id': 'light.light' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                name_mgr = FriendlyNameManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, 'light', data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x21':
                # 0xa0', '0xc6', '0x4', '0xa0', '0x4', '0x43', '0x4', '0xa0', '0x7a', '0x5b
                friendly_name = '二路单火灯'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'light' + mac.replace('#', '')}}, 'platform': 'polylight2'}
                pack = {'plugin_type': 'light', 'entity_id': 'light.light' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                name_mgr = FriendlyNameManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, 'light', data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr.edit_friendly_name(pack['entity_id'] + '1', friendly_name + '1')
                name_mgr.edit_friendly_name(pack['entity_id'] + '2', friendly_name + '2')
                data = {'entity_id': pack['entity_id'] + '1', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
                data = {'entity_id': pack['entity_id'] + '2', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x22':
                # 0xa0', '0xc6', '0x4', '0xa0', '0x4', '0x43', '0x4', '0xa0', '0x7a', '0x5b
                friendly_name = '三路单火灯'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'light' + mac.replace('#', '')}}, 'platform': 'polylight3'}
                pack = {'plugin_type': 'light', 'entity_id': 'light.light' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                name_mgr = FriendlyNameManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, 'light', data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr.edit_friendly_name(pack['entity_id'] + '1', friendly_name + '1')
                name_mgr.edit_friendly_name(pack['entity_id'] + '2', friendly_name + '2')
                name_mgr.edit_friendly_name(pack['entity_id'] + '3', friendly_name + '3')
                data = {'entity_id': pack['entity_id'] + '1', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
                data = {'entity_id': pack['entity_id'] + '2', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
                data = {'entity_id': pack['entity_id'] + '3', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x43':
                # 0xa0', '0xc6', '0x4', '0xa0', '0x4', '0x43', '0x4', '0xa0', '0x7a', '0x5b
                friendly_name = '4键情景面板'
                component = 'binary_sensor'
                platform = 'polypanel4'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'panel4' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'binary_sensor.panel4' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                name_mgr = FriendlyNameManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, platform, {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name, 'device_type': 'polypanel4'}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x40':
                # 0xa0', '0xc6', '0x4', '0xa0', '0x4', '0x43', '0x4', '0xa0', '0x7a', '0x5b
                friendly_name = '门磁'
                component = 'binary_sensor'
                platform = 'polydoorsensor'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'door' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'binary_sensor.door' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                name_mgr = FriendlyNameManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name, 'device_type': platform}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x44':
                # 0xa0', '0xc6', '0x4', '0xa0', '0x4', '0x43', '0x4', '0xa0', '0x7a', '0x5b
                friendly_name = 'IO探测器'
                component = 'binary_sensor'
                platform = 'polyiosensor'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'pir' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'binary_sensor.io' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                name_mgr = FriendlyNameManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name, 'platform': platform}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x63':
                # 0xa0', '0xc6', '0x4', '0xa0', '0x4', '0x63', '0x4', '0xa0', '0x7a', '0x5b
                friendly_name = '二路强电窗帘'
                component = 'cover'
                platform = 'polysccurtain2'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'cover' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'cover.cover' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'] + '1', friendly_name + '1')
                name_mgr.edit_friendly_name(pack['entity_id'] + '2', friendly_name + '2')
                data = {'entity_id': pack['entity_id'] + '1', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
                data = {'entity_id': pack['entity_id'] + '2', 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0xb0':
                # 0xa0', '0xc6', '0x4', '0xa0', '0x4', '0xb0', '0x4', '0xa0', '0x7a', '0x5b
                friendly_name = '调光开关'
                component = 'light'
                platform = 'polydimlight'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'dimlight' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'light.dimlight' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)  
            elif pack_list[5] == '0x10':
                # '0xa0', '0xbe', '0x9', '0x7f', '0x4', '0x10', '0x9', '0x7f', '0x7a', '0x70' 
                friendly_name = 'Yodar背景音乐'
                component = 'media_player'
                platform = 'polyyodar_i3'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'yodar' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'media_player.yodar' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)   
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)  
            elif pack_list[5] == '0x1e':
                # '0xa0', '0xc6', '0x14', '0x42', '0x4', '0x1e', '0x14', '0x42', '0x7a', '0x6'
                friendly_name = '杜亚窗帘'
                component = 'cover'
                platform = 'polydooya'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'dooya' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'cover.dooya' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x5':
                # 0xa0', '0xd3', '0x10', '0x26', '0x4', '0x5', '0x10', '0x26', '0x7a', '0x8
                friendly_name = '一路干节点窗帘'
                component = 'cover'
                platform = 'polycurtain'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'curtain' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'cover.curtain' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj) 
            elif pack_list[5] == '0x14':
                # '0xa0', '0xd5', '0x52', '0x77', '0x4', '0x14', '0x52', '0x77', '0x7a', '0x1f'
                friendly_name = '耶鲁门锁'
                component = 'lock'
                platform = 'polyyale'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'lock' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'lock.lock' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj) 
            elif pack_list[5] == '0x12':
                # '0xa0', '0xcd', '0x13', '0xa9', '0x4', '0x12', '0x13', '0xa9', '0x7a', '0x1'
                friendly_name = '豪力士语音门锁'
                component = 'lock'
                platform = 'polyholishi'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'lock' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'lock.lock' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)                 
            elif pack_list[5] == '0xf3':
                # '0xa0', '0xcd', '0x13', '0xa9', '0x4', '0x12', '0x13', '0xa9', '0x7a', '0x1'
                friendly_name = 'LCD情景面板'
                component = 'binary_sensor'
                platform = 'polylcdpanel'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'panel' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'binary_sensor.panel' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj) 
            elif pack_list[5] == '0xf0':
                # '0xa0', '0xcd', '0x13', '0xa9', '0x4', '0x12', '0x13', '0xa9', '0x7a', '0x1'
                friendly_name = '夜灯'
                component = 'light'
                platform = 'polynightlight'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'light' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'light.light' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj) 
            elif pack_list[5] == '0xf1':
                # '0xa0', '0xcd', '0x13', '0xa9', '0x4', '0x12', '0x13', '0xa9', '0x7a', '0x1'
                friendly_name = '壁灯'
                component = 'light'
                platform = 'polywalllight'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'light' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'light.light' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x53':
                # '0xa0', '0xcf', '0x46', '0xb1', '0x4', '0x53', '0x46', '0xb1', '0x7a', '0x42'
                friendly_name = '温湿度传感器'
                component = 'sensor'
                platform = 'polythl'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'sensor' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'sensor.sensor' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'] + '1', '温度')
                name_mgr.edit_friendly_name(pack['entity_id'] + '2', '湿度')
                name_mgr.edit_friendly_name(pack['entity_id'] + '3', '亮度')
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x3':
                # '0xa0', '0xcd', '0x5d', '0x69', '0x4', '0x3', '0x5d', '0x69', '0x7a', '0x10'  
                friendly_name = '电话拨号器'
                component = 'switch'
                platform = 'polyphone'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'phone' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'switch.phone' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], '电话拨号器')
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x1':
                # '0xa0', '0xc8', '0x4b', '0x20', '0x4', '0x1', '0x4b', '0x20', '0x7a', '0x17'
                friendly_name = '二路干节点窗帘'
                component = 'cover'
                platform = 'polycurtain2'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'curtain' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'cover.curtain' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'] + '1', friendly_name + '1')
                name_mgr.edit_friendly_name(pack['entity_id'] + '2', friendly_name + '2')
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x3c':
                # '0xa0', '0xc9', '0x4', '0xa0', '0x4', '0x3e', '0x4', '0xa0', '0x7a', '0x29'
                friendly_name = '一路零火情景面板'
                component = 'light'
                platform = 'polyzfirepanel1'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'light' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'light.light' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x3d':
                # '0xa0', '0xc9', '0x4', '0xa0', '0x4', '0x3e', '0x4', '0xa0', '0x7a', '0x29'
                friendly_name = '二路零火情景面板'
                component = 'light'
                platform = 'polyzfirepanel2'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'light' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'light.light' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'] + '1', friendly_name + '1')
                name_mgr.edit_friendly_name(pack['entity_id'] + '2', friendly_name + '2')
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x3e':
                # '0xa0', '0xc9', '0x4', '0xa0', '0x4', '0x3e', '0x4', '0xa0', '0x7a', '0x29'
                friendly_name = '三路零火情景面板'
                component = 'light'
                platform = 'polyzfirepanel3'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'light' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'light.light' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'] + '1', friendly_name + '1')
                name_mgr.edit_friendly_name(pack['entity_id'] + '2', friendly_name + '2')
                name_mgr.edit_friendly_name(pack['entity_id'] + '3', friendly_name + '3')
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x24':
                # '0xa0', '0xc9', '0x4', '0xa0', '0x4', '0x3e', '0x4', '0xa0', '0x7a', '0x29'
                friendly_name = '一路单火情景面板'
                component = 'light'
                platform = 'polylightpanel'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'light' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'light.light' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x25':
                # '0xa0', '0xc9', '0x4', '0xa0', '0x4', '0x3e', '0x4', '0xa0', '0x7a', '0x29'
                friendly_name = '二路单火情景面板'
                component = 'light'
                platform = 'polylightpanel2'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'light' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'light.light' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'] + '1', friendly_name + '1')
                name_mgr.edit_friendly_name(pack['entity_id'] + '2', friendly_name + '2')
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x26':
                # '0xa0', '0xc9', '0x4', '0xa0', '0x4', '0x3e', '0x4', '0xa0', '0x7a', '0x29'
                friendly_name = '三路单火情景面板'
                component = 'light'
                platform = 'polylightpanel3'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'light' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'light.light' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'] + '1', friendly_name + '1')
                name_mgr.edit_friendly_name(pack['entity_id'] + '2', friendly_name + '2')
                name_mgr.edit_friendly_name(pack['entity_id'] + '3', friendly_name + '3')
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x60':
                # '0xa0', '0xc9', '0x4', '0xa0', '0x4', '0x3e', '0x4', '0xa0', '0x7a', '0x29'
                friendly_name = '警号'
                component = 'switch'
                platform = 'polywarsignal'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'warsignal' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'switch.warsignal' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x40':
                # '0xa0', '0xc9', '0x4', '0xa0', '0x4', '0x3e', '0x4', '0xa0', '0x7a', '0x29'
                friendly_name = '烟雾报警器'
                component = 'binary_sensor'
                platform = 'polysmokesensor'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'smokesensor' + mac.replace('#', '')}}, 'platform': platform}
                pack = {'plugin_type': component, 'entity_id': 'switch.smokesensor' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr = FriendlyNameManager(hass, config)
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
                notity_client_device_into_net(data_obj)
            elif pack_list[5] == '0x2':
                friendly_name = '红外转发器'
                component = 'remote'
                platform = 'polyremoteforward'
                mac = pack_list[6].replace('0x', '') + "#" + pack_list[7].replace('0x', '')
                data = {'devices': {mac: {'name': 'remote' + mac.replace('#', '')}}, 'platform': 'polyremoteforward'}
                pack = {'plugin_type': component, 'entity_id': 'remote.remote' + mac.replace('#', ''), 'plugin_info': data}
                mgr = DevicePluginManager(hass, config)
                name_mgr = FriendlyNameManager(hass, config)
                if mgr.add_plugin(pack):
                    discovery.load_platform(hass, component, data['platform'], {'name': data['devices'][mac]['name'], 'mac': mac})
                name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
                data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
                data_obj = {'status':'OK', 'data': data, 'type': 'add_device', 'device_type': platform}
                notity_client_device_into_net(data_obj)

            # reload core config and friendlyname is work 
            hass.services.call('homeassistant', 'reload_core_config')

    hass.bus.listen(EVENT_ZIGBEE_RECV, event_zigbee_msg_handle)

    def dongle_softsence_service(call):
        sence_id = call.data.get('id')
        data = [0x80, 0x00, 0xFF, 0xFF, 0x07, 0x44, 0xFF, 0xFF, 0x9C, 0xFF, 0xFF, 0x0D, 0xe3]
        data[-2] = int(sence_id)
        resu_crc = checkcrc.xorcrc_hex(data)
        data[-1] = resu_crc
        hass.services.call(POLY_ZIGBEE_DOMAIN, POLY_ZIGBEE_SERVICE, {"data": data})

    hass.services.async_register('gateway', 'trigger_dongle_softsence', dongle_softsence_service)
    
    """Device Plugin Manager Service
    """
    def cur_host_version_service(call):
        # debug | beta | release
        data_obj = {'status':'OK', 'data': {'version': CUR_VERSION}, 'type': 'cur_host_version'}
        notity_client_data(data_obj)

    def add_plugin_service(call):
        component = call.data.get('plugin_type')
        platform = call.data.get('platform')
        if component == 'sensor' and platform == 'weiguoair':
            macU = call.data.get('mac')
            mac = macU.lower()
            friendly_name = '威果'
            data = {'devices': {mac: {'name': component + mac}}, 'platform': platform}
            pack = {'plugin_type': component, 'entity_id': component + '.' + component + mac, 'plugin_info': data}
            mgr = DevicePluginManager(hass, config)
            if mgr.add_plugin(pack):
                discovery.load_platform(hass, component, data['platform'], \
										{'name': data['devices'][mac]['name'], 'mac': mac})
            name_mgr = FriendlyNameManager(hass, config)
            name_mgr.edit_friendly_name(pack['entity_id'] + '1', '温度')
            name_mgr.edit_friendly_name(pack['entity_id'] + '2', '湿度')
            name_mgr.edit_friendly_name(pack['entity_id'] + '3', 'pm25')
            name_mgr.edit_friendly_name(pack['entity_id'] + '4', 'co2')
            name_mgr.edit_friendly_name(pack['entity_id'] + '5', 'voc')
            data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
            data_obj = {'status': 'OK', 'data': data, 'type': 'add_device'}
            notity_client_device_into_net(data_obj)
        elif component == 'camera' and platform == 'polylecheng':
            devidU = call.data.get('devid')
            devid = devidU.lower()
            phone = call.data.get('phone')
            channelid = call.data.get('channelid')
            friendly_name = '乐橙'
            data = {'devices': {devid: {'name': component + devid, 'phone': phone, 'channelid': channelid}}, 'platform': platform}
            pack = {'plugin_type': component, 'entity_id': component + '.' + component + devid, 'plugin_info': data}
            mgr = DevicePluginManager(hass, config)
            if mgr.add_plugin(pack):
                discovery.load_platform(hass, component, data['platform'], \
										{'name': data['devices'][devid]['name'], 'devid': devid, 'phone': phone, 'channelid': channelid})
            name_mgr = FriendlyNameManager(hass, config)
            name_mgr.edit_friendly_name(pack['entity_id'], friendly_name)
            data = {'entity_id': pack['entity_id'], 'friendly_name': friendly_name}
            data_obj = {'status': 'OK', 'data': data, 'type': 'add_device'}
            notity_client_device_into_net(data_obj)

    def del_plugin_service(call):
        plug_id = call.data.get('entity_id')
        if isinstance(plug_id, list):
            for entity_id in plug_id:
                del_one_plugin(entity_id)
        if isinstance(plug_id, str):
            del_one_plugin(plug_id)

        # notify all clients
        data_obj = {'status':'OK', 'data': {}, 'type': 'del_plugin'}
        notity_client_data(data_obj)
        # restart homeassistant service
        hass.add_job(async_restart(hass))

    def del_one_plugin(entity_id):
        # delete device from configuration.yaml
        comp_mgr = DevicePluginManager(hass, config)
        comp_mgr.delete_plugin(entity_id)
        # delete device from groups.yaml
        group_mgr = GroupsManager(hass, config)
        group_mgr.del_group_device(entity_id)
        # delete device from customize.yaml
        name_mgr = FriendlyNameManager(hass, config)
        name_mgr.del_friendly_name(entity_id)

    # System Event Manager Service.
    def event_state_change_handler(call):
        entity_id = call.data.get('entity_id')
        if entity_id.split('.')[0] in CONTANT_SUPPORT:
            # state_json = {'entity_id': entity_id, 'state': new_state['state']}
            # data_obj = {'status':'OK', 'data': state_json, 'type': 'state_change'}
            # notity_client_data(data_obj)
            # publish new state for MQTT Server
            new_state = call.data.get('new_state').as_dict()
            msg = json.dumps(new_state, sort_keys=True, cls=JSONEncoder)
            json_msg = json.loads(msg)
            pub_obj = {'status':'OK', 'data': json_msg, 'type': 'state_change'}
            data_str = {'data': json.dumps(pub_obj)}
            hass.services.call('poly_mqtt', 'mqtt_pub_state_change', data_str)

    def event_ha_start_handler(call):
        data_obj = {'status':'OK', 'data': {}, 'type': 'polyhome_start'}
        notity_client_data(data_obj)

    def event_ha_stop_handler(call):
        data_obj = {'status':'OK', 'data': {}, 'type': 'polyhome_stop'}
        notity_client_data(data_obj)

    def publish_heart_beat_services(call):
        entity_id = call.data.get('entity_id')
        state = hass.states.get(entity_id).as_dict()
        # publish new state for MQTT Server
        msg = json.dumps(state, sort_keys=True, cls=JSONEncoder)
        pub_obj = {'status':'OK', 'data': json.loads(msg), 'type': 'heart_beat'}
        data_str = {'data': json.dumps(pub_obj)}
        hass.services.call('poly_mqtt', 'mqtt_pub_state_change', data_str)

    def gateway_register_service(call):
        friendly_name = '智能网关'
        data = {'entity_id': mac_util.get_uuid(hass.config.config_dir), 'friendly_name': friendly_name, 'device_type': 'gateway'}
        data_obj = {'status':'OK', 'data': data, 'type': 'add_device'}
        notity_client_device_into_net(data_obj)

    def get_all_automation_service(call):
        try:
            auto_mgr = AutomationsManager(hass, config)
            data = auto_mgr.get_automations()
            data_obj = {'status':'OK', 'data': data, 'type': 'all_automations'}
            data_str = {'data': json.dumps(data_obj)}
            hass.services.call('poly_mqtt', 'pub_data', data_str)
        except Exception as e:
            data_obj = {'status':'ERROR', 'data': {'msg': e}, 'type': 'all_automations'}
            data_str = {'data': json.dumps(data_obj)}
            hass.services.call('poly_mqtt', 'pub_data', data_str)
    
    def edit_automation_service(call):
        try:
            data = call.data
            if data is None:
                data_obj = {'status':'ERROR', 'data': {'msg': 'data is Null'}, 'type': 'edit_automation'}
                data_str = {'data': json.dumps(data_obj)}
                hass.services.call('poly_mqtt', 'pub_data', data_str)
                return
            auto_mgr = AutomationsManager(hass, config)
            auto_mgr.edit_automation(data)
            data_obj = {'status':'OK', 'data': {}, 'type': 'edit_automation'}
            data_str = {'data': json.dumps(data_obj)}
            hass.add_job(async_auto_reload(hass, data_str))
        except Exception as e:
            data_obj = {'status':'ERROR', 'data': {'msg': e}, 'type': 'edit_automation'}
            data_str = {'data': json.dumps(data_obj)}
            hass.add_job(async_auto_reload(hass, data_str))
        
    def delete_automation_service(call):
        auto_id = call.data.get('id')
        auto_mgr = AutomationsManager(hass, config)
        auto_mgr.delete_automation(auto_id)
        data_obj = {'status':'OK', 'data': {}, 'type': 'delete_automation'}
        data_str = {'data': json.dumps(data_obj)}
        hass.add_job(async_auto_reload(hass, data_str))
        
    def get_automation_by_id_service(call):
        auto_id = call.data.get('id')
        auto_mgr = AutomationsManager(hass, config)
        auto_detail = auto_mgr.get_automation_by_id(auto_id)
        data_obj = {'status':'OK', 'data': auto_detail, 'type': 'automation_by_id'}
        data_str = {'data': json.dumps(data_obj)}
        hass.services.call('poly_mqtt', 'pub_data', data_str)

    def trigger_automation_service(call):
        auto_id = call.data.get('id')
        auto_id = str(auto_id)
        auto_mgr = AutomationsManager(hass, config)
        auto_mgr.trigger_automation(auto_id)
        data_obj = {'status':'OK', 'data': '', 'type': 'trigger_automation'}
        data_str = {'data': json.dumps(data_obj)}
        hass.services.call('poly_mqtt', 'pub_data', data_str)
    
    def edit_automation_name_service(call):
        try:
            auto_id = call.data['id']
            friendly_name = call.data['name']
            auto_mgr = AutomationsManager(hass, config)
            auto_mgr.edit_automation_name(auto_id, friendly_name)
            data_obj = {'status':'OK', 'data': "", 'type': 'edit_automation_name'}
            data_str = {'data': json.dumps(data_obj)}
            hass.add_job(async_auto_reload(hass, data_str))
        except Exception as e:
            data_obj = {'status':'OK', 'data': e, 'type': 'edit_automation_name'}
            data_str = {'data': json.dumps(data_obj)}
            hass.add_job(async_auto_reload(hass, data_str))
                   
    def event_publish_message_handler(call):
        data_str = call.data
        hass.services.call('poly_mqtt', 'pub_data', data_str)

    hass.bus.listen('event_mqtt_publish', event_publish_message_handler)

    # Services
    hass.services.register('gateway', 'get_all_automation', get_all_automation_service)
    hass.services.register('gateway', 'edit_automation', edit_automation_service)
    hass.services.register('gateway', 'delete_automation', delete_automation_service)
    hass.services.register('gateway', 'get_automation_by_id', get_automation_by_id_service)
    hass.services.register('gateway', 'trigger_automation', trigger_automation_service)
    hass.services.register('gateway', 'edit_automation_name', edit_automation_name_service)

    hass.services.register('gateway', 'get_states', get_states_service)
    hass.services.register('gateway', 'edit_friendlyname', edit_friendlyname_service)

    hass.services.register('gateway', 'get_groups', get_groups_service)
    hass.services.register('gateway', 'edit_group', edit_group_service)
    hass.services.register('gateway', 'delete_group', delete_group_service)
    hass.services.register('gateway', 'device_edit_group', device_edit_group_service)

    hass.services.register('gateway', 'zigbee_network', zigbee_network_service)
    hass.services.register('gateway', 'edit_dongle_conf', edit_dongle_conf_service)
    hass.services.register('gateway', 'get_dongle_conf', get_dongle_conf_service)

    hass.services.register('gateway', 'cur_host_version', cur_host_version_service)
    hass.services.register('gateway', 'add_plugin', add_plugin_service)
    hass.services.register('gateway', 'del_plugin', del_plugin_service)

    hass.services.register('gateway', 'publish_heart_beat', publish_heart_beat_services)
    hass.services.register('gateway', 'gateway_register', gateway_register_service)

    # listen some system events
    hass.bus.listen('state_changed', event_state_change_handler)
    hass.bus.listen('homeassistant_start', event_ha_start_handler)
    hass.bus.listen('homeassistant_stop', event_ha_stop_handler)
    

    # setup zigbee dongle component /dev/tty.usbserial
    zigbee_conf = {'poly_zigbee': {'baudbrate': 57600, 'uartpath': UART_PATH}}
    Setup.setup_component(hass, 'poly_zigbee', zigbee_conf)
    Setup.setup_component(hass, 'poly_mqtt', config)
    Setup.setup_component(hass, 'poly_zeroconf')

    def trigger_auto_by_name_service(call):
        name = call.data.get('name')
        for state in hass.states.async_all():
            entity_id = state.as_dict()['entity_id']
            id_domain = entity_id.split('.')[0]
            if id_domain not in 'automation':
                continue
            if name in state.as_dict()['attributes']['friendly_name']:
                data = {"entity_id": state.as_dict()['entity_id']}
                hass.services.call('automation', 'trigger', data)

    hass.services.register('gateway', 'trigger_auto_by_name', trigger_auto_by_name_service)    
    
    def trigger_light_by_name_service(call):
        action = call.data.get('action')
        name = call.data.get('name')
        for state in hass.states.async_all():
            entity_id = state.as_dict()['entity_id']
            id_domain = entity_id.split('.')[0]
            if id_domain not in 'light':
                continue
            if name in state.as_dict()['attributes']['friendly_name']:
                data = {"entity_id": state.as_dict()['entity_id']}
                hass.services.call('light', action, data)

    hass.services.register('gateway', 'trigger_light_by_name', trigger_light_by_name_service)
    
    return True


class JSONEncoder(json.JSONEncoder):
    """JSONEncoder that supports Home Assistant objects."""
    def default(self, o):
        """Convert Home Assistant objects.
        Hand other objects to the original method.
        """
        if isinstance(o, datetime):
            return str(round(datetime.timestamp(o)))
        elif isinstance(o, set):
            return list(o)
        elif hasattr(o, 'as_dict'):
            return o.as_dict()

        try:
            return json.JSONEncoder.default(self, o)
        except TypeError:
            # If the JSON serializer couldn't serialize it
            # it might be a generator, convert it to a list
            try:
                return [self.default(child_obj)
                        for child_obj in o]
            except TypeError:
                # Ok, we're lost, cause the original error
                return json.JSONEncoder.default(self, o)

@asyncio.coroutine
def async_auto_reload(hass, data):
    """Reload the automation from config.
    Returns a coroutine object.
    """
    yield from hass.services.async_call('homeassistant', 'reload_core_config')
    yield from hass.services.async_call('automation', 'reload')
    hass.bus.fire('event_mqtt_publish', data)

@asyncio.coroutine
def async_reload(hass):
    return hass.services.async_call('group', 'reload')

@asyncio.coroutine
def async_restart(hass):
    return hass.services.async_call('homeassistant', 'restart')

@asyncio.coroutine
def async_reload_core_conf(hass):
    return hass.services.async_call('homeassistant', 'reload_core_config')