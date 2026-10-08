# -*- coding: utf-8 -*-
# Ensure IPv4 compatibility in Docker bridge environments without IPv6 routing
try:
    import urllib3.util.connection as urllib3_cn
    urllib3_cn.HAS_IPV6 = False
except Exception:
    pass

from . import res_company
from . import res_config_settings
from . import ai_extract_mixin
