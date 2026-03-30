"""
AI Phone Agent - 命令行接口 (CLI)
用于 OpenClaw Skill 集成

从项目根目录运行: python -m src.cli <子命令>
"""

import sys
import asyncio
import argparse
import logging
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import configure_logging

configure_logging()

from src.phone_controller import PhoneController, CallState
from src.audio_capture import AudioCapture
from src.audio_player import AudioPlayer
from src.ai_pipeline import AIPipeline, PipelineState

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
        if self._initialized:
            return

        logger.info("Initializing Phone Agent...")

        self.phone_controller = PhoneController()
        self.audio_capture = AudioCapture()
        self.audio_player = AudioPlayer()

        self.pipeline = AIPipeline(self.phone_controller)
        self.pipeline.set_audio_devices(self.audio_capture, self.audio_player)
        self.pipeline.load_models()

        self._initialized = True
        logger.info("Phone Agent initialized")

    async def outbound(self, phone_number: str):
        self.initialize()

        logger.info("Starting outbound call to %s", phone_number)

        try:
            success = await self.pipeline.start_outbound_call(phone_number)

            if success:
                print(f"OK outbound: {phone_number}")
                print("Call active. Press Ctrl+C to end.")

                while self.pipeline.state == PipelineState.ACTIVE:
                    await asyncio.sleep(1)

            else:
                print(f"FAIL outbound: {phone_number}")

        except Exception as e:
            logger.error("Outbound error: %s", e)
            print(f"ERROR: {e}")

    async def inbound(self):
        self.initialize()

        logger.info("Starting inbound call monitoring...")
        print("Inbound monitor started. Waiting for calls...")

        def on_incoming(event):
            print(f"\nIncoming: {event.phone_number}")
            asyncio.create_task(self.handle_incoming(event))

        self.phone_controller.start_monitoring(on_incoming=on_incoming)

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            self.phone_controller.stop_monitoring()

    async def handle_incoming(self, event):
        try:
            success = await self.pipeline.handle_incoming_call(event)
            if success:
                print("Answered, call active...")

                while self.pipeline.state == PipelineState.ACTIVE:
                    await asyncio.sleep(1)

        except Exception as e:
            logger.error("handle_incoming: %s", e)

    def hangup(self):
        if not self._initialized:
            self.initialize()

        if self.pipeline and self.pipeline.state == PipelineState.ACTIVE:
            asyncio.run(self.pipeline.end_call())
            print("Hangup OK")
        else:
            self.phone_controller.hangup()
            print("Hangup OK")

    def status(self):
        if not self._initialized:
            self.initialize()

        state = self.phone_controller.get_call_state()
        print(f"Call state: {state.name}")

        if self.pipeline:
            print(f"Pipeline state: {self.pipeline.state.value}")
            if self.pipeline.current_phone_number:
                print(f"Number: {self.pipeline.current_phone_number}")


def main():
    parser = argparse.ArgumentParser(description="AI Phone Agent CLI")
    sub = parser.add_subparsers(dest="command", help="command")

    p_out = sub.add_parser("outbound", help="place outbound call")
    p_out.add_argument("phone_number", help="phone number")

    sub.add_parser("inbound", help="listen for incoming calls")
    sub.add_parser("hangup", help="hang up")
    sub.add_parser("status", help="show status")
    sub.add_parser("test", help="run integration smoke tests")

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
        from tests.test_integration import main as integration_main

        integration_main()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
