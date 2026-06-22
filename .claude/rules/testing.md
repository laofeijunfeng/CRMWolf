# 测试规则

**适用范围**：CRMWolf 全项目测试

---

## 覆盖率要求

| 代码类型 | 覆盖率要求 | 校验时机 |
|----------|------------|----------|
| 新增组件 | 100% | pre-push |
| 新增 Store | 100% | pre-push |
| 新增 API | 100% | pre-push |
| 新增 Service | 100% | pre-push |
| 存量代码 | ≥80% | CI |

---

## 前端测试规范（Vitest）

### 测试文件命名

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| 组件测试 | `[module].test.ts` | `customer.test.ts` |
| Store 测试 | `[module].test.ts` | `customer.test.ts` |
| API 测试 | `[module].test.ts` | `customer.test.ts` |

### Mock 数据规范

| 规则 | 要求 |
|------|------|
| Mock 类型 | 必须遵循 TYPESCRIPT.md 类型 |
| 禁止 any | Mock 数据禁止使用 any |

### 运行命令

```bash
npm run test:unit                 # 运行所有测试
npm run test:unit -- file.test.ts # 运行特定文件
npm run coverage                  # 生成覆盖率报告
```

---

## 后端测试规范（pytest）

### 测试文件命名

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| 单元测试 | `test_[module].py` | `test_customer_service.py` |
| CRUD 测试 | `test_[module]_crud.py` | `test_customer_crud.py` |

### 测试类结构

```python
class TestCustomerService:
    """客户服务单元测试"""

    @pytest.fixture
    def mock_db(self):
        return Mock()

    def test_create_customer_success(self, mock_db):
        ...
```

### 运行命令

```bash
pytest tests/unit -v                     # 运行单元测试
pytest tests/unit --cov=app              # 生成覆盖率报告
pytest tests/unit --cov=app --cov-report=html  # HTML 报告
```

---

## 禁止行为汇总

| 禁止 | 原因 |
|------|------|
| 跳过测试（`.skip`） | 违反覆盖率要求 |
| Mock 数据使用 any | 违反类型安全 |
| 不写测试直接提交 | 违反红线 |
| 测试不覆盖边界情况 | 测试不完整 |

---

## 校验规则

| 校验点 | 工具 | 时机 |
|--------|------|------|
| 测试存在 | Git hooks 文件检测 | pre-push |
| 覆盖率 | Vitest/pytest coverage | pre-push |
| 测试通过 | Vitest/pytest | pre-push |

---

**详细参考**：`CRM-Client/docs/TESTING.md`