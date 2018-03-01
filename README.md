# 项目目录说明

* configuration.yaml 项目的配置文件
* automations.yaml 情景配置文件
* customize.yaml 汉化文件
* group.yaml 分组配置文件
* scripts.yaml 自定义脚本文件
* deps 组件的依赖库文件
* custom_components 自定义组件根目录
* custom_components/util/ 自定义组件的工具类模块
* custom_components/helper/ 自定义组件的辅助类模块
* custom_components/light／ 平台加载的根目录
* test/ 自己的一些测试代码片段
* .HA_VERSION 框架版本号
* known_devices.yaml 小米路由器追踪的设备列表和参数配置文件

# 运行环境

* homeassistant: last 

https://home-assistant.io/ 查看最新的版本

* linux板子python版本: python3.5.2

# 开发环境

* VSCode ／ Atom / pycharm
* python检测工具 pylint
* 代码风格 PEP8 style 和 PEP 257

# 术语

Homeassistant 简称 ha

# 基础命令

* hass --open-ui 启动ha并打开浏览器显示web界面
* hass -c yourself-config-dir 启动ha并加载自定义配置文件
* hass --demo-mode    启动 HomeAssistant 的Demo模式

# 开发者向导

* https://home-assistant.io/developers/

里面详细的介绍了几大组件的功能和api

* https://home-assistant.io/developers/platform_example_sensor/

增加一个Sensor组件的Demo代码

* https://home-assistant.io/developers/platform_example_light/

增加一个平台的Demo代码

# python代码规范

http://zh-google-styleguide.readthedocs.io/en/latest/google-python-styleguide/python_style_rules/

