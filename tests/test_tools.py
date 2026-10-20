"""
工具层测试
==========
  - calculator：纯逻辑，不需要网络和密钥
  - weather：调用真实 API（Open-Meteo），但断言写得"两种情况下都成立"，
    所以有网/没网都能过（没网时工具会降级到本地模拟数据 —— 这本身也是要测的行为）

⚠️ 旧版本的坑（记录一下）：
   最早的断言是 assert "25" in result —— 那是写死模拟数据的年代。
   后来天气工具改成调真实 API，"25" 就再也不出现了，测试变红。
   教训：**断言要针对"契约"，不要针对"某次具体数据"**。
     契约 = 无论走真实 API 还是降级，都必须带城市名和温度单位。
"""

from app.tools.calculator import calculator
from app.tools.weather import get_weather


def test_calculator_add():
    assert calculator.func("1+1") == 2


def test_calculator_complex():
    assert calculator.func("(3+5)*2") == 16


def test_weather_returns_city_and_temperature():
    """不管走实时 API 还是降级数据，都必须包含城市名和温度单位"""
    result = get_weather.func("北京")
    assert "北京" in result
    assert "°C" in result
    # 要么是真 API 的数据，要么是降级数据 —— 二者必居其一（说明降级机制生效）
    assert ("实时数据" in result) or ("本地缓存" in result)


def test_weather_unknown_city():
    """查不到的城市：要么明确说'未找到'，要么降级数据里也没有 —— 但不能崩"""
    result = get_weather.func("不存在的城市zzz")
    assert ("未找到" in result) or ("暂无" in result)
