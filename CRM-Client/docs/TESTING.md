# 测试规范 - CRMWolf

**适用范围**：CRMWolf 全项目（前端 + 后端）

---

## 一、前端单元测试（Vitest）

### 1.1 测试文件模板

```typescript
// tests/components/CustomerCard.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import CustomerCard from '@/components/CustomerCard.vue'
import type { CustomerResponse } from '@/schemas/customer'
import { createPinia, setActivePinia } from 'pinia'

// Mock 数据（遵循 TYPESCRIPT.md 类型）
const mockCustomer: CustomerResponse = {
  id: 1,
  account_name: '测试公司',
  industry: '互联网',
  city: '北京',
  address: '北京市朝阳区',
  company_scale: '51-200',
  source: '线上注册',
  status: '0',
  owner_id: 'ou_test123',
  source_lead_id: null,
  default_procurement_method_id: null,
  return_reason: null,
  returned_time: null,
  creator_id: 'ou_test123',
  created_time: '2024-01-01T00:00:00',
  last_modified_time: '2024-01-01T00:00:00',
  version: 1
}

describe('CustomerCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders customer name correctly', () => {
    const wrapper = mount(CustomerCard, {
      props: { customer: mockCustomer }
    })
    expect(wrapper.text()).toContain('测试公司')
  })

  it('emits update event on save button click', async () => {
    const wrapper = mount(CustomerCard, {
      props: { customer: mockCustomer, mode: 'edit' }
    })
    await wrapper.find('.save-btn').trigger('click')
    expect(wrapper.emitted('update')).toBeTruthy()
  })

  it('shows loading state when loading prop is true', () => {
    const wrapper = mount(CustomerCard, {
      props: { customer: mockCustomer, loading: true }
    })
    expect(wrapper.find('.loading-spinner').exists()).toBe(true)
  })

  it('hides edit button when user lacks permission', async () => {
    const wrapper = mount(CustomerCard, {
      props: { customer: mockCustomer }
    })
    expect(wrapper.find('.edit-btn').exists()).toBe(false)
  })
})
```

### 1.2 API 测试模板

```typescript
// tests/api/customer.test.ts
import { describe, it, expect, vi } from 'vitest'
import { customerApi } from '@/api/customer'
import { CustomerListResponseSchema } from '@/schemas/customer'

// Mock axios
vi.mock('@/utils/request', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn()
  }
}))

describe('customerApi', () => {
  it('getList returns valid CustomerListResponse', async () => {
    const mockResponse = {
      data: [mockCustomer],
      total: 1,
      page: 1,
      pageSize: 20
    }
    vi.mocked(request.get).mockResolvedValue(mockResponse)

    const result = await customerApi.getList({ page: 1, pageSize: 20 })

    // Zod 校验
    expect(() => CustomerListResponseSchema.parse(result)).not.toThrow()
  })
})
```

### 1.3 Store 测试模板

```typescript
// tests/stores/customer.test.ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useCustomerStore } from '@/stores/customer'

describe('useCustomerStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('initializes with empty items', () => {
    const store = useCustomerStore()
    expect(store.items).toEqual([])
    expect(store.loading).toBe(false)
  })

  it('fetchList populates items', async () => {
    const store = useCustomerStore()
    vi.mock('@/api/customer').mockResolvedValue({
      data: [mockCustomer],
      total: 1
    })

    await store.fetchList(1, 20)

    expect(store.items.length).toBe(1)
    expect(store.total).toBe(1)
  })
})
```

---

## 二、后端单元测试（pytest）

### 2.1 测试文件模板

