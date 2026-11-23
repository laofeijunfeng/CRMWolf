"""
行业分级 API 接口

提供行业层级结构的查询接口
"""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.crud.industry import industry_crud
from app.schemas.industry import IndustryHierarchyResponse

router = APIRouter(prefix="/v1/industries", tags=["行业管理"])


@router.get("/hierarchy", response_model=IndustryHierarchyResponse, summary="获取行业层级结构", description="""
获取完整的行业层级结构\uff08一级 + 二级行业\uff09。

**返回格式\uff1a**
```json
{
  "primary_code": {
    "name": "一级行业名称",
    "children": [
      {"code": "secondary_code", "name": "二级行业名称"}
    ]
  }
}
```

**用途\uff1a**
- 前端行业选择器
- AI 提示词构建
""")
def get_industry_hierarchy(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return industry_crud.get_industry_hierarchy(db)


@router.get("/primary", response_model=list[dict[str, Any]], summary="获取一级行业列表", description="""
获取所有一级行业列表。

**返回字段\uff1a**
- id: 行业ID
- code: 行业编码
- name: 行业名称
- sort_order: 排序
""")
def get_primary_industries(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    industries = industry_crud.get_all_primary(db)
    return [
        {
            "id": i.id,
            "code": i.code,
            "name": i.name,
            "sort_order": i.sort_order
        }
        for i in industries
    ]


@router.get("/secondary", response_model=list[dict[str, Any]], summary="获取二级行业列表", description="""
获取所有二级行业列表。

**返回字段\uff1a**
- id: 行业ID
- code: 行业编码
- name: 行业名称
- parent_code: 父行业编码
- parent_name: 父行业名称
- sort_order: 排序
""")
def get_secondary_industries(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    industries = industry_crud.get_all_secondary(db)
    result = []
    for i in industries:
        parent = industry_crud.get_by_id(db, i.parent_id)
        result.append({
            "id": i.id,
            "code": i.code,
            "name": i.name,
            "parent_code": parent.code if parent else None,
            "parent_name": parent.name if parent else None,
            "sort_order": i.sort_order
        })
    return result


@router.get(
    "/secondary/by-parent/{parent_code}",
    response_model=list[dict[str, Any]],
    summary="根据父行业获取二级行业",
    description="""
根据一级行业编码获取其所有二级行业。

**路径参数\uff1a**
- parent_code: 一级行业编码

**用途\uff1a**
- 级联选择器\uff1a先选一级行业\uff0c再选二级行业
""",
)
def get_secondary_by_parent(
    parent_code: str,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    industries = industry_crud.get_secondary_by_parent(db, parent_code)
    return [
        {
            "id": i.id,
            "code": i.code,
            "name": i.name,
            "sort_order": i.sort_order
        }
        for i in industries
    ]