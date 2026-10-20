"""
日志模块（企业版：loguru）
==========================
比 print 专业的地方：
  1. 自动带时间戳、日志级别（INFO/WARNING/ERROR）
  2. 同时输出到控制台和文件（logs/app.log）
  3. 文件按大小滚动（10MB 一个），保留 7 天

用法：from app.core.logger import logger; logger.info("xxx")
"""

import os
import sys

from loguru import logger

from app.config import LOG_LEVEL

# 日志目录（D 盘项目内）
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

# 清掉 loguru 默认配置，按我们的来
logger.remove()
# 控制台输出（带颜色）
logger.add(sys.stderr, level=LOG_LEVEL,
           format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
# 文件输出（按大小滚动）
logger.add(os.path.join(_LOG_DIR, "app.log"),
           level=LOG_LEVEL, rotation="10 MB", retention="7 days",
           encoding="utf-8", enqueue=True)
