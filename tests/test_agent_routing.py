"""
Agent 通知请求"路由判断"测试（纯函数：不需要数据库、不需要 API 密钥）
====================================================================
被测对象：`agent_service._looks_like_notice_request()` 和 `_parse_notice_args()`

它们决定用户消息是不是"要发通知"，从而决定要不要走"三层保障"
（模型自主 → 强制重试 → 确定性兜底）。

★ 为什么要有这个文件（记录了修复的两个真实 bug）
------------------------------------------------
**bug 1（关键词误判）**
    旧版用一张宽松关键词表：["通知","提醒","公告","发送","告知","转告"]，
    只要消息里出现其中任意一个词，就认为用户要发通知。
    后果："提醒我一下，3500乘以12等于多少？" 也被判成通知请求 →
          模型不调通知工具 → 强制重试 2 次仍不调 → 走确定性兜底 →
          弹出荒谬审批："是否批准给员工发送通知：3500乘以12等于多少？？"
    修法：**信号分级**
          · 强信号（通知 / 公告）→ 出现即认定
          · 弱信号（提醒 / 发送 / 告知 / 转告）→ 必须同时出现明确收件人（"给X发…"）

**bug 2（正则贪婪匹配）**
    收件人正则原本是贪婪的 `{1,10}`：
        r"(?:给|向)([^\\s，。：:]{1,10})(?:发|发送|通知)"
    后果："给张三发一条通知：明天上午10点开周会" 解析出收件人 = **"张三发一条"**
          （贪婪地把"发一条"也吃进了姓名）。这个错误姓名会显示在审批卡片上，
          并被 `_do_send` 拿去发送 → **通知发给一个不存在的收件人**。
    修法：改成非贪婪 `{1,10}?`，让它在遇到动词（发/发送/通知）时尽早停下。

★ 这两个 bug 的共同特点（重要教训）
    它们**只在"模型不听话"的兜底路径上暴露**——正常走模型调用工具的路径，
    这两段代码根本不会被执行，所以测不出来、也看不出来。
    这也是为什么"纯函数单测"有价值：不用等模型出错就能覆盖这些分支。
"""

from app.services.agent_service import _looks_like_notice_request, _parse_notice_args

# ============ bug 1 回归：弱信号单独出现，不能算通知请求 ============


def test_weak_keyword_alone_is_not_notice_request():
    """弱信号词单独出现不算通知请求（这就是 bug 1 的原始场景）"""
    assert _looks_like_notice_request("提醒我一下，3500乘以12等于多少？") is False
    assert _looks_like_notice_request("把结果发送给我") is False
    assert _looks_like_notice_request("告知我一下年假几天") is False
    assert _looks_like_notice_request("明天的会议提醒") is False


def test_plain_questions_are_not_notice_request():
    """普通问题不含任何通知关键词，必须走正常路径"""
    assert _looks_like_notice_request("3500乘以12等于多少？") is False
    assert _looks_like_notice_request("北京今天天气怎么样？") is False
    assert _looks_like_notice_request("年假有几天？") is False


# ============ 正常路径：真正的通知请求必须被认出来 ============


def test_strong_keyword_always_triggers():
    """强信号词出现即认定为通知请求"""
    assert _looks_like_notice_request("发个公告") is True
    assert _looks_like_notice_request("通知张三") is True
    assert _looks_like_notice_request("给张三发一条通知：明天上午10点开周会") is True


def test_weak_keyword_with_recipient_triggers():
    """弱信号词 + 明确收件人 = 通知请求"""
    assert _looks_like_notice_request("给张三发送提醒") is True
    assert _looks_like_notice_request("给李四转告一下") is True


# ============ bug 2 回归：收件人解析不能用贪婪匹配 ============


def test_recipient_name_is_not_greedy():
    """★ 非贪婪匹配：不能把"发一条"吃进收件人姓名（bug 2）"""
    emp, content = _parse_notice_args("给张三发一条通知：明天上午10点开周会")
    assert emp == "张三"
    assert "开周会" in content


def test_recipient_parsed_for_various_verbs():
    """发 / 发送 / 转告 等不同动词，都要能正确取到收件人"""
    assert _parse_notice_args("给张三发送提醒")[0] == "张三"
    assert _parse_notice_args("给李四转告一下")[0] == "李四"


def test_recipient_falls_back_when_absent():
    """没有明确收件人时返回占位词"员工"，调用方据此就能判断"这不是格式清晰的通知" """
    assert _parse_notice_args("发个公告")[0] == "员工"
    assert _parse_notice_args("明天的会议提醒")[0] == "员工"
