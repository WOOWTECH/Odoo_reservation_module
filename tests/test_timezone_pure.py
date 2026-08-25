# -*- coding: utf-8 -*-
"""不需要 Odoo 的時區轉換測試入口。

    python -m pytest tests/

真正的測試案例寫在 reservation_module/tests/test_timezone_pure.py，
那裡才是模組被部署時 Odoo test loader 會撿到的位置。這一支只是把它
以檔案路徑載進來再匯出，讓 pytest 可以直接跑——直接對 addon 內那支
執行 pytest 會失敗，因為 pytest 會沿著 __init__.py 往上匯入
reservation_module，而那會 import odoo。

被匯出的測試類別本身完全不碰 Odoo，只依賴 pytz。
"""

import importlib.util
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_TARGET = os.path.join(
    os.path.dirname(_HERE), 'reservation_module', 'tests', 'test_timezone_pure.py')


def _load_module():
    spec = importlib.util.spec_from_file_location(
        'reservation_module_test_timezone_pure', _TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_impl = _load_module()

# 把 addon 內的 TestCase 全部拉到本模組命名空間，pytest / unittest 才收得到。
for _name in dir(_impl):
    _obj = getattr(_impl, _name)
    if isinstance(_obj, type) and issubclass(_obj, unittest.TestCase):
        globals()[_name] = _obj

del _name, _obj

if __name__ == '__main__':
    unittest.main()
