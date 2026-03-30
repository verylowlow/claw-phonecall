"""
真机测试 - 电话控制功能
测试项目：拨打电话、接听、挂断、状态监控

默认跳过；需要时: 设置环境变量 RUN_REAL_PHONE_TESTS=1 后再 pytest。
"""

import os
import sys
import time
import logging
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.phone_controller import PhoneController, CallState
from src import config

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_REAL_PHONE_TESTS"),
    reason="Real-device tests; set RUN_REAL_PHONE_TESTS=1 to enable",
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_get_call_state():
    """测试1: 获取通话状态"""
    logger.info("\n=== 测试1: 获取通话状态 ===")

    controller = PhoneController()
    state = controller.get_call_state()

    logger.info(f"当前通话状态: {state.name} ({state.value})")

    # 测试获取来电号码
    number = controller.get_incoming_number()
    logger.info(f"来电号码: {number or '无'}")

    return True


def test_dial_phone():
    """测试2: 拨打电话"""
    logger.info("\n=== 测试2: 拨打电话 ===")

    controller = PhoneController()

    # 拨打电话（使用测试号码）
    test_number = "10086"  # 中国移动客服
    logger.info(f"正在拨打 {test_number} ...")

    result = controller.dial_and_call(test_number)
    logger.info(f"拨号结果: {'成功' if result else '失败'}")

    if result:
        # 等待对方接听（最多等待10秒）
        logger.info("等待对方接听...")
        for i in range(20):
            time.sleep(0.5)
            state = controller.get_call_state()
            logger.info(f"  通话状态: {state.name}")
            if state == CallState.OFFHOOK:
                logger.info("对方已接听！")
                break

    return result


def test_hangup():
    """测试3: 挂断电话"""
    logger.info("\n=== 测试3: 挂断电话 ===")

    controller = PhoneController()
    state = controller.get_call_state()

    if state in [CallState.RINGING, CallState.OFFHOOK]:
        result = controller.hangup()
        logger.info(f"挂断结果: {'成功' if result else '失败'}")
        time.sleep(1)

        # 验证状态
        new_state = controller.get_call_state()
        logger.info(f"挂断后状态: {new_state.name}")
        return new_state == CallState.IDLE
    else:
        logger.info("当前没有通话，无法测试挂断")
        return True


def test_monitoring():
    """测试4: 状态监控"""
    logger.info("\n=== 测试4: 状态监控 ===")

    controller = PhoneController()

    # 状态变化记录
    events = []

    def on_incoming(event):
        logger.info(f"📞 来电事件: {event.phone_number or '未知号码'}")
        events.append(event)

    def on_answered(event):
        logger.info("✅ 接通事件")
        events.append(event)

    def on_hungup(event):
        logger.info("📴 挂断事件")
        events.append(event)

    def on_state_changed(event):
        logger.info(f"🔄 状态变化: {event.state.name}")
        events.append(event)

    # 启动监控
    controller.start_monitoring(
        on_incoming=on_incoming,
        on_answered=on_answered,
        on_hungup=on_hungup,
        on_state_changed=on_state_changed
    )

    # 持续监控10秒
    logger.info("开始监控通话状态 (10秒)...")
    for i in range(10):
        time.sleep(1)
        state = controller.get_call_state()
        logger.info(f"  {i+1}s - 状态: {state.name}")

    # 停止监控
    controller.stop_monitoring()

    logger.info(f"捕获事件数: {len(events)}")
    return True


def main():
    logger.info("=" * 50)
    logger.info("真机测试 - 电话控制功能")
    logger.info("=" * 50)

    # 测试1: 获取通话状态
    test_get_call_state()

    # 确认继续
    print("\n请确认手机屏幕，准备拨打测试电话...")
    input("按回车继续测试拨打电话...")

    # 测试2: 拨打电话
    test_dial_phone()

    # 确认继续
    print("\n请在手机上接听或等待对方挂断...")
    input("按回车继续测试挂断...")

    # 测试3: 挂断
    test_hangup()

    # 确认继续
    print("\n准备测试状态监控...")
    input("按回车开始监控测试...")

    # 测试4: 监控
    test_monitoring()

    logger.info("\n" + "=" * 50)
    logger.info("所有测试完成!")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()