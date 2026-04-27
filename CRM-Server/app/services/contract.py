from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import threading


class ContractNumberGenerator:
    """合同编号生成器（线程安全）"""
    
    _lock = threading.Lock()
    
    @classmethod
    def generate_contract_number(cls, db: Session) -> str:
        """
        生成合同编号
        格式：CT + YYYYMMDD + 四位流水号
        例如：CT202602060001
        
        Args:
            db: 数据库会话
            
        Returns:
            str: 合同编号
        """
        with cls._lock:
            today = datetime.now()
            date_str = today.strftime("%Y%m%d")
            
            result = db.execute(text("""
                SELECT contract_number 
                FROM crm_contracts 
                WHERE contract_number LIKE :pattern 
                ORDER BY id DESC 
                LIMIT 1
            """), {"pattern": f"CT{date_str}%"}).fetchone()
            
            if result:
                last_number = result[0]
                sequence = int(last_number[-4:]) + 1
            else:
                sequence = 1
            
            return f"CT{date_str}{sequence:04d}"


class ContractPricingService:
    """合同价格计算服务"""
    
    @staticmethod
    def calculate_standard_unit_price(
        total_amount: Decimal,
        user_count: int,
        license_type: str,
        subscription_years: Optional[int] = None
    ) -> Decimal:
        """
        计算标准单价
        
        Args:
            total_amount: 合同总金额
            user_count: 采购用户数
            license_type: 授权模式 (SUBSCRIPTION:订阅, PERPETUAL:买断)
            subscription_years: 订阅年限（默认1年）
            
        Returns:
            Decimal: 计算出的标准单价
            
        Raises:
            ValueError: 计算过程中的异常
        """
        try:
            if user_count <= 0:
                raise ValueError("用户数量必须大于0")
            
            if license_type == "SUBSCRIPTION":
                if subscription_years is None or subscription_years <= 0:
                    raise ValueError("订阅制下订阅年限必须大于0")
                
                unit_price = total_amount / Decimal(user_count) / Decimal(subscription_years)
                
            elif license_type == "PERPETUAL":
                unit_price = total_amount / Decimal(user_count) / Decimal(5)
                
            else:
                raise ValueError(f"未知的授权类型: {license_type}")
            
            return unit_price.quantize(Decimal('0.01'))
            
        except Exception as e:
            raise ValueError(f"计算标准单价失败: {str(e)}")
    
    @staticmethod
    def calculate_expiry_date(
        effective_date: Optional[date],
        license_type: str,
        subscription_years: Optional[int] = None
    ) -> Optional[date]:
        """
        计算到期日期
        
        Args:
            effective_date: 生效日期
            license_type: 授权模式
            subscription_years: 订阅年限
            
        Returns:
            Optional[date]: 到期日期
        """
        if not effective_date:
            return None
        
        if license_type == "SUBSCRIPTION" and subscription_years:
            from dateutil.relativedelta import relativedelta
            return effective_date + relativedelta(years=subscription_years)
        
        return None
