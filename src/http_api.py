"""
HTTP API Server - HTTP API 服务器模块
提供通话记录的 HTTP 查询接口
"""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, List
from urllib.parse import urlparse, parse_qs

from .call_record import CallRecord, CallRecordData

logger = logging.getLogger(__name__)


class CallRecordHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    # 类变量，用于存储 call_record 实例
    _call_record: Optional[CallRecord] = None

    def do_GET(self) -> None:
        """处理 GET 请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            self._send_json({"status": "ok"})
        elif path == "/api/calls":
            self._handle_list_calls(query)
        elif path.startswith("/api/calls/"):
            # /api/calls/{id}
            record_id = path.split("/")[-1]
            self._handle_get_call(record_id)
        else:
            self._send_error(404, "Not Found")

    def _handle_list_calls(self, query: dict) -> None:
        """列出通话记录"""
        try:
            phone = query.get("phone", [None])[0]
            limit = int(query.get("limit", [100])[0])
            offset = int(query.get("offset", [0])[0])

            if phone:
                records = self._call_record.get_by_phone(phone)
            else:
                records = self._call_record.get_all(limit, offset)

            self._send_json({
                "data": [self._record_to_dict(r) for r in records],
                "total": len(records)
            })
        except Exception as e:
            logger.error(f"Failed to list calls: {e}")
            self._send_error(500, str(e))

    def _handle_get_call(self, record_id: str) -> None:
        """获取单条通话记录"""
        try:
            record = self._call_record.get_by_id(int(record_id))
            if record:
                self._send_json(self._record_to_dict(record))
            else:
                self._send_error(404, "Record not found")
        except Exception as e:
            logger.error(f"Failed to get call: {e}")
            self._send_error(500, str(e))

    def _record_to_dict(self, record: CallRecordData) -> dict:
        """将记录转换为字典"""
        return {
            "id": record.id,
            "phone_number": record.phone_number,
            "call_time": record.call_time.isoformat() if record.call_time else None,
            "duration": record.duration,
            "call_type": record.call_type,
            "user_text": record.user_text,
            "agent_response": record.agent_response
        }

    def _send_json(self, data: dict, status: int = 200) -> None:
        """发送 JSON 响应"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _send_error(self, status: int, message: str) -> None:
        """发送错误响应"""
        self._send_json({"error": message}, status)

    def log_message(self, format, *args) -> None:
        """禁用日志输出"""
        pass


class APIServer:
    """
    HTTP API 服务器
    提供通话记录的 HTTP 查询接口
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        """
        初始化 HTTP 服务器

        Args:
            host: 监听地址
            port: 监听端口
        """
        self._host = host
        self._port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._call_record: Optional[CallRecord] = None
        self._running = False

    def register_call_record(self, call_record: CallRecord) -> None:
        """
        注册通话记录管理器

        Args:
            call_record: CallRecord 实例
        """
        self._call_record = call_record
        CallRecordHandler._call_record = call_record

    def start(self) -> None:
        """启动服务器"""
        if self._running:
            return

        self._server = HTTPServer((self._host, self._port), CallRecordHandler)
        self._running = True

        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

        logger.info(f"HTTP API server started: {self._host}:{self._port}")

    def _run_server(self) -> None:
        """运行服务器"""
        try:
            while self._running:
                self._server.handle_request()
        except Exception as e:
            logger.error(f"HTTP server error: {e}")

    def stop(self) -> None:
        """停止服务器"""
        if not self._running:
            return

        self._running = False
        if self._server:
            self._server.server_close()

        logger.info("HTTP API server stopped")

    @property
    def is_running(self) -> bool:
        """服务器是否运行中"""
        return self._running

    @property
    def url(self) -> str:
        """服务器 URL"""
        return f"http://{self._host}:{self._port}"