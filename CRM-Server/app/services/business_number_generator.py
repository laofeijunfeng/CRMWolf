"""通用业务编号生成器"""
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
import threading


class BusinessNumberGenerator:
    """
    通用业务编号生成器（线程安全）

    支持可配置前缀，每日重置序号。

    格式：{PREFIX}{YYYYMMDD}{四位序号}
    例如：CT202602060001, PAY202607130001
    """

    _lock = threading.Lock()

    # 表名映射：前缀 -> (表名, 编号字段名)
    TABLE_MAPPING = {
        'CT': ('crm_contracts', 'contract_number'),
        'PAY': ('crm_payment_records', 'record_number'),
    }

    @classmethod
    def generate(cls, prefix: str, db: Session) -> str:
        """
        生成业务编号

        Args:
            prefix: 业务前缀（CT/PAY 等）
            db: 数据库会话

        Returns:
            str: 业务编号

        Raises:
            ValueError: 未注册的前缀
        """
        if prefix not in cls.TABLE_MAPPING:
            raise ValueError(f"未注册的业务编号前缀: {prefix}")

        table_name, number_field = cls.TABLE_MAPPING[prefix]

        with cls._lock:
            today = datetime.now()
            date_str = today.strftime("%Y%m%d")

            result = db.execute(text(f"""
                SELECT {number_field}
                FROM {table_name}
                WHERE {number_field} LIKE :pattern
                ORDER BY id DESC
                LIMIT 1
            """), {"pattern": f"{prefix}{date_str}%"}).fetchone()

            if result:
                last_number = result[0]
                sequence = int(last_number[-4:]) + 1
            else:
                sequence = 1

            return f"{prefix}{date_str}{sequence:04d}"

    @classmethod
    def register_table(cls, prefix: str, table_name: str, number_field: str) -> None:
        """
        注册新的业务编号表

        Args:
            prefix: 业务前缀
            table_name: 数据库表名
            number_field: 编号字段名
        """
        cls.TABLE_MAPPING[prefix] = (table_name, number_field)
