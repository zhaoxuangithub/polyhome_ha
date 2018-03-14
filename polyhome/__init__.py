#!/usr/bin/env python3
# -*- coding: utf-8 -*-import asyncio
import os
import time
import json

from datetime import datetime
from polyhome.util.yaml import load_yaml, dump
from polyhome.helper.const import CONTANT_SUPPORT

"""
Group Manager Class
"""
class GroupsManager(object):
    """Groups Manager"""
    def __init__(self, hass, config):
        self._hass = hass
        self._config = config
        self._filepath = self._hass.config.path('groups.yaml')
        
    def get_groups(self):
        """return All groups"""
        all_groups = []
        for state in self._hass.states.async_all():
            group_id = state.as_dict()['entity_id']
            if 'group.all_' in group_id:
                continue
            if 'group.' in group_id:
                dev_str = json.dumps(state, sort_keys=True, cls=JSONEncoder)
                dev_obj = json.loads(dev_str)
                del dev_obj['state']
                del dev_obj['last_updated']
                del dev_obj['last_changed']
                del dev_obj['attributes']['assumed_state']
                del dev_obj['attributes']['hidden']
                del dev_obj['attributes']['order']
                del dev_obj['attributes']['view']
                all_groups.append(dev_obj)

        return all_groups

    def edit_group(self, group_id, attr, name):
        """Edit id friendlyname"""
        current = self._read_config()
        self._write_value(current, group_id, attr, name)
        self._write(self._filepath, current)

    def delete_group(self, group_id):
        """Delete group by id"""
        current = self._read_config()
        self._delete_value_group(current, group_id)
        self._write(self._filepath, current)

    def add_group_device(self, group_id, entity_id):
        """Add id friendlyname"""
        if 'group.' in group_id:
            group_id = group_id.replace('group.', '')
        current = self._read_config()
        if current.get(group_id, None) is None:
            return
        current[group_id]['entities'].append(entity_id)
        self._write(self._filepath, current)

    def del_group_device(self, entity_id):
        """Delete id friendlyname"""
        current = self._read_config()
        for group in current.values():
            if entity_id in group['entities']:
                group['entities'].remove(entity_id)
        self._write(self._filepath, current)

    def _read_config(self):
        """Read the config."""
        current = self._read(self._filepath)
        if not current:
            current = {}
        return current

    def _read(self, path):
        """Read YAML helper."""
        if not os.path.isfile(path):
            return None
        return load_yaml(path)

    def _write_value(self, groups, group_id, entities, name):
        """Set value."""    
        groups[group_id] = {}
        groups[group_id]['name'] = name
        groups[group_id]['view'] = True
        groups[group_id]['entities'] = entities
        
    def _write(self, path, data):
        """Write YAML helper."""
        # Do it before opening file. If dump causes error it will now not
        # truncate the file.
        data = dump(data)
        with open(path, 'w', encoding='utf-8') as outfile:
            outfile.write(data)

    def _delete_value_group(self, data, config_key):
        """delete value"""
        value = self._get_value(data, config_key)
        if value is not None:
            del data[config_key]

    def _get_value(self, data, config_key):
        """Get value."""
        for k, group_id in data.items():
            if k == config_key:
                return group_id
        return None


