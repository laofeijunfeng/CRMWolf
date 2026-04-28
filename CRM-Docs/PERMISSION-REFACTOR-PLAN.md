# 权限码规范化重构方案

## 一、现状分析

### 1.1 格式统计

| 格式 | 数量 | 占比 |
|------|------|------|
| 两层 `resource:action` | 82 | 76% |
| 三层 `resource:action:scope` | 26 | 24% |
| **总计** | 108 | - |

### 1.2 主要问题

#### 问题 1：同一模块格式不一致

```
# customer 模块混用两种格式
customer:view_own      (两层) ← 旧格式
customer:view:own      (三层) ← 新格式
customer:edit_own      (两层) ← 应为 customer:edit:own
customer:contact:create (三层) ← 子资源用三层
```

#### 问题 2：语义重复

| 重复权限 | 建议保留 | 建议删除 |
|---------|---------|---------|
| `opportunity:update` vs `opportunity:edit_all/own` | `edit:all/own` | `update` |
| `customer:update` vs `customer:edit_all/own` | `edit:all/own` | `update` |
| `customer:delete` vs `customer:delete_own` | `delete:own` | `delete` |
| `finance:view_receivables` vs `finance:receivables_view` | `receivables:view` | `view_receivables` |
| `opportunity:stage` vs `opportunity:stage:*` | `stage:*` 系列 | `stage` |
| `opportunity:delete` vs `opportunity:delete_own` | `delete:own` | `delete` |
| `*:list`, `*:read` vs `*:view:*` | 保留开放接口用途 | - |

#### 问题 3：命名风格混乱

| 风格 | 示例 | 问题 |
|------|------|------|
| `_own/_all` 后缀 | `view_own`, `edit_all` | 与三层格式冲突 |
| 动词形式 | `create`, `update`, `delete` | 无范围区分 |
| 名词形式 | `list`, `read` | 与 `view` 语义重叠 |
| 复合动词 | `mark_issued`, `submit_approval` | 不符合规范 |

#### 问题 4：子资源处理不一致

```
# 有三层格式
lead:follow_up:create
customer:contact:create
customer:follow_up:create

# 无三层格式
customer:create       ← 主资源，无范围
```

### 1.3 角色权限分配现状

| 角色 | 权限数 | 备注 |
|------|--------|------|
| SYSTEM_ADMIN | 89 | 系统管理员 |
| SALES_DIRECTOR | 76 | 销售总监 |
| SALES_MEMBER | 42 | 销售成员 |
| FINANCE | 16 | 财务人员 |

---

## 二、规范化方案

### 2.1 统一格式定义

**三层格式**：`{resource}:{action}:{scope}`

| 层级 | 说明 | 可选值 |
|------|------|--------|
| resource | 资源模块 | `lead`, `customer`, `opportunity`, `contract`, `payment`, `invoice` 等 |
| action | 操作类型 | `create`, `view`, `edit`, `delete`, `approve`, `assign`, `convert` 等 |
| scope | 权限范围 | `own`（自己的）、`all`（全部）、`team`（团队）、`public`（公海） |

**特殊格式**：
- 子资源：`{resource}:{sub_resource}:{action}`（无需 scope，默认 own）
- 开放接口：`{resource}:api:{action}`（API 专用权限）
- 系统权限：`{module}:{action}`（无 scope，全局权限）

### 2.2 Action 标准词汇表

| Action | 说明 | 适用资源 |
|--------|------|---------|
| `create` | 创建 | 全部核心资源 |
| `view` | 查看 | 全部核心资源 |
| `edit` | 编辑 | 全部核心资源 |
| `delete` | 删除 | 全部核心资源 |
| `approve` | 审批 | contract, invoice |
| `assign` | 分配 | lead, customer, opportunity |
| `claim` | 领取 | lead, customer |
| `convert` | 转化 | lead |
| `return` | 退回公海 | lead, customer |
| `import` | 导入 | lead |
| `win` | 赢单 | opportunity |
| `lose` | 输单 | opportunity |
| `confirm` | 确认入账 | payment |
| `register` | 登记 | payment |
| `manage` | 管理 | user, role, permission, system |

### 2.3 Scope 标准词汇表

