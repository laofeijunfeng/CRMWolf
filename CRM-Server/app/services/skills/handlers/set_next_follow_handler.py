"""
设置下次跟进 Handler

处理更新跟进记录的 next_follow_time 和 next_action
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.skills.handlers.base_handler import BaseHandler


class SetNextFollowHandler(BaseHandler):
    """设置下次跟进 Handler"""

    handler_type = "SetNextFollowHandler"

    async def execute(
        self,
        db: Session,
        handler_config: Dict[str, Any],
        params: Dict[str, Any],
        user_id: int,
        user_feishu_open_id: Optional[str] = None,
        team_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        执行设置下次跟进

        handler_config 结构:
        {
            "crud_mapping": "lead_follow_up",
            "mode": "update_latest"  // 或 "update_by_id"
        }

        params 必须包含:
            - lead_id 或 customer_id (根据 crud_mapping 类型)
            - next_follow_time: 下次跟进时间 (YYYY-MM-DD)
            - next_action: 下一步动作内容 (可选)
        """
        crud_mapping_name = handler_config.get("crud_mapping")
        mode = handler_config.get("mode", "update_latest")

        if not crud_mapping_name:
            return self.build_result(False, "Handler 配置缺少 crud_mapping")

        # 从数据库获取 CRUD 映射配置
        from app.crud.ai_crud_mapping import ai_crud_mapping_crud

        crud_mapping = ai_crud_mapping_crud.get_by_name(db, crud_mapping_name)
        if not crud_mapping:
            return self.build_result(False, f"CRUD 映射不存在: {crud_mapping_name}")

        # 获取 CRUD 实例
        follow_up_crud = self.get_crud_instance(
            crud_mapping.crud_module,
            crud_mapping.crud_instance_name
        )

        # 解析下次跟进时间
        next_follow_time_str = params.get("next_follow_time")
        if not next_follow_time_str:
            return self.build_result(False, "缺少下次跟进时间")

        next_follow_time = self.parse_date(next_follow_time_str)
        if not next_follow_time:
            return self.build_result(False, "日期格式错误，请使用 YYYY-MM-DD 格式")

        next_action = params.get("next_action")

        # 根据 mode 决定如何找到跟进记录
        follow_up = None
        parent_id = None
        parent_type = None

        if mode == "update_by_id":
            # 通过 follow_up_id 直接更新
            follow_up_id = params.get("follow_up_id")
            if not follow_up_id:
                return self.build_result(False, "缺少 follow_up_id")
            follow_up = follow_up_crud.get_by_id(db, follow_up_id)

        elif mode == "update_latest":
            # 通过 parent_id 找最新跟进记录
            if "lead" in crud_mapping_name:
                parent_id = params.get("lead_id")
                parent_type = "lead"
            else:
                parent_id = params.get("customer_id")
                parent_type = "customer"

            if not parent_id:
                return self.build_result(False, f"缺少 {parent_type}_id")

            # 获取最新跟进记录
            follow_up = follow_up_crud.get_latest_by_lead_id(db, parent_id) if parent_type == "lead" else None

            # 对于客户跟进，需要用不同的查询方法
            if parent_type == "customer" and not follow_up:
                from app.crud.customer_follow_up import customer_follow_up_crud
                follow_ups = customer_follow_up_crud.get_by_customer_id(db, parent_id, limit=1)
                follow_up = follow_ups[0] if follow_ups else None

        if not follow_up:
            return self.build_result(False, "未找到跟进记录，请先创建跟进记录")

        # 执行更新
        try:
            updated = follow_up_crud.update_next_time(
                db, follow_up, next_follow_time, next_action
            )
        except Exception as e:
            return self.build_result(False, f"更新失败: {str(e)}")

        message = f"下次跟进时间已设置为 {next_follow_time_str}"
        if next_action:
            message += f"，下一步动作：{next_action}"

        return self.build_result(True, message, {
            "follow_up_id": updated.id,
            "next_follow_time": next_follow_time_str,
            "next_action": next_action
        })