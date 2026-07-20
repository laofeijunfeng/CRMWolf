"""
客户档案 AI 自动补充服务

负责在客户创建或线索转化后，异步调用 AI 生成客户档案信息
使用行业分级体系进行行业匹配和同行业客户筛选
"""
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import SessionLocal
from app.models.customer import Customer
from app.crud.customer import customer_crud
from app.crud.customer_follow_up import customer_follow_up_crud
from app.crud.industry import industry_crud
from app.crud.ai_config import ai_config_crud
from app.services.ai_task_limiter import ai_generation_semaphore
from app.services.ai_service import ai_service

logger = logging.getLogger(__name__)


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
        logger.info(f"开始生成客户档案: customer_id={customer_id}, team_id={team_id}")

        async with ai_generation_semaphore:
            try:
                # 1. 短连接读取配置和上下文，避免 AI 调用期间占用 DB 连接
                db = SessionLocal()
                try:
                    customer_crud.update_profile_status(db, customer_id, "GENERATING")
                    logger.info(f"状态已更新为 GENERATING: customer_id={customer_id}")

                    effective_team_id = team_id
                    if effective_team_id is None:
                        customer = db.query(Customer).filter(Customer.id == customer_id).first()
                        if not customer:
                            raise ValueError("客户不存在")
                        effective_team_id = customer.team_id

                    config = ai_config_crud.get_config(db, effective_team_id)
                    if not config:
                        raise ValueError("AI 配置未设置")

                    api_host = config.api_host
                    model_name = config.model_name
                    api_key = ai_config_crud.get_decrypted_api_key(db, effective_team_id)
                    if not api_key:
                        raise ValueError("无法获取 API Key")

                    logger.info(f"AI 配置获取成功: api_host={api_host}, model={model_name}")

                    industry_hierarchy = industry_crud.get_industry_hierarchy(db)
                    logger.info(f"行业层级结构获取成功，一级行业数量: {len(industry_hierarchy)}")

                    lead_follow_ups = None
                    if source_lead_id:
                        lead_follow_ups = customer_follow_up_crud.get_by_original_lead_id(db, source_lead_id)
                        logger.info(f"跟进记录数量: {len(lead_follow_ups) if lead_follow_ups else 0}")

                    prompt = self._build_prompt_for_industry(account_name, industry_hierarchy, lead_follow_ups)
                finally:
                    db.close()
                logger.info(f"第一阶段提示词构建完成，长度: {len(prompt)}")

                # 2. 第一次 AI 调用：判断行业
                logger.info("开始第一次 AI 调用：判断行业")
                full_content = await ai_service._stream_chat_collect(
                    api_host=api_host,
                    api_key=api_key,
                    model=model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt_for_industry()},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1024,
                    response_format={"type": "json_object"}
                )
                logger.info(f"第一次 AI 调用完成，响应长度: {len(full_content)}")

                # 3. 短连接写入行业并读取第二阶段上下文
                industry_data = self._parse_industry_response(full_content, industry_hierarchy)
                industry_code = industry_data.get("industry_code", "other")
                logger.info(f"行业解析结果: {industry_code}")

                db = SessionLocal()
                try:
                    customer_crud.update_industry(db, customer_id, industry_code)
                    logger.info(f"行业字段已更新: {industry_code}")

                    similar_customer_candidates = industry_crud.get_customers_by_industry(
                        db, industry_code, customer_id, effective_team_id, limit=50
                    )
                    logger.info(f"同行业客户候选数量: {len(similar_customer_candidates) if similar_customer_candidates else 0}")

                    prompt2 = self._build_prompt_for_profile(
                        account_name,
                        industry_code,
                        industry_hierarchy,
                        similar_customer_candidates,
                        lead_follow_ups
                    )
                finally:
                    db.close()
                logger.info(f"第二阶段提示词构建完成，长度: {len(prompt2)}")

                logger.info("开始第二次 AI 调用：生成完整档案")
                full_content2 = await ai_service._stream_chat_collect(
                    api_host=api_host,
                    api_key=api_key,
                    model=model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt_for_profile()},
                        {"role": "user", "content": prompt2}
                    ],
                    temperature=0.3,
                    max_tokens=2048,
                    response_format={"type": "json_object"}
                )
                logger.info(f"第二次 AI 调用完成，响应长度: {len(full_content2)}")

                # 4. 短连接写入档案
                profile_data = self._parse_profile_response(full_content2, similar_customer_candidates)
                logger.info(f"档案解析完成")

                db = SessionLocal()
                try:
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
                finally:
                    db.close()
                logger.info(f"客户档案更新完成: customer_id={customer_id}, status=COMPLETED")

                try:
                    from app.services.customer_brief_service import customer_brief_service
                    await customer_brief_service.trigger_generation(customer_id=customer_id, team_id=effective_team_id)
                except Exception as brief_error:
                    logger.warning("客户档案完成后触发客户概况生成失败: %s", brief_error)

                return {
                    "success": True,
                    "customer_id": customer_id,
                    "industry_code": industry_code,
                    "profile_data": profile_data
                }

            except Exception as e:
                logger.error(f"客户档案生成失败: customer_id={customer_id}, error={str(e)}")
                db = SessionLocal()
                try:
                    customer_crud.update_profile_status(
                        db,
                        customer_id,
                        "FAILED",
                        error_message=str(e)
                    )
                except Exception:
                    logger.exception("更新客户档案失败状态失败: customer_id=%s", customer_id)
                finally:
                    db.close()

                return {
                    "success": False,
                    "customer_id": customer_id,
                    "error": str(e)
                }

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
