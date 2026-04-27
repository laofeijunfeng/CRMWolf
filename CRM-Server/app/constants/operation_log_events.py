"""
操作记录事件类型常量定义

该模块定义了系统中所有操作记录的事件类型，供各业务模块使用。
"""

class EventTypes:
    """事件类型常量"""
    
    # 线索模块
    LEAD_CREATED = "LEAD_CREATED"
    LEAD_UPDATED = "LEAD_UPDATED"
    LEAD_DELETED = "LEAD_DELETED"
    LEAD_CONVERTED = "LEAD_CONVERTED"
    LEAD_STATUS_CHANGED = "LEAD_STATUS_CHANGED"
    LEAD_FOLLOW_UP = "LEAD_FOLLOW_UP"
    LEAD_ASSIGNED = "LEAD_ASSIGNED"
    LEAD_RETURNED_TO_POOL = "LEAD_RETURNED_TO_POOL"
    
    # 客户模块
    CUSTOMER_CREATED = "CUSTOMER_CREATED"
    CUSTOMER_UPDATED = "CUSTOMER_UPDATED"
    CUSTOMER_DELETED = "CUSTOMER_DELETED"
    CUSTOMER_STATUS_CHANGED = "CUSTOMER_STATUS_CHANGED"
    CUSTOMER_FOLLOW_UP = "CUSTOMER_FOLLOW_UP"
    CUSTOMER_ASSIGNED = "CUSTOMER_ASSIGNED"
    CUSTOMER_RETURNED_TO_PUBLIC = "CUSTOMER_RETURNED_TO_PUBLIC"
    
    # 商机模块
    OPPORTUNITY_CREATED = "OPPORTUNITY_CREATED"
    OPPORTUNITY_UPDATED = "OPPORTUNITY_UPDATED"
    OPPORTUNITY_DELETED = "OPPORTUNITY_DELETED"
    OPPORTUNITY_STAGE_CHANGED = "OPPORTUNITY_STAGE_CHANGED"
    OPPORTUNITY_WON = "OPPORTUNITY_WON"
    OPPORTUNITY_LOST = "OPPORTUNITY_LOST"
    
    # 合同模块
    CONTRACT_CREATED = "CONTRACT_CREATED"
    CONTRACT_UPDATED = "CONTRACT_UPDATED"
    CONTRACT_DELETED = "CONTRACT_DELETED"
    CONTRACT_STATUS_CHANGED = "CONTRACT_STATUS_CHANGED"
    CONTRACT_SUBMITTED = "CONTRACT_SUBMITTED"
    CONTRACT_APPROVED = "CONTRACT_APPROVED"
    CONTRACT_REJECTED = "CONTRACT_REJECTED"
    CONTRACT_CANCELLED = "CONTRACT_CANCELLED"
    
    # 发票模块
    INVOICE_APPLICATION_CREATED = "INVOICE_APPLICATION_CREATED"
    INVOICE_APPLICATION_UPDATED = "INVOICE_APPLICATION_UPDATED"
    INVOICE_APPLICATION_DELETED = "INVOICE_APPLICATION_DELETED"
    INVOICE_APPLICATION_SUBMITTED = "INVOICE_APPLICATION_SUBMITTED"
    INVOICE_APPLICATION_APPROVED = "INVOICE_APPLICATION_APPROVED"
    INVOICE_APPLICATION_REJECTED = "INVOICE_APPLICATION_REJECTED"
    INVOICE_TITLE_CREATED = "INVOICE_TITLE_CREATED"
    INVOICE_TITLE_UPDATED = "INVOICE_TITLE_UPDATED"
    
    # 回款模块
    PAYMENT_PLAN_CREATED = "PAYMENT_PLAN_CREATED"
    PAYMENT_PLAN_UPDATED = "PAYMENT_PLAN_UPDATED"
    PAYMENT_PLAN_DELETED = "PAYMENT_PLAN_DELETED"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    PAYMENT_PLAN_COMPLETED = "PAYMENT_PLAN_COMPLETED"
    
    # 跟进记录
    MANUAL_FOLLOW_UP = "MANUAL_FOLLOW_UP"
    FOLLOW_UP_RECORDED = "FOLLOW_UP_RECORDED"


class EventActions:
    """事件动作常量"""
    
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    CONVERT = "CONVERT"
    WIN = "WIN"
    LOSE = "LOSE"
    ASSIGN = "ASSIGN"
    RETURN = "RETURN"


class ResourceTypes:
    """资源类型常量"""
    
    LEAD = "LEAD"
    CUSTOMER = "CUSTOMER"
    OPPORTUNITY = "OPPORTUNITY"
    CONTRACT = "CONTRACT"
    INVOICE = "INVOICE"
    INVOICE_APPLICATION = "INVOICE_APPLICATION"
    INVOICE_TITLE = "INVOICE_TITLE"
    PAYMENT_PLAN = "PAYMENT_PLAN"
    PAYMENT_RECORD = "PAYMENT_RECORD"


class OperationLogTemplates:
    """操作记录内容模板"""
    
    @staticmethod
    def lead_created(lead_name: str, source: str, city: str) -> dict:
        return {
            "leadName": lead_name,
            "source": source,
            "city": city
        }
    
    @staticmethod
    def lead_converted(original_lead_name: str, new_customer_name: str, new_customer_id: int) -> dict:
        return {
            "originalLeadName": original_lead_name,
            "newCustomerName": new_customer_name,
            "newCustomerId": new_customer_id
        }
    
    @staticmethod
    def manual_follow_up(content: str, method: str, next_follow_time: str = None) -> dict:
        data = {
            "content": content,
            "method": method
        }
        if next_follow_time:
            data["nextFollowTime"] = next_follow_time
        return data
    
    @staticmethod
    def opportunity_created(opportunity_name: str, expected_amount: float, stage: str) -> dict:
        return {
            "opportunityName": opportunity_name,
            "expectedAmount": expected_amount,
            "stage": stage
        }
    
    @staticmethod
    def contract_status_changed(previous_status: str, current_status: str) -> dict:
        return {
            "previousStatus": previous_status,
            "currentStatus": current_status
        }
    
    @staticmethod
    def payment_received(amount: float, payment_method: str, payment_date: str) -> dict:
        return {
            "amount": amount,
            "paymentMethod": payment_method,
            "paymentDate": payment_date
        }
