#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
import json
import hashlib
from urllib import request, parse, error

import polyhome.util.macaddr as mac_util
from polyhome.util.zipfile import ZFile

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'gateway'


def setup(hass, config):
    """polyhome ota component"""

    """
    http://api.ourjujia.com/api/v1b/update/poly?
    data={%22platform%22:%224%22,%22packages%22:[%22com.polyhome.mainhost%22]}&
    sign=7cdbe6ec6636d47fd641dc325c64fe46'
    """
    def gateway_update_service(call):
        base_url = 'http://test.poly.ourjujia.com/'
        private_key = "GjcfbhCIJ2owQP1Kxn64DqSk5X4YRZ7u"
        json_obj = {"platform": "4","packages": ["com.homeassistant.component"]}
        json_str = json.dumps(json_obj).replace(' ', '')
        for_sign_str = json_str + private_key
        m = hashlib.md5(for_sign_str.encode(encoding='utf-8'))
        sign_str = m.hexdigest()
        req_url = base_url + 'api/v1b/' + 'update/poly?data=%s&sign=%s' % (json_str, sign_str)
        with request.urlopen(req_url) as web:  
            if web.status == 200:
                data = web.read().decode('utf-8')
                res_json = json.loads(data)
                # print(res_json['data']['result'][0]['url'])
                # download zip package
                url = base_url + res_json['data']['result'][0]['url']
                path = hass.config.config_dir + '/temp.zip'
                with request.urlopen(url) as web:
                    with open(path, 'wb') as outfile:
                        outfile.write(web.read())
                # unpackage zip
                zipfile_obj = ZFile(hass.config.config_dir + '/temp.zip', 'r')
                zipfile_obj.set_password('polyhome6630')
                zipfile_obj.extract_to(hass.config.config_dir + '/')
                zipfile_obj.close()
                # clean temp.zip
                if os.path.exists(hass.config.config_dir + '/temp.zip'):
                    os.remove(hass.config.config_dir + '/temp.zip')
                # restart
                hass.services.call('homeassistant', 'restart')
            else:
                pass

    hass.services.register(DOMAIN, 'host_update', gateway_update_service)
    
    return True



    