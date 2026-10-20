"""
天气工具（实时 API）
===================
从"教学版模拟数据"升级为"真实天气 API"：
  - 用 Open-Meteo（免费、无需 API key、支持中国城市）
  - 两步：① 城市名 → 经纬度（地理编码）② 经纬度 → 实时天气
  - 降级策略：API 失败/没网 → 退回本地模拟数据（不阻断 Agent 流程）

面试讲点：Agent 调外部 API 是真实场景——工具内部可以调用任何第三方服务。
"""

import json
import urllib.request
from urllib.parse import quote

from langchain_core.tools import tool

# 降级用的本地模拟数据（API 不可用时兜底）
# ★ 值里带上城市名，保证"降级回答"与"真实 API 回答"的格式一致。
#   否则 API 挂掉时用户会看到一句没有城市的天气，莫名其妙；
#   同时这也让测试能写成"契约级"断言（两条路径都含城市名 + 温度单位）。
_WEATHER = {
    "北京": "北京：晴，25°C，空气质量良（本地缓存）",
    "上海": "上海：小雨，22°C，记得带伞（本地缓存）",
    "广州": "广州：多云，30°C，闷热（本地缓存）",
    "深圳": "深圳：雷阵雨，28°C（本地缓存）",
}

# WMO 天气代码 → 中文描述（Open-Meteo 返回的是代码）
_WMO_DESC = {
    0: "晴", 1: "基本晴朗", 2: "多云", 3: "阴",
    45: "雾", 48: "冻雾",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    80: "阵雨", 81: "阵雨", 82: "强阵雨",
    95: "雷暴", 96: "雷暴伴冰雹", 99: "强雷暴伴冰雹",
}


def _wmo_description(code: int) -> str:
    return _WMO_DESC.get(code, f"天气代码{code}")


def _fetch_weather(city: str) -> str:
    """第 1 步：城市名 → 经纬度（Open-Meteo 地理编码，免费无 key）"""
    geo_url = (
        "https://geocoding-api.open-meteo.com/v1/search?"
        f"name={quote(city)}&count=1&language=zh"
    )
    with urllib.request.urlopen(geo_url, timeout=8) as resp:
        geo = json.loads(resp.read().decode("utf-8"))
    if not geo.get("results"):
        return f"未找到城市『{city}』，请确认城市名"
    loc = geo["results"][0]
    lat, lon = loc["latitude"], loc["longitude"]

    # 第 2 步：经纬度 → 实时天气
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        "&timezone=auto"
    )
    with urllib.request.urlopen(weather_url, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    cur = data["current"]
    name = loc.get("name", city)
    return (
        f"{name}：{_wmo_description(cur['weather_code'])}，"
        f"{cur['temperature_2m']}°C，湿度{cur['relative_humidity_2m']}%，"
        f"风速{cur['wind_speed_10m']}km/h（实时数据）"
    )


@tool
def get_weather(city: str) -> str:
    """查询指定城市的实时天气。参数 city 是城市名，例如"北京"、"上海"、"广州"。
    返回实时温度、天气状况、湿度、风速。"""
    try:
        return _fetch_weather(city)
    except Exception as e:
        # 降级：API 不可用（没网/超时）→ 本地模拟数据，不阻断 Agent
        print(f"  ⚠️ 天气 API 不可用，降级本地数据: {type(e).__name__}")
        return _WEATHER.get(city, f"实时天气查询失败，暂无{city}的数据")