"""
Device Manager Class
"""
class DeviceManager(object):
    """All States Manager"""

    def __init__(self, hass, config):
        self._hass = hass
        self._config = config

    def get_devices(self):
        """return All entitys device and states"""
        all_states = []
        for state in self._hass.states.async_all():
            entity_id = state.as_dict()['entity_id']
            id_domain = entity_id.split('.')[0]
            id_name = entity_id.split('.')[1]
            if id_domain not in CONTANT_SUPPORT:
                continue
            
            json_data = []
            for item in self._config[id_domain]:
                json_data.append({
                    'devices': item['devices'],
                    'platform': item['platform']
                })
            dev_str = json.dumps(state, sort_keys=True, cls=JSONEncoder)
            dev_obj = json.loads(dev_str)
            del dev_obj['last_changed']
            del dev_obj['last_updated']
            if dev_obj['attributes'].get('icon', None) is not None:
                del dev_obj['attributes']['icon']
            dev_obj['platform'] = dev_obj['attributes']['platform']
            if dev_obj['attributes'].get('platform', None) is not None:
                del dev_obj['attributes']['platform']
            dev_obj['group'] = self.get_group(entity_id)
            # print(dev_obj)
            all_states.append(dev_obj)
            
        return all_states
    
    def get_group(self, entity_id):
        """get group"""
        for state in self._hass.states.async_all():
            group_id = state.as_dict()['entity_id']
            if 'group.all_' in group_id:
                continue
            if 'group.' in group_id:
                if entity_id in state.as_dict()['attributes']['entity_id']:
                    return  state.as_dict()['attributes']['friendly_name']        
        
        return 'unknown'

    def _has_device(self, devices, name):
        for item in devices:
            if self._has_name(item['devices'], name):
                return item['platform']
        return None

    def _has_name(self, arry_dict, name):
        for k, v in arry_dict.items():
            if v['name'] in name:
                return True
        return False
    
    def get_device_by_type(self, value_key):
        if value_key not in CONTANT_SUPPORT:
            return None
        current = self._read(self._hass.config.path('configuration.yaml'))
        if not current:
            current = []
        data = self._get_value(current, value_key)
        return data

    def edit_device_by_type(self, value_key, value_data):
        if value_key not in CONTANT_SUPPORT:
            return None 
        current = self._read(self._hass.config.path('configuration.yaml'))
        if not current:
            current = []
        # set value
        value = self._get_value(current, value_key)
        if value is None:
            value = {value_key: value_data}
            current.append(value)
        value[value_key] = value_data
        self._write(self._hass.config.path('configuration.yaml'), current)

    def _read_config(self, filename):
        """Read the config."""
        current = self._read(self._hass.config.path(filename))
        if not current:
            current = []
        return current

    def _read(self, path):
        """Read YAML helper."""
        if not os.path.isfile(path):
            return None
        return load_yaml(path)
    
    def _write_friendlyname(self, data, config_key, new_value):
        """Set value."""
        value = self._get_value(data, config_key)
        if value is None:
            data[config_key] = {"friendly_name":""}
        data[config_key]['friendly_name'] = new_value 

    def _write_value(self, data, config_key, new_value):
        """Set value."""
        value = self._get_value(data, config_key)
        if value is None:
            value = {config_key: new_value}
            data.append(value)
        value['friendly_name'] = new_value

    def _write(self, path, data):
        """Write YAML helper."""
        data = dump(data)
        with open(path, 'w', encoding='utf-8') as outfile:
            outfile.write(data)

    def _delete_value(self, data, config_key):
        """delete value"""
        value = self._get_value(data, config_key)
        if value is not None:
            for node in data:
                if node['friendly_name'] == config_key:
                    data.remove(node)

    def _get_value(self, data, config_key):
        """Get value."""
        for k, v in data.items():
            if k == config_key:
                return v    
        return None


"""
Friendly Name Manager
"""
class FriendlyNameManager(object):
    """All FriendlyName Manager."""
    
    def __init__(self, hass, config):
        """init"""
        self._hass = hass
        self._config = config
        self._path = hass.config.path('customize.yaml')

    def edit_friendly_name(self, id, name):
        """Edit id friendlyname"""
        current = self._read_config()
        self._write_friendly_name(current, id, name)
        self._write(self._path, current)

    def del_friendly_name(self, name_id):
        """Edit id friendlyname"""
        current = self._read_config()
        self._delete_value(current, name_id)
        self._write(self._path, current)

    def get_friendly_name(self, name_id):
        """Get entity_id name from customize.yaml"""
        current = self._read_config()
        name = current.get(name_id, None)
        return name

    def _read_config(self):
        """Read the config."""
        current = self._read(self._path)
        if not current:
            current = {}
        return current
    
    def _write(self, path, data):
        """Write YAML helper."""
        data = dump(data)
        with open(path, 'w', encoding='utf-8') as outfile:
            outfile.write(data)
    
    def _read(self, path):
        """Read YAML helper."""
        if not os.path.isfile(path):
            return None
        return load_yaml(path)
    
    def _write_friendly_name(self, current, key, alias):
        """Set value."""        
        name = {key: {'friendly_name': alias}}
        current.update(name)
    
    def _delete_value(self, data, key):
        """Delete value."""
        value = self._get_value(data, key)
        if value is not None:
            del data[key]

    def _get_value(self, data, config_key):
        """Get value."""
        for k, name in enumerate(data):
            if k == config_key:
                return name
        return None


