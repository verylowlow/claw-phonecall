"""
AI Phone Agent - 集成测试脚本
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from phone_controller import PhoneController, CallState
from audio_capture import AudioCapture
from audio_player import AudioPlayer
from humanization import Humanization
from ai_pipeline import AIPipeline, PipelineState
import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format=config.LOG_CONFIG["format"]
)
logger = logging.getLogger(__name__)


class IntegrationTest:
    """集成测试类"""
    
    def __init__(self):
        self.results = {}
    
    def run_all_tests(self):
        """运行所有测试"""
        logger.info("=" * 50)
        logger.info("Starting Integration Tests")
        logger.info("=" * 50)
        
        tests = [
            ("Config Loading", self.test_config_loading),
            ("PhoneController Init", self.test_phone_controller_init),
            ("AudioCapture Init", self.test_audio_capture_init),
            ("AudioPlayer Init", self.test_audio_player_init),
            ("Humanization Init", self.test_humanization_init),
            ("AIPipeline Init", self.test_ai_pipeline_init),
        ]
        
        for name, test_func in tests:
            logger.info(f"\n--- Test: {name} ---")
            try:
                result = test_func()
                self.results[name] = "PASS" if result else "FAIL"
                logger.info(f"Result: {self.results[name]}")
            except Exception as e:
                self.results[name] = f"ERROR: {e}"
                logger.error(f"Result: ERROR - {e}")
        
        self.print_summary()
    
    def test_config_loading(self) -> bool:
        """测试配置加载"""
        logger.info(f"Sample rate: {config.AUDIO_CONFIG['sample_rate']}")
        logger.info(f"Channels: {config.AUDIO_CONFIG['channels']}")
        logger.info(f"ADB timeout: {config.ADB_CONFIG['timeout']}")
        return True
    
    def test_phone_controller_init(self) -> bool:
        """测试 PhoneController 初始化"""
        controller = PhoneController()
        assert controller is not None
        assert controller.device_id is None
        logger.info("PhoneController created successfully")
        return True
    
    def test_audio_capture_init(self) -> bool:
        """测试 AudioCapture 初始化"""
        capture = AudioCapture()
        assert capture is not None
        assert capture.device_id is None
        logger.info("AudioCapture created successfully")
        return True
    
    def test_audio_player_init(self) -> bool:
        """测试 AudioPlayer 初始化"""
        player = AudioPlayer()
        assert player is not None
        # 不实际打开设备，避免错误
        logger.info("AudioPlayer created successfully")
        return True
    
    def test_humanization_init(self) -> bool:
        """测试 Humanization 初始化"""
        human = Humanization()
        assert human is not None
        assert len(human.filler_phrases) > 0
        logger.info(f"Humanization created with {len(human.filler_phrases)} filler phrases")
        return True
    
    def test_ai_pipeline_init(self) -> bool:
        """测试 AIPipeline 初始化"""
        controller = PhoneController()
        pipeline = AIPipeline(controller)
        assert pipeline is not None
        assert pipeline.state == PipelineState.IDLE
        logger.info("AIPipeline created successfully")
        return True
    
    def print_summary(self):
        """打印测试摘要"""
        logger.info("\n" + "=" * 50)
        logger.info("Test Summary")
        logger.info("=" * 50)
        
        passed = sum(1 for v in self.results.values() if v == "PASS")
        failed = sum(1 for v in self.results.values() if v == "FAIL")
        errors = sum(1 for v in self.results.values() if "ERROR" in v)
        
        for name, result in self.results.items():
            logger.info(f"  {name}: {result}")
        
        logger.info(f"\nTotal: {len(self.results)}")
        logger.info(f"Passed: {passed}, Failed: {failed}, Errors: {errors}")


def test_phone_controller():
    """测试 PhoneController 功能"""
    logger.info("\n--- Testing PhoneController ---")
    
    controller = PhoneController()
    
    # 测试状态获取（在没有手机连接时会失败，但不会崩溃）
    try:
        state = controller.get_call_state()
        logger.info(f"Current call state: {state}")
    except Exception as e:
        logger.warning(f"Cannot get call state (no device): {e}")
    
    logger.info("PhoneController test completed")


def test_humanization():
    """测试 Humanization 功能"""
    logger.info("\n--- Testing Humanization ---")
    
    human = Humanization()
    
    # 测试填充词检测
    human.on_speech_end(1000)
    time.sleep(0.1)
    
    # 模拟 LLM 响应开始
    human.on_llm_response_start()
    
    # 检查是否应该插入填充词
    should_filler = human.should_insert_filler()
    logger.info(f"Should insert filler: {should_filler}")
    
    if should_filler:
        filler = human.get_filler()
        logger.info(f"Filler phrase: {filler}")
    
    logger.info("Humanization test completed")


def main():
    """主函数"""
    logger.info("AI Phone Agent - Integration Tests")
    logger.info(f"Python version: {sys.version}")
    
    # 运行集成测试
    test = IntegrationTest()
    test.run_all_tests()
    
    # 运行功能测试
    test_phone_controller()
    test_humanization()
    
    logger.info("\nAll tests completed!")


if __name__ == "__main__":
    main()