| Scope | 说明 | 适用场景 |
|-------|------|---------|
| `own` | 仅自己的数据 | 销售/跟进人员默认权限 |
| `all` | 全部数据 | 管理员/总监权限 |
| `team` | 团队数据 | 团队负责人权限 |
| `public` | 公海数据 | 公海领取/分配权限 |

---

## 三、权限映射表

### 3.1 线索管理 (lead)

| 新权限码 | 说明 | 映射旧权限 |
|---------|------|-----------|
| `lead:create` | 创建线索 | `lead:create` |
| `lead:view:own` | 查看自己的线索 | `lead:view_own`, `lead:read` |
| `lead:view:all` | 查看所有线索 | `lead:view_all`, `lead:list` |
| `lead:edit:own` | 编辑自己的线索 | `lead:edit_own` |
| `lead:edit:all` | 编辑所有线索 | `lead:edit_all` |
| `lead:delete:own` | 删除自己的线索 | `lead:delete_own` |
| `lead:assign` | 分配线索 | `lead:assign` |
| `lead:claim` | 领取线索 | `lead:claim` |
| `lead:convert` | 转化线索 | `lead:convert` |
| `lead:return` | 退回公海 | `lead:return_to_pool` |
| `lead:import` | 导入线索 | `lead:import` |
| `lead:follow_up:create` | 创建跟进 | `lead:follow_up:create` |

### 3.2 客户管理 (customer)

| 新权限码 | 说明 | 映射旧权限 |
|---------|------|-----------|
| `customer:create` | 创建客户 | `customer:create` |
| `customer:view:own` | 查看自己的客户 | `customer:view_own`, `customer:view:own`, `customer:read` |
| `customer:view:all` | 查看所有客户 | `customer:view_all`, `customer:list` |
| `customer:edit:own` | 编辑自己的客户 | `customer:edit_own`, `customer:update` |
| `customer:edit:all` | 编辑所有客户 | `customer:edit_all` |
| `customer:delete:own` | 删除自己的客户 | `customer:delete_own`, `customer:delete` |
| `customer:assign` | 分配客户 | `customer:assign` |
| `customer:claim` | 领取客户 | `customer:claim` |
| `customer:return` | 退回公海 | `customer:return_to_pool` |
| `customer:contact:create` | 创建联系人 | `customer:contact:create` |
| `customer:contact:edit` | 编辑联系人 | `customer:contact:edit` |
| `customer:contact:delete` | 删除联系人 | `customer:contact:delete` |
| `customer:follow_up:create` | 创建跟进 | `customer:follow_up:create` |
| `customer:follow_up:edit` | 编辑跟进 | `customer:follow_up:edit` |
| `customer:follow_up:delete` | 删除跟进 | `customer:follow_up:delete` |

### 3.3 商机管理 (opportunity)

| 新权限码 | 说明 | 映射旧权限 |
|---------|------|-----------|
| `opportunity:create` | 创建商机 | `opportunity:create` |
| `opportunity:view:own` | 查看自己的商机 | `opportunity:view_own`, `opportunity:view:own`, `opportunity:read` |
| `opportunity:view:all` | 查看所有商机 | `opportunity:view_all`, `opportunity:list` |
| `opportunity:edit:own` | 编辑自己的商机 | `opportunity:edit_own`, `opportunity:update` |
| `opportunity:edit:all` | 编辑所有商机 | `opportunity:edit_all` |
| `opportunity:delete:own` | 删除自己的商机 | `opportunity:delete_own`, `opportunity:delete` |
| `opportunity:assign` | 分配商机 | `opportunity:assign` |
| `opportunity:win` | 赢单 | `opportunity:win` |
| `opportunity:lose` | 输单 | `opportunity:lose` |
| `opportunity:stage:create` | 创建阶段模板 | `opportunity:stage:create` |
| `opportunity:stage:edit` | 编辑阶段模板 | `opportunity:stage:update` |
| `opportunity:stage:delete` | 删除阶段模板 | `opportunity:stage:delete` |
| `opportunity:analytics:view` | 查看分析 | `opportunity:analytics:view` |

### 3.4 合同管理 (contract)