"""
Automation Manager Class
"""
class AutomationsManager(object):
    """All Automations Manager."""

    def __init__(self, hass, config):
        self._hass = hass
        self._config = config
        self._filepath = self._hass.config.path('automations.yaml')

    def get_automations(self):
        all_auto = []
        for state in self._hass.states.async_all():
            entity_id = state.as_dict()['entity_id']
            id_domain = entity_id.split('.')[0]
            if id_domain not in 'automation':
                continue
            dev_str = json.dumps(state, sort_keys=True, cls=JSONEncoder)
            dev_obj = json.loads(dev_str)
            all_auto.append(dev_obj)
        return all_auto

    def edit_automation(self, data):
        """edit automation by id.
        """
        current = self._read_config()
        auto_id = data.get('id', None)
        alias = data['alias']
        if auto_id is None:
            auto_id = str(int(time.time()))
        else:    
            total_id = 'automation.' + auto_id
            if total_id not in self._hass.states.entity_ids():
                return
        # edit sence alias
        self.edit_automation_name(auto_id, alias)
        self.check_data(data)
        # json.loads(data)['alias'] = auto_id
        self._write_value(self._hass, current, auto_id, data)
        self._write(self._filepath, current)

    def delete_automation(self, auto_id):
        current = self._read_config()
        self._delete_value(self._hass, current, auto_id)
        self._write(self._filepath, current)

    def get_automation_by_id(self, id):
        current = self._read_config()
        auto_detail = self._get_value(self._hass, current, id)
        name_mgr = FriendlyNameManager(self._hass, self._config)
        auto_id = 'automation.' + auto_detail['id']
        auto_alias = name_mgr.get_friendly_name(auto_id)
        if auto_alias is not None:
            auto_detail['alias'] = auto_alias['friendly_name']

        return auto_detail

    def trigger_automation(self, auto_id):
        if 'automation.' in auto_id:
            auto_id = auto_id.replace('automation.', '')
        current = self._read_config()
        for auto in current:
            if auto['id'] == auto_id:
                data = {"entity_id": 'automation.' + auto['alias']}
                self._hass.services.call('automation', 'trigger', data)
    
    def edit_automation_name(self, auto_id, name):
        auto_id = 'automation.' + auto_id
        name_mgr = FriendlyNameManager(self._hass, self._config)
        name_mgr.edit_friendly_name(auto_id, name)

    def check_data(self, data):
        dict_data = dict(data)
        for action in dict_data['action']:
            if 'data' in action.keys():
                del action['data']['friendly_name']

    def _read_config(self):
        """Read the config.
        """
        current = self._read(self._filepath)
        if not current:
            current = []
        return current

    def _read(self, path):
        """Read YAML helper."""
        if not os.path.isfile(path):
            return None

        return load_yaml(path)

    def _write(self, path, data):
        """Write YAML helper."""
        data = dump(data)
        with open(path, 'w', encoding='utf-8') as outfile:
            outfile.write(data)

    def _get_value(self, hass, data, config_key):
        """Get value."""
        return next(
            (val for val in data if val.get('id') == config_key), None)

    def _write_value(self, hass, data, config_key, new_value):
        """Set value."""
        value = self._get_value(hass, data, config_key)
        if value is None:
            value = {'id': config_key}
            data.append(value)
        value.update(new_value)
        value['alias'] = config_key

    def _delete_value(self, hass, data, config_key):
        value = self._get_value(hass, data, config_key)
        if value is not None:
            for node in data:
                if node['id'] == config_key:
                    data.remove(node)


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


class DevicePluginManager(object):
    """Device Manager"""
    def __init__(self, hass, config):
        self._hass = hass
        self._config = config

    def _write(self, path, data):
        """Write YAML"""
        data = dump(data)
        with open(path, 'w', encoding='utf-8') as outfile:
            outfile.write(data)

    def _read(self, path):
        """Read YAML helper."""
        if not os.path.isfile(path):
            return None
        return load_yaml(path)

    def _write_value(self, data, entity_id, content):
        """Set value."""
        value = self._get_value(entity_id)
        if value is None:
            data.append(content)
            return True
        return False

    def _delete_value(self, data, plugin_name):
        """delete value"""
        for entity in data:
            if 'devices' in entity:
                for device in entity['devices'].values():
                    if 'name' in device and device['name'] in plugin_name:
                        data.remove(entity)
        return data

    def _get_value(self, entity_id):
        """Get value."""
        for state in self._hass.states.async_all():
            state_dict = state.as_dict()
            if entity_id in state_dict['entity_id']:
                return entity_id
        return None

    def _read_config(self, filename):
        """Read the config."""
        current = self._read(self._hass.config.path(filename))
        if not current:
            current = []
        return current

    def add_plugin(self, plugin_data):
        # 1.检查config中是否有该插件
        if 'plugin_type' not in plugin_data.keys():
            return
        plugin_type = plugin_data['plugin_type'] 
        current = self._read_config(plugin_type + '.yaml')
        entity_id = plugin_data['entity_id']
        ret = self._write_value(current, entity_id, plugin_data['plugin_info'])
        if ret:
            self._write(self._hass.config.path(plugin_type + '.yaml'), current)
        return ret

    def delete_plugin(self, entity_id):
        """delete plugin from customize.yaml"""
        plugin_type = entity_id.split('.')[0]
        plugin_name = entity_id.split('.')[1]
        if plugin_type not in self._config.keys():
            return
        # 删除指定插件值
        current = self._read_config(plugin_type + '.yaml')
        self._delete_value(current, plugin_name)
        self._write(self._hass.config.path(plugin_type + '.yaml'), current)