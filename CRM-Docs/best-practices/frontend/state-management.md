# 状态管理规范

> 前端状态管理必须遵循此规范，确保状态可追踪、可维护。

---

## 状态分类

| 状态类型 | 存放位置 | 示例 |
|----------|----------|------|
| 全局状态 | Pinia Store | 用户信息、token、权限 |
| 页面状态 | Pinia Store（按模块） | 列表数据、筛选条件 |
| 组件内部状态 | Vue ref/reactive | 表单输入、展开状态 |

---

## 全局状态管理

### 🟢 推荐做法

使用 Pinia Store 管理全局状态：

```typescript
// stores/user.ts
export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    userInfo: null as UserInfo | null,
    permissions: [] as string[]
  }),
  
  actions: {
    setToken(token: string) {
      this.token = token
      localStorage.setItem('token', token)
    },
    
    logout() {
      this.token = ''
      this.userInfo = null
      localStorage.removeItem('token')
    }
  }
})

// 组件中使用
const userStore = useUserStore()
const token = computed(() => userStore.token)
```

### 🔴 禁止做法

```typescript
// ❌ 禁止在组件间共享 ref
const globalToken = ref('')  // 在 A 组件定义
export default globalToken   // 其他组件导入使用

// ❌ 禁止分散存储
localStorage.setItem('token', token)  // 多处直接操作
sessionStorage.setItem('userInfo', info)

// ❌ 禁止全局变量
window.token = token
```

---

## 页面状态管理

### 🟢 推荐做法

按业务模块创建 Store：

```typescript
// stores/customer.ts
export const useCustomerStore = defineStore('customer', {
  state: () => ({
    list: [] as Customer[],
    filters: {
      status: '',
      keyword: ''
    },
    pagination: {
      page: 1,
      pageSize: 10,
      total: 0
    }
  }),
  
  actions: {
    async fetchList() {
      const res = await request.get('/v1/customers/', { params: this.filters })
      this.list = res.data
      this.pagination.total = res.total
    },
    
    resetFilters() {
      this.filters = { status: '', keyword: '' }
      this.pagination.page = 1
    }
  }
})
```

### 🟡 可选做法

简单页面可以使用组件内状态：

```typescript
// 简单页面（无跨组件共享）
const list = ref<Customer[]>([])
const filters = ref({ status: '', keyword: '' })

onMounted(async () => {
  const res = await request.get('/v1/customers/')
  list.value = res.data
})
```

---

## 组件内部状态

### 🟢 推荐做法

```typescript
// 组件内部状态
const expanded = ref(false)
const formData = reactive({
  name: '',
  email: ''
})

// 表单输入使用 reactive
const form = reactive<CustomerCreate>({
  name: '',
  contact_phone: '',
  city: ''
})
```

### 🔴 禁止做法

```typescript
// ❌ 禁止组件间共享 ref（即使是父子）
// 父组件
const childData = ref({})
// 子组件通过 props 接收 ref 并直接修改
props.childData.value = newData  // 违反单向数据流
```

---

## 组件通信

### 父子组件通信

| 方向 | 推荐方式 | 禁止方式 |
|------|----------|----------|
| 父 → 子 | Props | 直接访问子组件属性 |
| 子 → 父 | Events (emit) | 直接修改父组件状态 |
| 双向 | v-model | 共享 ref |

```typescript
// 🟢 推荐：Props + Events
// 父组件
<ChildComponent :data="parentData" @update="handleUpdate" />

// 子组件
const props = defineProps<{ data: Customer }>()
const emit = defineEmits<{ update: [Customer] }>()

emit('update', newData)
```

### 跨组件通信

| 场景 | 推荐方式 |
|------|----------|
| 全局共享 | Pinia Store |
| 兄弟组件 | 共用同一个 Store |
| 嵌套深层 | provide/inject 或 Store |

---

## Store 命名规范

```typescript
// 模块 Store 命名：use + 模块名 + Store
useUserStore()       // 用户模块
useCustomerStore()   // 客户模块
useOpportunityStore() // 商机模块

// Store 文件命名：模块名.ts
stores/user.ts
stores/customer.ts
stores/opportunity.ts
```

---

## 状态持久化

### 🟢 推荐做法

```typescript
// Store 内统一处理持久化
export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
  }),
  
  actions: {
    setToken(token: string) {
      this.token = token
      localStorage.setItem('token', token)
    }
  }
})
```

### 🔴 禁止做法

```typescript
// ❌ 禁止多处分散操作 localStorage
// 组件 A
localStorage.setItem('token', token)
// 组件 B
const token = localStorage.getItem('token')
// 组件 C
localStorage.removeItem('token')
```

---

## 相关文档

- [components.md](components.md) - 组件通信规范