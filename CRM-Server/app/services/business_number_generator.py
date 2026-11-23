"""通用业务编号生成器"""
import threading
from typing import ClassVar

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.utils.time import business_now


class BusinessNumberGenerator:
    """
    通用业务编号生成器\uff08线程安全\uff09

    支持可配置前缀\uff0c每日重置序号。

    格式\uff1a{PREFIX}{YYYYMMDD}{四位序号}
    例如\uff1aCT202602060001, PAY202607130001
    """

    _lock = threading.Lock()

    # 表名映射:前缀 -> (表名, 编号字段名)
    TABLE_MAPPING: ClassVar[dict[str, tuple[str, str]]] = {
        'CT': ('crm_contracts', 'contract_number'),
        'PAY': ('crm_payment_records', 'record_number'),
        'PP': ('crm_contract_payment_plans', 'plan_number'),
        'INV': ('crm_invoice_applications', 'application_number'),
        'INVR': ('crm_invoice_reissue_applications', 'application_number'),
        'LIC': ('crm_license_applications', 'application_number'),
        'OPP': ('crm_opportunities', 'opportunity_number'),
    }

    @classmethod
    def generate(cls, prefix: str, db: Session) -> str:
        """
        生成业务编号

        Args:
            prefix: 业务前缀\uff08CT/PAY/PP/INV/LIC/OPP 等\uff09
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
            today = business_now()
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