| 新权限码 | 说明 | 映射旧权限 |
|---------|------|-----------|
| `contract:create` | 创建合同 | `contract:create` |
| `contract:view:own` | 查看自己的合同 | `contract:view_own`, `contract:read` |
| `contract:view:all` | 查看所有合同 | `contract:view_all`, `contract:list` |
| `contract:edit:own` | 编辑自己的合同 | `contract:edit_own` |
| `contract:edit:all` | 编辑所有合同 | `contract:edit_all` |
| `contract:delete:own` | 删除自己的合同 | `contract:delete_own` |
| `contract:approve:own` | 审批自己创建的 | `contract:approve_own` |
| `contract:approve:all` | 审批所有合同 | `contract:approve_all` |
| `contract:submit` | 提交审批 | `contract:submit_approval` |
| `contract:cancel` | 撤回审批 | `contract:cancel_approval` |

### 3.5 回款管理 (payment)

| 新权限码 | 说明 | 映射旧权限 |
|---------|------|-----------|
| `payment:plan:create` | 创建回款计划 | `payment:plan:create` |
| `payment:plan:edit` | 编辑回款计划 | `payment:plan:edit` |
| `payment:plan:delete` | 删除回款计划 | `payment:plan:delete` |
| `payment:plan:view:own` | 查看自己的计划 | `payment:plan:view_own` |
| `payment:plan:view:all` | 查看所有计划 | `payment:plan:view_all` |
| `payment:view:own` | 查看自己的回款 | `payment:view_own`, `payment:read` |
| `payment:view:all` | 查看所有回款 | `payment:view_all`, `payment:list` |
| `payment:register` | 登记回款 | `payment:register` |
| `payment:confirm` | 确认入账 | `payment:confirm` |

### 3.6 发票管理 (invoice)

| 新权限码 | 说明 | 映射旧权限 |
|---------|------|-----------|
| `invoice:create` | 创建发票申请 | `invoice:create` |
| `invoice:view:own` | 查看自己的发票 | `invoice:view_own`, `invoice:read` |
| `invoice:view:all` | 查看所有发票 | `invoice:view_all`, `invoice:list` |
| `invoice:approve` | 审批发票 | `invoice:approve` |
| `invoice:issue` | 标记已开票 | `invoice:mark_issued` |

### 3.7 财务管理 (finance)

| 新权限码 | 说明 | 映射旧权限 |
|---------|------|-----------|
| `finance:receivables:view` | 查看应收账款 | `finance:receivables_view`, `finance:view_receivables` |
| `finance:reports:view` | 查看财务报表 | `finance:reports_view` |
| `finance:audit:view` | 查看审计日志 | `finance:audit_logs` |

### 3.8 系统管理

| 新权限码 | 说明 | 映射旧权限 |
|---------|------|-----------|
| `user:manage` | 管理用户 | `user:manage` |
| `role:manage` | 管理角色 | `role:manage` |
| `permission:manage` | 管理权限 | `permission:manage` |
| `system:config` | 系统配置 | `system:config` |
| `ai:manage` | AI 配置管理 | `ai:manage` |
| `ai:view` | AI 配置查看 | `ai:read` |
| `apikey:manage` | 管理 API Key | `apikey:manage` |
| `approval:flow:create` | 创建审批流程 | `approval:flow:create` |
| `approval:flow:edit` | 编辑审批流程 | `approval:flow:update` |
| `statistics:view` | 查看统计 | `statistics:view` |
| `report:view:own` | 查看报表 | `report:view` |
| `report:view:team` | 查看团队报表 | `report:view:team` |

### 3.9 采购管理 (procurement)

| 新权限码 | 说明 | 映射旧权限 |
|---------|------|-----------|
| `procurement_method:view` | 查看采购方式 | `procurement_method:view` |
| `procurement_method:create` | 创建采购方式 | `procurement_method:create` |
| `procurement_method:edit` | 编辑采购方式 | `procurement_method:update` |
| `procurement_method:delete` | 删除采购方式 | `procurement_method:delete` |
| `procurement_stage:view` | 查看阶段模板 | `procurement_stage:view` |
| `procurement_stage:create` | 创建阶段模板 | `procurement_stage:create` |
| `procurement_stage:edit` | 编辑阶段模板 | `procurement_stage:update` |
| `procurement_stage:delete` | 删除阶段模板 | `procurement_stage:delete` |

---

## 四、删除的冗余权限

