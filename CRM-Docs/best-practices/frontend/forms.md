# 表单处理规范

> 前端表单开发必须遵循此规范，确保校验逻辑统一、可维护。

---

## 表单校验原则

### 🟢 推荐做法：Schema 校验

使用统一的校验 Schema，而非分散的校验规则：

```typescript
// 定义校验 Schema
const customerSchema = {
  name: [
    { required: true, message: '请输入客户名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度 2-50 字符', trigger: 'blur' }
  ],
  contact_phone: [
    { required: true, message: '请输入联系电话', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号', trigger: 'blur' }
  ],
  city: [
    { required: true, message: '请选择城市', trigger: 'change' }
  ]
}

// 表单中使用
<el-form :model="form" :rules="customerSchema" ref="formRef">
  <el-form-item label="客户名称" prop="name">
    <el-input v-model="form.name" />
  </el-form-item>
</el-form>
```

### 🔴 禁止做法

```typescript
// ❌ 禁止分散定义校验规则
<el-form-item label="客户名称" :rules="[{ required: true }]">
  ...
</el-form-item>
<el-form-item label="联系电话" :rules="[{ required: true }]">
  ...
</el-form-item>

// ❌ 禁止手写分散的校验逻辑
const validateName = () => {
  if (!form.name) {
    ElMessage.error('请输入客户名称')
    return false
  }
  return true
}
const validatePhone = () => { ... }
const validateAll = () => validateName() && validatePhone() && ...
```

---

## 表单状态管理

### 🟢 推荐做法

```typescript
// 使用 reactive 统一管理表单状态
const form = reactive<CustomerCreate>({
  name: '',
  contact_phone: '',
  city: '',
  source: '',
  company_scale: ''
})

// 提交时统一处理
const handleSubmit = async () => {
  const valid = await formRef.value?.validate()
  if (!valid) return
  
  try {
    await request.post('/v1/customers/', form)
    ElMessage.success('创建成功')
    emit('success')
  } catch (error) {
    ElMessage.error('创建失败')
  }
}
```

### 🔴 禁止做法

```typescript
// ❌ 禁止分散的 ref
const name = ref('')
const phone = ref('')
const city = ref('')

// ❌ 禁止直接操作 DOM
document.querySelector('#name').value
```

---

## 表单重置

### 🟢 推荐做法

```typescript
// 使用 resetFields 方法
const handleReset = () => {
  formRef.value?.resetFields()
}

// 或手动重置 reactive 对象
const initialForm = {
  name: '',
  contact_phone: '',
  city: ''
}
const form = reactive({ ...initialForm })

const handleReset = () => {
  Object.assign(form, initialForm)
}
```

---

## 动态表单

### 🟢 推荐做法

```typescript
// 动态表单项使用数组
const dynamicForm = reactive({
  items: [
    { label: '字段1', value: '' },
    { label: '字段2', value: '' }
  ]
})

// 动态校验
const getRules = (index: number) => ({
  value: [{ required: true, message: `请填写${dynamicForm.items[index].label}` }]
})

<el-form-item v-for="(item, index) in dynamicForm.items" :key="index" :prop="`items.${index}.value`" :rules="getRules(index)">
  <el-input v-model="item.value" />
</el-form-item>
```

---

## 异步校验

### 🟢 推荐做法

```typescript
// 异步校验使用 validator 函数
const checkPhoneUnique = async (rule: any, value: string) => {
  if (!value) return true
  const res = await request.get('/v1/customers/check-phone', { params: { phone: value } })
  if (res.exists) {
    throw new Error('电话号码已存在')
  }
  return true
}

const schema = {
  contact_phone: [
    { required: true, message: '请输入联系电话', trigger: 'blur' },
    { validator: checkPhoneUnique, trigger: 'blur' }
  ]
}
```

---

## 表单提交防重复

### 🟢 推荐做法

```typescript
// 使用 loading 状态
const submitting = ref(false)

const handleSubmit = async () => {
  if (submitting.value) return  // 防重复
  
  const valid = await formRef.value?.validate()
  if (!valid) return
  
  submitting.value = true
  try {
    await request.post('/v1/customers/', form)
    ElMessage.success('创建成功')
  } finally {
    submitting.value = false
  }
}

<el-button :loading="submitting" @click="handleSubmit">提交</el-button>
```

---

## 复用校验规则

### 🟢 推荐做法：抽取公共校验

```typescript
// utils/validators.ts
export const commonRules = {
  phone: [
    { required: true, message: '请输入联系电话' },
    { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号' }
  ],
  email: [
    { type: 'email', message: '请输入正确的邮箱格式' }
  ],
  required: (label: string) => [
    { required: true, message: `请输入${label}`, trigger: 'blur' }
  ]
}

// 组件中复用
import { commonRules } from '@/utils/validators'

const schema = {
  contact_phone: commonRules.phone,
  email: commonRules.email,
  name: commonRules.required('客户名称')
}
```

---

## 相关文档

- [components.md](components.md) - 组件开发规范
- [state-management.md](state-management.md) - 状态管理规范