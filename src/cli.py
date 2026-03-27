"""
AI Phone Agent - 命令行接口 (CLI)
用于 OpenClaw Skill 集成
"""

import sys
import asyncio
import argparse
import logging
import time
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from phone_controller import PhoneController, CallState
from audio_capture import AudioCapture
from audio_player import AudioPlayer
from ai_pipeline import AIPipeline, PipelineState
import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PhoneAgentCLI:
    """电话 Agent CLI"""
    
    def __init__(self):
        self.phone_controller = None
        self.audio_capture = None
        self.audio_player = None
        self.pipeline = None
        self._initialized = False
    
    def initialize(self):
        """初始化组件"""
        if self._initialized:
            return
        
        logger.info("Initializing Phone Agent...")
        
        # 创建组件
        self.phone_controller = PhoneController()
        self.audio_capture = AudioCapture()
        self.audio_player = AudioPlayer()
        
        # 创建 AI 管道
        self.pipeline = AIPipeline(self.phone_controller)
        self.pipeline.set_audio_devices(self.audio_capture, self.audio_player)
        self.pipeline.load_models()
        
        self._initialized = True
        logger.info("Phone Agent initialized")
    
    async def outbound(self, phone_number: str):
        """发起外呼"""
        self.initialize()
        
        logger.info(f"Starting outbound call to {phone_number}")
        
        try:
            success = await self.pipeline.start_outbound_call(phone_number)
            
            if success:
                print(f"✓ 外呼成功: {phone_number}")
                print("通话已建立，AI 对话中...")
                print("按 Ctrl+C 结束通话")
                
                # 等待通话结束
                while self.pipeline.state == PipelineState.ACTIVE:
                    await asyncio.sleep(1)
                
            else:
                print(f"✗ 外呼失败: {phone_number}")
                
        except Exception as e:
            logger.error(f"外呼错误: {e}")
            print(f"✗ 错误: {e}")
    
    async def inbound(self):
        """启动呼入监控"""
        self.initialize()
        
        logger.info("Starting inbound call monitoring...")
        print("✓ 监听模式已启动")
        print("等待来电...")
        
        # 注册回调
        def on_incoming(event):
            print(f"\n📞 来电: {event.phone_number}")
            asyncio.create_task(self.handle_incoming(event))
        
        self.phone_controller.start_monitoring(on_incoming=on_incoming)
        
        # 保持运行
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n停止监听...")
            self.phone_controller.stop_monitoring()
    
    async def handle_incoming(self, event):
        """处理来电"""
        try:
            success = await self.pipeline.handle_incoming_call(event)
            if success:
                print("✓ 已接听，通话中...")
                
                while self.pipeline.state == PipelineState.ACTIVE:
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"处理来电错误: {e}")
    
    def hangup(self):
        """挂断电话"""
        if not self._initialized:
            self.initialize()
        
        if self.pipeline and self.pipeline.state == PipelineState.ACTIVE:
            asyncio.run(self.pipeline.end_call())
            print("✓ 已挂断")
        else:
            # 直接用控制器挂断
            self.phone_controller.hangup()
            print("✓ 已挂断")
    
    def status(self):
        """查看状态"""
        if not self._initialized:
            self.initialize()
        
        state = self.phone_controller.get_call_state()
        print(f"通话状态: {state.name}")
        
        if self.pipeline:
            print(f"AI 管道状态: {self.pipeline.state.value}")
            if self.pipeline.current_phone_number:
                print(f"当前号码: {self.pipeline.current_phone_number}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="AI Phone Agent CLI")
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # 外呼命令
    outbound_parser = subparsers.add_parser("outbound", help="发起外呼")
    outbound_parser.add_argument("phone_number", help="电话号码")
    
    # 监听命令
    subparsers.add_parser("inbound", help="启动来电监听")
    
    # 挂断命令
    subparsers.add_parser("hangup", help="挂断电话")
    
    # 状态命令
    subparsers.add_parser("status", help="查看通话状态")
    
    # 测试命令
    subparsers.add_parser("test", help="运行测试")
    
    args = parser.parse_args()
    
    cli = PhoneAgentCLI()
    
    if args.command == "outbound":
        asyncio.run(cli.outbound(args.phone_number))
    elif args.command == "inbound":
        asyncio.run(cli.inbound())
    elif args.command == "hangup":
        cli.hangup()
    elif args.command == "status":
        cli.status()
    elif args.command == "test":
        # 运行集成测试
        from tests.test_integration import IntegrationTest
        test = IntegrationTest()
        test.run_all_tests()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()