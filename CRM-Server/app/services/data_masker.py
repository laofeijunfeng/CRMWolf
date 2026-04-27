"""
数据脱敏服务 - 对敏感数据进行掩码处理
"""
import re
from typing import Optional, Any, Dict, List


class DataMasker:
    """数据脱敏处理器"""

    # 脱敏规则配置
    RULES = {
        # 手机号：138****1234
        "phone": {
            "pattern": r"(\d{3})\d{4}(\d{4})",
            "mask": r"\1****\2"
        },
        # 邮箱：a***@example.com
        "email": {
            "pattern": r"([^@]{1})[^@]*(@[^@]+)",
            "mask": r"\1***\2"
        },
        # 身份证：310***********1234
        "id_card": {
            "pattern": r"(\d{3})\d{11}(\d{4})",
            "mask": r"\1***********\2"
        },
        # 银行账号：6222****1234
        "bank_account": {
            "pattern": r"(\d{4})\d+(\d{4})",
            "mask": r"\1****\2"
        },
        # 姓名：张*明（两个字：张*）
        "name": {
            "pattern": r"([^]{1})[^]+([^]{1})?$",
            "mask": lambda m: m.group(1) + "*" + (m.group(2) if m.group(2) else "")
        },
        # 地址：保留前6个字符，后续用****
        "address": {
            "pattern": r"([^]{6})[^]+",
            "mask": r"\1****"
        }
    }

    # 需要脱敏的字段名（按类型分类）
    SENSITIVE_FIELDS = {
        "phone": ["phone", "mobile", "contact_phone", "telephone", "tel"],
        "email": ["email", "mail", "mailbox"],
        "id_card": ["id_card", "id_number", "identity_card", "身份证号"],
        "bank_account": ["bank_account", "bank_card", "银行卡号"],
        "name": ["name", "real_name", "真实姓名", "customer_name", "lead_name", "contact_name"],
        "address": ["address", "详细地址", "street", "location"]
    }

    @classmethod
    def mask_value(cls, value: Any, field_name: str) -> Any:
        """
        根据字段名自动识别并脱敏

        Args:
            value: 原始值
            field_name: 字段名

        Returns:
            脱敏后的值
        """
        if not value or not isinstance(value, str):
            return value

        # 查找匹配的脱敏类型
        for mask_type, field_names in cls.SENSITIVE_FIELDS.items():
            if field_name.lower() in [f.lower() for f in field_names]:
                return cls._apply_mask(value, mask_type)

        return value

    @classmethod
    def _apply_mask(cls, value: str, mask_type: str) -> str:
        """应用指定类型的脱敏规则"""
        rule = cls.RULES.get(mask_type)
        if not rule:
            return value

        pattern = rule["pattern"]
        mask = rule["mask"]

        try:
            if callable(mask):
                # 使用函数处理
                match = re.search(pattern, value)
                if match:
                    return mask(match)
            else:
                # 使用正则替换
                return re.sub(pattern, mask, value)
        except re.error:
            return value

        return value

    @classmethod
    def mask_phone(cls, phone: Optional[str]) -> Optional[str]:
        """手机号脱敏：138****1234"""
        if not phone:
            return phone
        return cls._apply_mask(phone, "phone")

    @classmethod
    def mask_email(cls, email: Optional[str]) -> Optional[str]:
        """邮箱脱敏：a***@example.com"""
        if not email:
            return email
        return cls._apply_mask(email, "email")

    @classmethod
    def mask_id_card(cls, id_card: Optional[str]) -> Optional[str]:
        """身份证脱敏：310***********1234"""
        if not id_card:
            return id_card
        return cls._apply_mask(id_card, "id_card")

    @classmethod
    def mask_bank_account(cls, account: Optional[str]) -> Optional[str]:
        """银行账号脱敏：6222****1234"""
        if not account:
            return account
        return cls._apply_mask(account, "bank_account")

    @classmethod
    def mask_name(cls, name: Optional[str]) -> Optional[str]:
        """姓名脱敏：张*明"""
        if not name:
            return name
        return cls._apply_mask(name, "name")

    @classmethod
    def mask_dict(cls, data: Dict, sensitive_fields: Optional[List[str]] = None) -> Dict:
        """
        对字典中的敏感字段进行脱敏

        Args:
            data: 原始数据字典
            sensitive_fields: 自定义敏感字段列表（可选）

        Returns:
            脱敏后的数据字典
        """
        if not data:
            return data

        result = {}
        for key, value in data.items():
            if sensitive_fields and key in sensitive_fields:
                # 使用自定义字段列表
                result[key] = cls.mask_value(value, key) if isinstance(value, str) else value
            else:
                # 使用默认规则
                result[key] = cls.mask_value(value, key)
        return result

    @classmethod
    def mask_request_params(cls, params: Optional[Dict]) -> Optional[Dict]:
        """脱敏请求参数"""
        if not params:
            return params

        # 请求参数中需要强制脱敏的字段
        forced_mask_fields = ["password", "pwd", "token", "secret", "api_key", "key"]

        result = {}
        for key, value in params.items():
            if key.lower() in forced_mask_fields:
                result[key] = "******"
            else:
                result[key] = cls.mask_value(value, key)
        return result

    @classmethod
    def mask_response_body(cls, body: Optional[str], max_length: int = 1000) -> Optional[str]:
        """
        脱敏响应体（用于日志记录）

        Args:
            body: 响应体字符串
            max_length: 最大记录长度

        Returns:
            截断后的响应体
        """
        if not body:
            return body

        if len(body) > max_length:
            return body[:max_length] + "...(truncated)"

        return body


# 全局单例
data_masker = DataMasker()