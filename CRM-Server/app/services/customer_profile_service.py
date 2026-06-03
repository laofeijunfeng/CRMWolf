"""
客户档案 AI 自动补充服务

负责在客户创建或线索转化后，异步调用 AI 生成客户档案信息
使用行业分级体系进行行业匹配和同行业客户筛选
"""
import json
import asyncio
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import SessionLocal
from app.models.customer import Customer
from app.crud.customer import customer_crud
from app.crud.customer_follow_up import customer_follow_up_crud
from app.crud.industry import industry_crud
from app.crud.ai_config import ai_config_crud
from app.services.ai_service import ai_service


class CustomerProfileService:
    """客户档案生成服务"""

    async def generate_profile(
        self,
        customer_id: int,
        account_name: str,
        source_lead_id: Optional[int] = None,
        team_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        生成客户档案

        Args:
            customer_id: 客户ID
            account_name: 客户公司名称
            source_lead_id: 来源线索ID（如果是从线索转化）
            team_id: 团队ID

        Returns:
            生成结果字典
        """
        db = SessionLocal()
        try:
            # 1. 更新状态为 GENERATING
            customer_crud.update_profile_status(db, customer_id, "GENERATING")

            # 2. 获取 AI 配置
            config = ai_config_crud.get_config(db)
            if not config:
                raise ValueError("AI 配置未设置")

            api_key = ai_config_crud.get_decrypted_api_key(db)
            if not api_key:
                raise ValueError("无法获取 API Key")

            # 3. 获取行业层级结构
            industry_hierarchy = industry_crud.get_industry_hierarchy(db)

            # 4. 获取跟进记录（如果有线索来源）
            lead_follow_ups = None
            if source_lead_id:
                lead_follow_ups = customer_follow_up_crud.get_by_original_lead_id(db, source_lead_id)

            # 5. 构建提示词（第一阶段：判断行业）
            prompt = self._build_prompt_for_industry(account_name, industry_hierarchy, lead_follow_ups)

            # 6. 第一次调用 AI：判断行业
            full_content = await ai_service._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {"role": "system", "content": self._get_system_prompt_for_industry()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1024,
                response_format={"type": "json_object"}
            )

            # 7. 解析行业结果
            industry_data = self._parse_industry_response(full_content, industry_hierarchy)
            industry_code = industry_data.get("industry_code", "other")

            # 8. 更新行业字段
            customer_crud.update_industry(db, customer_id, industry_code)

            # 9. 获取同行业客户候选列表（限制在当前团队）
            similar_customer_candidates = industry_crud.get_customers_by_industry(
                db, industry_code, customer_id, team_id, limit=50
            )

            # 10. 第二次调用 AI：生成完整档案（包含同行业客户选择）
            prompt2 = self._build_prompt_for_profile(
                account_name,
                industry_code,
                industry_hierarchy,
                similar_customer_candidates,
                lead_follow_ups
            )

            full_content2 = await ai_service._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {"role": "system", "content": self._get_system_prompt_for_profile()},
                    {"role": "user", "content": prompt2}
                ],
                temperature=0.3,
                max_tokens=2048,
                response_format={"type": "json_object"}
            )

            # 11. 解析档案结果
            profile_data = self._parse_profile_response(full_content2, similar_customer_candidates)

            # 12. 更新客户档案
            customer_crud.update_profile(
                db,
                customer_id,
                {
                    "company_background": profile_data.get("company_background"),
                    "company_website": profile_data.get("company_website"),
                    "main_business": profile_data.get("main_business"),
                    "similar_customers": json.dumps(profile_data.get("similar_customers", [])),
                    "project_background": profile_data.get("project_background"),
                    "profile_status": "COMPLETED",
                    "profile_generated_time": datetime.now()
                }
            )

            return {
                "success": True,
                "customer_id": customer_id,
                "industry_code": industry_code,
                "profile_data": profile_data
            }

        except Exception as e:
            # 更新状态为 FAILED
            customer_crud.update_profile_status(
                db,
                customer_id,
                "FAILED",
                error_message=str(e)
            )

            return {
                "success": False,
                "customer_id": customer_id,
                "error": str(e)
            }
        finally:
            db.close()

    def _get_system_prompt_for_industry(self) -> str:
        """获取行业判断的系统提示词"""
        return """你是一个企业行业分类助手，负责根据企业名称判断其所属行业。

## 输出要求

你必须输出严格的 JSON 格式：
```json
{
  "industry_code": "二级行业编码（优先选择二级行业，如果无法判断则选择一级行业）"
}
```

## 行业选择原则

1. 尽可能选择二级行业（更精确的分类）
2. 如果无法确定二级行业，可以选择一级行业编码
3. 如果完全无法判断，选择 "other"

## 注意事项

- industry_code 必须从用户提供的行业编码列表中选择
- 不能自创行业编码
- 输出纯 JSON，不要包含任何其他文字"""

    def _get_system_prompt_for_profile(self) -> str:
        """获取档案生成的系统提示词"""
        return """你是一个企业信息分析助手，负责生成客户档案信息。

## 输出要求

你必须输出严格的 JSON 格式：
```json
{
  "company_background": "企业背景描述（100-200字，中文）",
  "company_website": "公司官网URL（如果无法确定，填写 null）",
  "main_business": "主营业务描述（100字左右，中文）",
  "similar_customers": ["从提供的候选客户中选择1-5个最相近的客户名称"],
  "project_background": "项目需求背景分析（如果有跟进记录，基于记录分析客户可能的需求；否则填写 null）"
}
```

## 注意事项

1. similar_customers 必须从用户提供的候选列表中选择，不能自创
2. 选择最相近的 1-5 个客户（业务相似、规模相近等）
3. 如果候选列表为空，similar_customers 填写空数组 []
4. company_website 如果不确定，填写 null
5. project_background 需要分析跟进记录中的客户痛点、需求等
6. 所有描述使用中文"""

    def _build_prompt_for_industry(
        self,
        account_name: str,
        industry_hierarchy: dict,
        lead_follow_ups: Optional[List[Any]]
    ) -> str:
        """构建行业判断的提示词"""

        # 构建行业编码列表
        industry_codes = []
        for primary_code, primary_info in industry_hierarchy.items():
            # 添加一级行业
            industry_codes.append(f"{primary_code}（{primary_info['name']}）")
            # 添加二级行业
            for child in primary_info['children']:
                industry_codes.append(f"{child['code']}（{child['name']}）")

        codes_str = "\n".join(industry_codes)

        prompt = f"""请判断以下企业的所属行业。

企业名称：{account_name}

可选的行业编码列表（优先选择二级行业）：
{codes_str}

请输出 JSON 格式的行业编码。"""

        # 如果有跟进记录，加入分析上下文
        if lead_follow_ups and len(lead_follow_ups) > 0:
            follow_up_summary = self._summarize_follow_ups(lead_follow_ups)
            prompt += f"\n\n以下是该企业的跟进记录（可用于辅助判断行业）：\n{follow_up_summary}"

        return prompt

    def _build_prompt_for_profile(
        self,
        account_name: str,
        industry_code: str,
        industry_hierarchy: dict,
        similar_customer_candidates: List[str],
        lead_follow_ups: Optional[List[Any]]
    ) -> str:
        """构建档案生成的提示词"""

        # 获取行业名称
        industry_name = self._get_industry_name(industry_code, industry_hierarchy)

        prompt = f"""请为以下企业生成客户档案信息。

企业名称：{account_name}
所属行业：{industry_name}（{industry_code}）"""

        # 同行业客户候选列表
        if similar_customer_candidates and len(similar_customer_candidates) > 0:
            candidates_str = "\n".join([f"- {name}" for name in similar_customer_candidates])
            prompt += f"\n\n以下是系统中的同行业客户候选列表（请从中选择1-5个最相近的客户）：\n{candidates_str}"
        else:
            prompt += "\n\n系统中暂无同行业客户候选。"

        # 跟进记录分析
        if lead_follow_ups and len(lead_follow_ups) > 0:
            follow_up_summary = self._summarize_follow_ups(lead_follow_ups)
            prompt += f"\n\n以下是该企业的跟进记录（请分析其中的客户需求和痛点）：\n{follow_up_summary}"

        return prompt

    def _get_industry_name(self, industry_code: str, industry_hierarchy: dict) -> str:
        """根据行业编码获取行业名称"""
        for primary_code, primary_info in industry_hierarchy.items():
            if primary_code == industry_code:
                return primary_info['name']
            for child in primary_info['children']:
                if child['code'] == industry_code:
                    return child['name']
        return "其他"

    def _summarize_follow_ups(self, follow_ups: List[Any]) -> str:
        """将跟进记录转换为文本摘要"""
        lines = []
        for i, fu in enumerate(follow_ups, 1):
            content = fu.content if hasattr(fu, 'content') else fu.get('content', '')
            method = fu.method if hasattr(fu, 'method') else fu.get('method', '')
            created_time = fu.created_time if hasattr(fu, 'created_time') else fu.get('created_time', '')

            if isinstance(created_time, datetime):
                date_str = created_time.strftime("%Y-%m-%d")
            else:
                date_str = str(created_time)[:10] if created_time else ''
            lines.append(f"{i}. [{date_str}] {method}: {content}")

        return "\n".join(lines)

    def _parse_industry_response(self, content: str, industry_hierarchy: dict) -> Dict[str, Any]:
        """解析行业判断响应"""
        # 清理 markdown 代码块标记
        clean_content = content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:]
        if clean_content.startswith("```"):
            clean_content = clean_content[3:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        clean_content = clean_content.strip()

        try:
            parsed = json.loads(clean_content)
            industry_code = parsed.get("industry_code", "other")

            # 验证行业编码是否有效
            valid_codes = []
            for primary_code, primary_info in industry_hierarchy.items():
                valid_codes.append(primary_code)
                for child in primary_info['children']:
                    valid_codes.append(child['code'])

            if industry_code not in valid_codes:
                industry_code = "other"

            return {"industry_code": industry_code}

        except json.JSONDecodeError as e:
            return {"industry_code": "other"}

    def _parse_profile_response(self, content: str, candidates: List[str]) -> Dict[str, Any]:
        """解析档案生成响应"""
        # 清理 markdown 代码块标记
        clean_content = content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:]
        if clean_content.startswith("```"):
            clean_content = clean_content[3:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        clean_content = clean_content.strip()

        try:
            parsed = json.loads(clean_content)

            # 验证 similar_customers 是否在候选列表中
            similar_customers = parsed.get("similar_customers", [])
            if candidates:
                valid_similar = [name for name in similar_customers if name in candidates]
                parsed["similar_customers"] = valid_similar[:5]
            else:
                parsed["similar_customers"] = []

            return parsed

        except json.JSONDecodeError as e:
            return {
                "company_background": None,
                "company_website": None,
                "main_business": None,
                "similar_customers": [],
                "project_background": None
            }

    async def trigger_generation(
        self,
        customer_id: int,
        account_name: str,
        source_lead_id: Optional[int] = None,
        team_id: Optional[int] = None
    ):
        """
        触发档案生成（异步后台任务）
        """
        asyncio.create_task(
            self.generate_profile(
                customer_id=customer_id,
                account_name=account_name,
                source_lead_id=source_lead_id,
                team_id=team_id
            )
        )


customer_profile_service = CustomerProfileService()