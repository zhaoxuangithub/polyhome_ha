"""default create file"""
DEFAULT_EXISTS_FILE = ['customize.yaml', 'groups.yaml', 'automations.yaml', 'scripts.yaml', \
                        'switch.yaml', 'light.yaml', 'binary_sensor.yaml', 'sensor.yaml', \
                        'lock.yaml', 'cover.yaml', 'media_player.yaml', 'camera.yaml']

MQTT_TOPIC_BIND_HOST = '/v1/polyhome-ha/host/bind/'
MQTT_TOPIC_BIND_CLIENT = '/v1/polyhome-ha/client/bind/'
MQTT_TOPIC_UNBIND_HOST = '/v1/polyhome-ha/host/unbind/'
MQTT_TOPIC_UNBIND_CLIENT = '/v1/polyhome-ha/client/unbind/'
MQTT_TOPIC_UPDATE = '/v1/polyhome-ha/host/update/'
MQTT_TOPIC_CALL_SERVICE = '/v1/polyhome-ha/host/{}/user_id/{}/services/'
MQTT_TOPIC_PUB_ACK = '/v1/polyhome-ha/host/{}/ack/'

"""
mqtt:
  broker: 123.57.139.200
  port: 1883
  username: polyhome
  password: 123
  client_id: HA_dc:a9:04:99:09:91
"""
POLY_MQTT_CONFIG = (
    # Tuples (attribute, default, auto detect property, description)
    ('broker', '123.57.139.200', '123.57.139.200', 'broker server'),
    ('port', 1883, 1883, 'broker port'),
    ('username', 'polyhome', 'polyhome', 'username'),
    ('password', 123, 123, 'password'),
    ('client_id', '', '', 'client id'),
)

POLY_HOMEASSISTANT_CONFIG = (
    # Tuples (attribute, default, auto detect property, description)
    ('name', 'Home', None, 'Name of the location where Home Assistant is '
     'running'),
    ('latitude', 0, 'latitude', 'Location required to calculate the time'
     ' the sun rises and sets'),
    ('longitude', 0, 'longitude', None),
    ('elevation', 0, None, 'Impacts weather/sunrise data'
                              ' (altitude above sea level in meters)'),
    ('unit_system', 'metric', None, ''),
    ('time_zone', 'UTC', 'time_zone', 'Pick yours from here: http://en.wiki'
     'pedia.org/wiki/List_of_tz_database_time_zones'),
    ('customize', '!include customize.yaml', None, 'Customization file'),
)

DEFAULT_CONF_CONTENT = \
"""
config:
http:
conversation:
poly_config:
poly_ota:
frontend:
automation: !include automations.yaml
group: !include groups.yaml
script: !include scripts.yaml
cover: !include cover.yaml
sensor: !include sensor.yaml
light: !include light.yaml
switch: !include switch.yaml
binary_sensor: !include binary_sensor.yaml
lock: !include lock.yaml
media_player: !include media_player.yaml
"""
