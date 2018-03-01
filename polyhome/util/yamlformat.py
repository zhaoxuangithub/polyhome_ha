import os
import logging
import yaml
import json

from homeassistant.util import dt as date_util, location as loc_util
from polyhome.helper.contant import DEFAULT_CONF_CONTENT, DEFAULT_EXISTS_FILE, POLY_MQTT_CONFIG, POLY_HOMEASSISTANT_CONFIG
from homeassistant.const import (
    CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME, CONF_PACKAGES, CONF_UNIT_SYSTEM,
    CONF_TIME_ZONE, CONF_ELEVATION, CONF_UNIT_SYSTEM_METRIC,
    CONF_UNIT_SYSTEM_IMPERIAL, CONF_TEMPERATURE_UNIT, TEMP_CELSIUS, CONF_CUSTOMIZE, CONF_CUSTOMIZE_DOMAIN, CONF_CUSTOMIZE_GLOB,
    CONF_WHITELIST_EXTERNAL_DIRS)

_LOGGER = logging.getLogger(__name__)


class FormatData(object):
    """format module (1) yaml to json (2) json to aml"""
    def __init__(self):
        self._is_debug = False
        self._save_dir = os.getcwd() + '/'

    def set_yaml_save_path(self, dirpath, isdebug=False):
        """save file"""
        if isdebug:
            self._save_dir = dirpath + '/debug/'
            if not os.path.exists(self._save_dir):
                os.mkdir(self._save_dir)
        else:
            self._save_dir = dirpath + '/'
        self._is_debug = isdebug
        _LOGGER.info('CONF PATH: ' + self._save_dir)

    def is_debug(self):
        return self._is_debug

    def set_default_conf_content(self):
        for filename in DEFAULT_EXISTS_FILE:
            open(self._save_dir + filename, 'wt')
        try:
            # write default config text
            with open(self._save_dir + 'configuration.yaml', 'a') as config_file:
                config_file.write(DEFAULT_CONF_CONTENT)
            # write default automations text
            with open(self._save_dir + 'automations.yaml', 'wt') as config_file:
                config_file.write("[]")
        except IOError:
            _LOGGER.error("Unable to create default configuration file")   

    # set mqtt default value
    def set_default_mqtt_config(self, id):
        try:
            info = {attr: default for attr, default, _, _ in POLY_MQTT_CONFIG}
            # write default config text
            with open(self._save_dir + 'configuration.yaml', 'a') as config_file:
                config_file.write("mqtt:\n")
                for attr, _, _, description in POLY_MQTT_CONFIG:
                    if attr == 'client_id':
                        info[attr] = id
                    if info[attr] is None:
                        continue
                    elif description:
                        config_file.write("  # {}\n".format(description))
                    config_file.write("  {}: {}\n".format(attr, info[attr]))
        except IOError:
            _LOGGER.error("Unable to create default configuration file")

    def set_homeassistant_config(self):
        
        info = {attr: default for attr, default, _, _ in POLY_HOMEASSISTANT_CONFIG}

        location_info = True and loc_util.detect_location_info()
        # print(location_info)
        if location_info:
            if location_info.use_metric:
                info[CONF_UNIT_SYSTEM] = CONF_UNIT_SYSTEM_METRIC
            else:
                info[CONF_UNIT_SYSTEM] = CONF_UNIT_SYSTEM_IMPERIAL

            for attr, default, prop, _ in POLY_HOMEASSISTANT_CONFIG:
                if prop is None:
                    continue
                info[attr] = getattr(location_info, prop) or default

            if location_info.latitude and location_info.longitude:
                info[CONF_ELEVATION] = loc_util.elevation(
                    location_info.latitude, location_info.longitude)
        try:
            # write default config text
            with open(self._save_dir + 'configuration.yaml', 'wt') as config_file:
                config_file.write("homeassistant:\n")
                for attr, _, _, description in POLY_HOMEASSISTANT_CONFIG:
                    if info[attr] is None:
                        continue
                    elif description:
                        config_file.write("  # {}\n".format(description))
                    config_file.write("  {}: {}\n".format(attr, info[attr]))
        except IOError:
            _LOGGER.error("Unable to create default configuration file")
        finally:
            config_file.close()    
       
    def get_config_path(self):
        return self._save_dir

    def json_to_yaml(self, file_name, data):
        """The params is json data return OK or ERROR str."""

        result = 'ERROR'
        
        # 检查是否为str
        if not isinstance(data, str):
            print("[ERROR]: data is not json str!")
            return result

        # TODO 增加一个文件夹判断 没有的话创建
        if not os.path.exists(self._save_dir):
            os.mkdir(self._save_dir)

        try:
            new_data = json.loads(data)
            # key homeassistant表示是否为config文件
            if isinstance(new_data, dict) and new_data['homeassistant'] is not None:
                new_data['homeassistant']['customize'] = "!include customize.yaml"
                new_data['group'] = "!include groups.yaml"
                new_data['automation'] = "!include automations.yaml"
                new_data['script'] = "!include scripts.yaml"
            # print('=========================')
            # print(new_data)
            # print('=========================')
            # data = dump(new_data)
            # with open(self._save_dir + file_name, 'w', encoding='utf-8') as outfile:
            #     outfile.write(data)

            # 将json文件存入yaml文件中
            with open(self._save_dir + file_name, 'w') as outfile:
                yaml.safe_dump(new_data, outfile,
                          default_flow_style=False,
                          default_style='',
                          encoding='utf-8',
                          width=50,
                          allow_unicode=True)

            # 格式化!include为标准语法
            with open(self._save_dir + file_name, 'r+', newline='') as outfile:
                s = outfile.read()
                # 将指针移到起始位置
                outfile.seek(0, 0)
                # 干掉空格和null
                outfile.write(s.replace("'", '').replace(': null', ':').replace('{','').replace('}',''))
                # 干掉最后生成的一行r: null
                current_line = outfile.tell() - 1
                outfile.truncate(current_line)
        except yaml.YAMLError as e:
            print("[ERROR-YAML]:", e)
            return result
        except IOError as e:
            print("[ERROR-IO]:", e)
            return result
        except Exception as e:
            print("[ERROR]:", e)
            return result

        return 'DONE'
    
    def yaml_to_json(self, file_name):
        """The params is yaml file name return a json file and json data."""
        result = 'ERROR'
        # 检查是否为yaml文件
        extension = os.path.splitext(file_name)[1].lstrip('.')

        if not isinstance(file_name, str):
            print("[ERROR]: file_name is not str!")
            return result
        elif extension not in ('yaml', 'yml'):
            print("[ERROR]: file_name is not yaml or yml!")
            return result
        
        if not os.path.exists(self._save_dir):
            os.mkdir(self._save_dir)

        try:
            yaml_loaded = None
            # 转换为dict
            with open(self._save_dir + file_name, 'r') as outfile:
                yaml_loaded = yaml.load(outfile, Loader)

            if isinstance(yaml_loaded, dict) and yaml_loaded['homeassistant'] is not None:
                yaml_loaded['homeassistant']['customize'] = "!include customize.yaml"
                yaml_loaded['group'] = "!include groups.yaml"
                yaml_loaded['automation'] = "!include automations.yaml"
                yaml_loaded['script'] = "!include scripts.yaml"
                yaml_loaded['switch'] = "!include switch.yaml"
                yaml_loaded['light'] = "!include light.yaml"
                yaml_loaded['binary_sensor'] = "!include binary_sensor.yaml"
                yaml_loaded['cover'] = "!include cover.yaml"
                yaml_loaded['lock'] = "!include lock.yaml"
                yaml_loaded['sensor'] = "!include sensor.yaml"
                yaml_loaded['media_player'] = "!include media_player.yaml"
            new_json_str = json.dumps(yaml_loaded)
        except IOError as e:
          print("[ERROR]:", e)
          return result
        except Exception as e:
            print("[ERROR]:", e)
            return result

        return new_json_str
    
    def write_ha_conf_include(self):
        try:
            # write default include config text
            with open(self._save_dir + 'configuration.yaml', 'a') as config_file:
                config_file.write("automation: !include automations.yaml\n")
                config_file.write("group: !include groups.yaml\n")
                config_file.write("script: !include scripts.yaml\n")
                config_file.write("switch: !include switch.yaml")
                config_file.write("light: !include light.yaml")
                config_file.write("binary_sensor: !include binary_sonsor.yaml")
                config_file.write("sensor: !include sensor.yaml")
                config_file.write("lock: !include lock.yaml")
                config_file.write("cover: !include cover.yaml")
                config_file.write("media_player: !include media_player.yaml")
        except IOError:
            _LOGGER.error("Unable to create default configuration file")
        finally:
            config_file.close() 

    def write_ha_conf(self):
        info = {attr: default for attr, default, _, _ in POLY_HOMEASSISTANT_CONFIG}

        location_info = True and loc_util.detect_location_info()
        # print(location_info)
        if location_info:
            if location_info.use_metric:
                info[CONF_UNIT_SYSTEM] = CONF_UNIT_SYSTEM_METRIC
            else:
                info[CONF_UNIT_SYSTEM] = CONF_UNIT_SYSTEM_IMPERIAL

            for attr, default, prop, _ in POLY_HOMEASSISTANT_CONFIG:
                if prop is None:
                    continue
                info[attr] = getattr(location_info, prop) or default

            if location_info.latitude and location_info.longitude:
                info[CONF_ELEVATION] = loc_util.elevation(
                    location_info.latitude, location_info.longitude)
        try:
            # write default config text
            with open(self._save_dir + 'configuration.yaml', 'wt') as config_file:
                config_file.write("homeassistant:\n")
                for attr, _, _, description in POLY_HOMEASSISTANT_CONFIG:
                    if info[attr] is None:
                        continue
                    elif description:
                        config_file.write("  # {}\n".format(description))
                    config_file.write("  {}: {}\n".format(attr, info[attr]))
        except IOError:
            _LOGGER.error("Unable to create default configuration file")
        finally:
            config_file.close()


class Loader(yaml.Loader):
    """解析!include语法"""
    def __init__(self, stream):
        self._root = os.path.split(stream.name)[0]
        super(Loader, self).__init__(stream)

    def include(self, node):
        filename = os.path.join(self._root, self.construct_scalar(node))
        with open(filename, 'r') as f:
            return yaml.load(f, Loader)

class MyDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(MyDumper, self).increase_indent(flow, False)