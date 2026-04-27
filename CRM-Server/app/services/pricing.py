from typing import Literal
from decimal import Decimal, InvalidOperation, DivisionByZero
from enum import Enum


class LicenseType(str, Enum):
    SUBSCRIPTION = "SUBSCRIPTION"
    PERPETUAL = "PERPETUAL"


class PricingCalculationError(Exception):
    """价格计算异常"""
    pass


class PricingService:
    """价格计算服务"""
    
    @staticmethod
    def calculate_unit_price(
        total_amount: float | Decimal,
        user_count: int,
        license_type: str | LicenseType,
        subscription_years: int = 1
    ) -> Decimal:
        """
        计算标准单价
        
        Args:
            total_amount: 预计总金额
            user_count: 采购用户数
            license_type: 授权模式 (SUBSCRIPTION:订阅, PERPETUAL:买断)
            subscription_years: 订阅年限（默认1年）
            
        Returns:
            Decimal: 计算出的标准单价
            
        Raises:
            PricingCalculationError: 计算过程中的异常
        """
        try:
            total_amount_decimal = Decimal(str(total_amount))
            
            if user_count <= 0:
                raise PricingCalculationError("用户数量必须大于0")
            
            license_type_str = str(license_type).split('.')[-1] if isinstance(license_type, str) and '.' in license_type else str(license_type)
            
            if license_type_str == LicenseType.SUBSCRIPTION or license_type == LicenseType.SUBSCRIPTION:
                if subscription_years <= 0:
                    raise PricingCalculationError("订阅年限必须大于0")
                
                unit_price = total_amount_decimal / Decimal(user_count) / Decimal(subscription_years)
                
            elif license_type_str == LicenseType.PERPETUAL or license_type == LicenseType.PERPETUAL:
                unit_price = total_amount_decimal / Decimal(user_count) / Decimal(5)
                
            else:
                raise PricingCalculationError(f"未知的授权类型: {license_type}")
            
            return unit_price.quantize(Decimal('0.01'))
            
        except DivisionByZero:
            raise PricingCalculationError("除零错误")
        except InvalidOperation:
            raise PricingCalculationError("无效的数值运算")
        except Exception as e:
            raise PricingCalculationError(f"计算标准单价失败: {str(e)}")
    
    @staticmethod
    def validate_pricing_input(
        total_amount: float,
        user_count: int,
        license_type: str,
        subscription_years: int = None
    ) -> tuple[bool, str]:
        """
        验证价格输入参数
        
        Args:
            total_amount: 预计总金额
            user_count: 采购用户数
            license_type: 授权模式
            subscription_years: 订阅年限
            
        Returns:
            tuple: (是否有效, 错误信息)
        """
        if total_amount <= 0:
            return False, "总金额必须大于0"
        
        if user_count <= 0:
            return False, "用户数量必须大于0"
        
        if license_type not in [LicenseType.SUBSCRIPTION, LicenseType.PERPETUAL]:
            return False, f"无效的授权模式: {license_type}"
        
        if license_type == LicenseType.SUBSCRIPTION:
            if subscription_years is None or subscription_years <= 0:
                return False, "订阅制下订阅年限必须大于0"
        
        return True, ""


pricing_service = PricingService()
