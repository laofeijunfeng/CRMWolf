# CRMWolf 页面结构规范 - 表单页

**适用页面**：新建客户、新建合同、新建商机、新建跟进记录、编辑页面

---

## 一、页面组成

### 1.1 导航层级

```
Sidebar（一级导航，固定）
└── TopBar（顶部栏，固定）
    └── Form Area（表单区域，居中）
```

### 1.2 组件清单

| 位置 | 组件 | 高度 | 说明 |
|------|------|------|------|
| **左侧** | `SidebarV2` | 100vh | 全局菜单，固定不动 |
| **顶部** | `TopBarV2` | 56px | 包含返回按钮、标题 |
| **内容** | Form + Buttons | 自适应 | 表单 + 操作按钮 |

---

## 二、TopBar 布局（表单页）

### 2.1 三段式布局

| 区域 | 内容 | 示例 |
|------|------|------|
| **左侧（48px）** | 返回按钮 | `<` 返回上一页 |
| **中间（居中）** | 表单标题 | "新建客户" 或 "编辑客户" |
| **右侧（48px）** | 空白 | 无操作按钮（按钮在表单底部） |

---

## 三、表单布局规范

### 3.1 表单宽度

| 断点 | 宽度 |
|------|------|
| **xs** | 全宽（calc(100vw - 32px)） |
| **sm** | 600px（居中） |
| **md+** | 800px（居中） |

### 3.2 表单卡片

| 属性 | 值 |
|------|-----|
| **背景** | `#FFFFFF` |
| **圆角** | 6px |
| **阴影** | `0 1px 3px rgba(0,0,0,0.1)` |
| **内边距** | 24px |

### 3.3 表单分组

| 分组 | 说明 |
|------|------|
| **基本信息** | 客户名称、行业、城市等 |
| **联系信息** | 联系人姓名、电话、邮箱 |
| **其他信息** | 备注、附件等 |

**分组样式**：
- 分组标题：`13px`，字重 `600`，颜色 `#64748B`
- 分组间距：`24px`

---

## 四、表单字段规范

### 4.1 字段布局

| 断点 | 列数 |
|------|------|
| **xs** | 1 列（全宽） |
| **sm+** | 2 列（某些字段全宽，如备注） |

### 4.2 字段高度

| 元素 | 高度 |
|------|------|
| **Input** | 32px |
| **Select** | 32px |
| **Textarea** | 自适应（最小 80px） |

### 4.3 字段间距

| 元素 | 间距 |
|------|------|
| **Label 与 Input** | 8px |
| **字段之间** | 16px |
| **分组之间** | 24px |

---

## 五、标签规范

### 5.1 标签样式

| 属性 | 值 |
|------|-----|
| **字号** | 14px |
| **字重** | 500 |
| **颜色** | `#0F172A`（深色） |

### 5.2 必填标识

- **标识符**：红色星号 `*`
- **位置**：标签文字右侧
- **字号**：与标签相同

---

## 六、错误提示规范

### 6.1 错误位置

- **位置**：Input 下方，与 Input 左对齐
- **间距**：4px（Input 底部到错误文字）

### 6.2 错误样式

| 属性 | 值 |
|------|-----|
| **字号** | 13px |
| **颜色** | `#DC2626` |
| **图标** | ⚠️ 警告图标（可选） |

### 6.3 Input Error 状态

| 属性 | 值 |
|------|-----|
| **边框** | `2px #DC2626` |
| **背景** | `#FEE2E2`（淡红） |

---

## 七、操作按钮规范

### 7.1 按钮位置

- **位置**：表单底部，右对齐
- **间距**：按钮之间 8px

### 7.2 按钮样式

| 按钮 | 类型 | 优先级 |
|------|------|--------|
| **提交** | Primary | 最高 |
| **取消** | Default | 中等 |
| **保存草稿** | Default | 低（可选） |

---

## 八、Help Text 规范

### 8.1 Help Text 位置

- **位置**：Input 下方（在 Error 之上）
- **间距**：4px（Label 与 Help Text）

### 8.2 Help Text 样式

| 属性 | 值 |
|------|-----|
| **字号** | 13px |
| **颜色** | `#64748B` |
| **图标** | 无（纯文字） |

---

## 九、交互动效

### 9.1 Focus 状态

| 元素 | Focus 效果 | 过渡时间 |
|------|----------|---------|
| **Input** | 2px 边框 + 外发光 | 150ms |
| **Select** | 同 Input | 150ms |

### 9.2 Error 状态

| 元素 | Error 效果 | 过渡时间 |
|------|----------|---------|
| **Input** | 边框变红 + shake 动画 | 200ms |

---

## 十、代码示例

### 10.1 表单结构（伪代码）

```vue
<template>
  <div class="form-page">
    <!-- 左侧菜单 -->
    <SidebarV2 />
    
    <!-- 顶部栏 -->
    <TopBarV2>
      <template #left>
        <ButtonV2 size="sm" @click="goBack">返回</ButtonV2>
      </template>
      <template #center>
        <h1>新建客户</h1>
      </template>
    </TopBarV2>
    
    <!-- 表单区域 -->
    <main class="form-container">
      <div class="form-card">
        <!-- 分组1：基本信息 -->
        <div class="form-section">
          <h3>基本信息</h3>
          <div class="form-row">
            <div class="form-field">
              <label>客户名称 <span class="required">*</span></label>
              <InputV2 v-model="form.name" :error="errors.name" />
              <div v-if="errors.name" class="error-text">{{ errors.name }}</div>
            </div>
            <div class="form-field">
              <label>行业</label>
              <SelectV2 v-model="form.industry" />
            </div>
          </div>
          <!-- ... 更多字段 -->
        </div>
        
        <!-- 分组2：联系信息 -->
        <div class="form-section">
          <h3>联系信息</h3>
          <!-- ... -->
        </div>
        
        <!-- 操作按钮 -->
        <div class="form-actions">
          <ButtonV2 variant="default" @click="goBack">取消</ButtonV2>
          <ButtonV2 variant="primary" @click="submit">提交</ButtonV2>
        </div>
      </div>
    </main>
  </div>
</template>
```

---

## 十一、特殊场景

### 11.1 新建跟进记录（Modal）

**位置**：Modal 弹窗，而非独立页面

### 11.2 新建回款计划（QuickCreate Modal）

**位置**：合同详情页内的 QuickCreate Modal

---

**适用页面列表**：
- 新建客户（CustomerEdit.vue）
- 新建合同（ContractCreate.vue）
- 新建商机（OpportunityEdit.vue）
- 编辑客户（CustomerEdit.vue）
- 编辑合同（ContractCreate.vue）

**版本：V2 | 最后更新：2026-07-08**