| 删除的权限码 | 原因 |
|-------------|------|
| `opportunity:update` | 与 `edit:own/all` 重复 |
| `customer:update` | 与 `edit:own/all` 重复 |
| `customer:delete` | 与 `delete:own` 重复 |
| `opportunity:delete` | 与 `delete:own` 重复 |
| `opportunity:stage` | 与 `stage:*` 系列重复 |
| `opportunity:stage:manage` | 语义不清，分解到具体操作 |
| `finance:view_receivables` | 与 `receivables:view` 重复 |
| `finance:audit_logs` | 改为 `audit:view` |

---

## 五、开放接口权限保留

以下权限用于 API 开放接口，与 Web 权限分离：

| 权限码 | 说明 | 保留原因 |
|-------|------|---------|
| `lead:api:list` | API 线索列表 | 原名 `lead:list` |
| `lead:api:read` | API 线索详情 | 原名 `lead:read` |
| `customer:api:list` | API 客户列表 | 原名 `customer:list` |
| `customer:api:read` | API 客户详情 | 原名 `customer:read` |
| `opportunity:api:list` | API 商机列表 | 原名 `opportunity:list` |
| `opportunity:api:read` | API 商机详情 | 原名 `opportunity:read` |
| `contract:api:list` | API 合同列表 | 原名 `contract:list` |
| `contract:api:read` | API 合同详情 | 原名 `contract:read` |
| `payment:api:list` | API 回款列表 | 原名 `payment:list` |
| `payment:api:read` | API 回款详情 | 原名 `payment:read` |
| `payment:api:create` | API 创建回款 | 原名 `payment:create` |
| `invoice:api:list` | API 发票列表 | 原名 `invoice:list` |
| `invoice:api:read` | API 发票详情 | 原名 `invoice:read` |

---

## 六、迁移执行计划

### 6.1 数据迁移步骤

1. **创建新权限码**（INSERT）
   - 按映射表创建新的权限记录
   - 保留旧权限记录（暂不删除）

2. **更新角色权限关联**（UPDATE role_permissions）
   - 根据映射关系，将角色关联到新权限
   - 保留旧关联（双轨运行）

3. **更新 Action 配置**（UPDATE ai_skill_actions）
   - 将所有 Action 的 `permission_code` 改为新格式

4. **更新代码中的硬编码权限检查**
   - 搜索代码中的权限码字符串
   - 替换为新格式

5. **清理旧数据**（DELETE）
   - 等待验证无误后，删除旧权限和旧关联

### 6.2 需要更新的代码文件

| 文件 | 更新内容 |
|------|---------|
| `scripts/reassign_role_permissions.py` | 权限分配脚本 |
| `scripts/migrate_complete_permissions.py` | 权限迁移脚本 |
| `scripts/migrate_skills_to_db.py` | Skill 迁移脚本 |
| `scripts/migrate_opportunity_stage_skill.py` | 商机阶段 Skill |
| `app/services/ai_skill_main.py` | 权限检查方法（可能需要兼容逻辑） |

### 6.3 兼容性处理

建议在 `_check_permission` 方法中增加兼容逻辑：

```python
def _check_permission(self, db: Session, user_id: int, permission_code: str) -> bool:
    """检查用户是否有指定权限（支持新旧格式兼容）"""
    permissions = permission_service.get_user_permissions_from_db(db, user_id)

    # 精确匹配
    for p in permissions:
        if p.code == permission_code:
            return True

    # 兼容匹配：旧格式自动映射到新格式
    normalized_code = self._normalize_permission_code(permission_code)
    for p in permissions:
        if p.code == normalized_code:
            return True

    return False

def _normalize_permission_code(self, code: str) -> str:
    """规范化权限码（将旧格式转为新格式）"""
    # view_own -> view:own
    # edit_all -> edit:all
    mapping = {
        'view_own': 'view:own',
        'view_all': 'view:all',
        'edit_own': 'edit:own',
        'edit_all': 'edit:all',
        'delete_own': 'delete:own',
        'delete_all': 'delete:all',
    }
    for old, new in mapping.items():
        if code.endswith(old):
            resource = code.rsplit(':', 1)[0]
            return f'{resource}:{new}'
    return code
```

---

## 七、验证清单

- [ ] 新权限码已创建
- [ ] 角色权限关联已更新
- [ ] Action 配置已更新
- [ ] 代码硬编码已替换
- [ ] 权限缓存已清除
- [ ] AI Skill 权限检查正常
- [ ] Web 界面权限检查正常
- [ ] 旧权限已清理

---

**版本：1.0 | 创建时间：2026-04-28**