```python
# tests/unit/test_customer_service.py
import pytest
from unittest.mock import Mock, patch
from app.services.customer_service import CustomerService
from app.schemas.customer import CustomerCreate, CustomerResponse
from app.core.exceptions import ConflictException

class TestCustomerService:
    """客户服务单元测试"""

    @pytest.fixture
    def mock_db(self):
        """Mock 数据库会话"""
        return Mock()

    @pytest.fixture
    def customer_create_data(self):
        """测试创建数据"""
        return CustomerCreate(
            account_name="测试公司",
            city="北京",
            industry="互联网"
        )

    def test_create_customer_success(self, mock_db, customer_create_data):
        """测试成功创建客户"""
        result = CustomerService.create(mock_db, customer_create_data)

        assert result.account_name == "测试公司"
        assert result.city == "北京"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_create_customer_duplicate_name_raises_conflict(
        self, mock_db, customer_create_data
    ):
        """测试重复名称抛出冲突异常"""
        # Mock 查询返回已存在客户
        mock_db.execute.return_value.scalar_one_or_none.return_value = Mock()

        with pytest.raises(ConflictException) as exc_info:
            CustomerService.create(mock_db, customer_create_data)

        assert "已存在" in str(exc_info.value)

    def test_get_customer_by_id_returns_customer(self, mock_db):
        """测试根据ID获取客户"""
        mock_customer = Mock(
            id=1,
            account_name="测试公司",
            city="北京"
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_customer

        result = CustomerService.get_by_id(mock_db, 1)

        assert result.id == 1
        assert result.account_name == "测试公司"
```

### 2.2 CRUD 测试模板

```python
# tests/unit/test_customer_crud.py
import pytest
from app.crud.customer import CustomerCRUD
from app.schemas.customer import CustomerCreate

class TestCustomerCRUD:
    """客户 CRUD 单元测试"""

    def test_get_multi_returns_paginated_results(self, mock_db):
        """测试分页查询"""
        mock_customers = [Mock(id=i) for i in range(5)]
        mock_db.execute.return_value.all.return_value = mock_customers

        result, count = CustomerCRUD.get_multi(mock_db, skip=0, limit=5)

        assert len(result) == 5
        assert count == 5

    def test_create_sets_creator_id(self, mock_db):
        """测试创建时设置创建人"""
        data = CustomerCreate(account_name="测试", city="北京")
        user_id = "ou_test123"

        result = CustomerCRUD.create_with_owner(mock_db, data, user_id)

        assert result.creator_id == user_id
```

---

## 三、覆盖率要求

| 代码类型 | 覆盖率要求 | 校验时机 |
|----------|------------|----------|
| 新增组件 | 100% | pre-push |
| 新增 Store | 100% | pre-push |
| 新增 API | 100% | pre-push |
| 新增 Service | 100% | pre-push |
| 存量代码 | ≥80% | CI |

---

## 四、测试命名规范

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| 前端测试 | `[module].test.ts` | `customer.test.ts` |
| 后端测试 | `test_[module].py` | `test_customer_service.py` |
| 测试目录 | `tests/unit/`, `tests/integration/` | 分层存放 |

---

## 五、测试运行命令

### 前端

```bash
# 运行所有测试
npm run test:unit

# 运行特定文件
npm run test:unit -- customer.test.ts

# 生成覆盖率报告
npm run coverage
```

### 后端

```bash
# 运行单元测试
pytest tests/unit -v

# 生成覆盖率报告
pytest tests/unit --cov=app --cov-report=html
```

---

## 六、禁止行为

| 禁止 | 原因 |
|------|------|
| 跳过测试（`.skip`） | 违反覆盖率要求 |
| Mock 数据使用 any | 违反类型安全 |
| 不写测试直接提交 | 违反红线 |
| 测试不覆盖边界情况 | 测试不完整 |

---

## 七、校验规则

| 校验点 | 工具 | 时机 |
|--------|------|------|
| 测试存在 | Git hooks 文件检测 | pre-push |
| 覆盖率 | Vitest/pytest coverage | pre-push |
| 测试通过 | Vitest/pytest | pre-push |

---

**版本：1.0 | 最后更新：2026-04-21 | 修改需人工审批**