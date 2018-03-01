"""about mac of net"""
import uuid
import json
import os

def get_mac_address():
    """get mac address"""
    mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
    mac_address = ":".join([mac[e:e+2] for e in range(0, 11, 2)])
    return mac_address

def get_uuid(config_path):
    """Read Device uuid"""
    try:
        with open(config_path + '/.uuid', 'r+') as uuid_file:
            dev_uuid = json.loads(uuid_file.read())
            return dev_uuid.get('uuid')
    except IOError:
        return None

def device_is_bind(config_path):
    """device is bind"""
    try:
        with open(config_path + '/.bind', 'r+') as bind_file:
            has_bind = 'true' in bind_file.read()
            return has_bind 
    except IOError:
        pass

def update_bind_state(config_path, state):
    """update bind state"""
    try:
        with open(config_path + '/.bind', 'w') as bind_file:
            bind_file.write(state)
    except IOError:
        pass

def is_factory_reset(path):
    try:
        if os.path.exists(path + '/.reset'):
            return False
        else: 
            return True
    except IOError:
        return True

def set_reset_flag(file_path):
    # write file make inited flag
    with open(file_path + '/.reset', 'wt') as config_file:
        config_file.write('true')

def _create_uuid(file_path):
    """Create UUID and save it in a file."""
    if os.path.exists(file_path + '/.uuid'): 
        return 
    with open(file_path + '/.uuid', 'w') as fptr:
        _uuid = uuid.uuid4().hex
        fptr.write(json.dumps({'uuid': _uuid}))
        return _uuid