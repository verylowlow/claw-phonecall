"""
Call Record - 通话记录模块
存储通话记录到 SQLite
"""

import sqlite3
import logging
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CallRecordData:
    """通话记录数据"""
    id: Optional[int] = None
    phone_number: str = ""
    call_time: datetime = None
    duration: int = 0
    call_type: str = "outbound"  # 'inbound' / 'outbound'
    user_text: str = ""
    agent_response: str = ""


class CallRecord:
    """
    通话记录管理器
    存储通话记录到 SQLite
    """

    def __init__(self, db_path: str = "call_records.db"):
        """
        初始化通话记录管理器

        Args:
            db_path: 数据库文件路径
        """
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表"""
        try:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row

            cursor = self._conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS call_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number VARCHAR(20) NOT NULL,
                    call_time DATETIME NOT NULL,
                    duration INTEGER DEFAULT 0,
                    call_type VARCHAR(10) DEFAULT 'outbound',
                    user_text TEXT,
                    agent_response TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_phone ON call_records(phone_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_call_time ON call_records(call_time)")
            self._conn.commit()

            logger.info(f"Call record database initialized: {self._db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def save(self, record: CallRecordData) -> int:
        """
        保存通话记录

        Args:
            record: 通话记录数据

        Returns:
            int: 记录 ID
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO call_records
                (phone_number, call_time, duration, call_type, user_text, agent_response)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                record.phone_number,
                record.call_time.isoformat() if record.call_time else datetime.now().isoformat(),
                record.duration,
                record.call_type,
                record.user_text,
                record.agent_response
            ))
            self._conn.commit()
            record_id = cursor.lastrowid
            logger.info(f"Saved call record: {record_id}")
            return record_id
        except Exception as e:
            logger.error(f"Failed to save call record: {e}")
            raise

    def get_by_phone(self, phone_number: str) -> List[CallRecordData]:
        """
        按手机号查询通话记录

        Args:
            phone_number: 手机号

        Returns:
            List[CallRecordData]: 通话记录列表
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT * FROM call_records
                WHERE phone_number = ?
                ORDER BY call_time DESC
            """, (phone_number,))

            return self._rows_to_records(cursor.fetchall())
        except Exception as e:
            logger.error(f"Failed to query call records: {e}")
            return []

    def get_by_id(self, record_id: int) -> Optional[CallRecordData]:
        """
        按 ID 查询单条记录

        Args:
            record_id: 记录 ID

        Returns:
            Optional[CallRecordData]: 通话记录
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM call_records WHERE id = ?", (record_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_record(row)
            return None
        except Exception as e:
            logger.error(f"Failed to query call record: {e}")
            return None

    def get_all(self, limit: int = 100, offset: int = 0) -> List[CallRecordData]:
        """
        获取所有通话记录（分页）

        Args:
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            List[CallRecordData]: 通话记录列表
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT * FROM call_records
                ORDER BY call_time DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

            return self._rows_to_records(cursor.fetchall())
        except Exception as e:
            logger.error(f"Failed to query call records: {e}")
            return []

    def _row_to_record(self, row: sqlite3.Row) -> CallRecordData:
        """将数据库行转换为 CallRecordData"""
        return CallRecordData(
            id=row["id"],
            phone_number=row["phone_number"],
            call_time=datetime.fromisoformat(row["call_time"]),
            duration=row["duration"],
            call_type=row["call_type"],
            user_text=row["user_text"] or "",
            agent_response=row["agent_response"] or ""
        )

    def _rows_to_records(self, rows: List[sqlite3.Row]) -> List[CallRecordData]:
        """将数据库行列表转换为 CallRecordData 列表"""
        return [self._row_to_record(row) for row in rows]

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None