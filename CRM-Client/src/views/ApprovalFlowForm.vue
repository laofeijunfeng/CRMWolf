<template>
  <div class="approval-flow-form-container">
    <div class="form-content">
      <el-row :gutter="16">
        <el-col :span="14">
          <el-card header="基本信息" class="form-card">
            <el-form
              ref="formRef"
              :model="form"
              :rules="rules"
              label-position="top"
              @submit.prevent="handleSubmit"
            >
              <el-form-item label="流程名称" prop="flow_name" required>
                <el-input
                  v-model="form.flow_name"
                  placeholder="请输入流程名称"
                  maxlength="100"
                  show-word-limit
                />
              </el-form-item>

              <el-form-item label="流程编码" prop="flow_code" required>
                <el-input
                  v-model="form.flow_code"
                  placeholder="请输入流程编码，如：CONTRACT_DEFAULT"
                  maxlength="50"
                  show-word-limit
                  :disabled="isEdit"
                />
              </el-form-item>

              <el-form-item label="流程描述" prop="description">
                <el-input
                  v-model="form.description"
                  type="textarea"
                  placeholder="请输入流程描述"
                  maxlength="500"
                  show-word-limit
                  :autosize="{ minRows: 3, maxRows: 6 }"
                />
              </el-form-item>
            </el-form>
          </el-card>

          <el-card header="适用条件" class="form-card">
            <el-form :model="form" label-position="top">
              <el-form-item label="授权类型" prop="license_type">
                <el-radio-group v-model="form.license_type">
                  <el-radio value="">不限</el-radio>
                  <el-radio value="SUBSCRIPTION">订阅</el-radio>
                  <el-radio value="PERPETUAL">买断</el-radio>
                </el-radio-group>
              </el-form-item>

              <el-form-item label="适用单据" prop="business_type">
                <el-radio-group v-model="form.business_type">
                  <el-radio value="CONTRACT">合同</el-radio>
                  <el-radio value="PAYMENT">回款登记</el-radio>
                  <el-radio value="INVOICE">发票申请</el-radio>
                  <el-radio value="LICENSE">License申请</el-radio>
                </el-radio-group>
                <div class="form-item-extra">
                  <div style="color: var(--el-text-color-secondary); font-size: 12px;">
                    选择该流程适用的业务单据类型
                  </div>
                </div>
              </el-form-item>

              <el-form-item label="金额范围" prop="amount_range">
                <div class="amount-range">
                  <el-input-number
                    v-model="form.min_amount"
                    placeholder="最小金额"
                    :min="0"
                    :precision="2"
                    :controls="false"
                    style="width: 200px"
                  />
                  <span class="separator">-</span>
                  <el-input-number
                    v-model="form.max_amount"
                    placeholder="最大金额"
                    :min="0"
                    :precision="2"
                    :controls="false"
                    style="width: 200px"
                  />
                </div>
                <div class="form-item-extra">
                  <div style="color: var(--el-text-color-secondary); font-size: 12px;">
                    留空表示不限制金额
                  </div>
                </div>
              </el-form-item>

              <el-form-item v-if="isEdit" label="状态" prop="is_active">
                <el-switch
                  v-model="isActiveSwitch"
                  active-text="启用"
                  inactive-text="禁用"
                />
              </el-form-item>
            </el-form>
          </el-card>

          <el-card class="form-card">
            <template #header>
              <div class="card-header">
                <span>审批节点</span>
                <el-button type="primary" size="small" class="wolf-btn wolf-btn--primary-sm" :icon="Plus" @click="handleAddNode">
                  添加节点
                </el-button>
              </div>
            </template>

            <div v-if="form.nodes.length === 0" class="empty-nodes">
              <!-- ✅ P0: Copywriting - Invitation to act（已有按钮，保持） -->
              <el-empty description="设置审批节点，定义审批顺序">
                <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleAddNode">
                  添加第一个节点
                </el-button>
              </el-empty>
            </div>

            <div v-else class="nodes-list">
              <transition-group name="list">
                <div
                  v-for="(node, index) in form.nodes"
                  :key="index"
                  class="node-card"
                >
                  <el-card :bordered="true" shadow="never">
                    <template #header>
                      <div class="node-card-title">
                        <el-tag type="primary" size="large">
                          第 {{ node.node_order }} 步
                        </el-tag>
                        <strong>{{ node.node_name || '未命名节点' }}</strong>
                      </div>
                    </template>
                    <template #extra>
                      <div class="node-actions">
                        <el-button
                          v-if="index > 0"
                          link
                          size="small"
                          @click="handleMoveNode(index, 'up')"
                        >
                          <el-icon><ArrowUp /></el-icon>
                        </el-button>
                        <el-button
                          v-if="index < form.nodes.length - 1"
                          link
                          size="small"
                          @click="handleMoveNode(index, 'down')"
                        >
                          <el-icon><ArrowDown /></el-icon>
                        </el-button>
                        <el-popconfirm
                          title="确定要删除这个节点吗？"
                          @confirm="handleDeleteNode(index)"
                        >
                          <template #reference>
                            <el-button link type="danger" size="small">
                              <el-icon><Delete /></el-icon>
                            </el-button>
                          </template>
                        </el-popconfirm>
                      </div>
                    </template>

                    <el-form :model="node" label-position="top">
                      <el-row :gutter="16">
                        <el-col :span="12">
                          <el-form-item label="节点名称" required>
                            <el-input
                              v-model="node.node_name"
                              placeholder="如：部门经理审批"
                              maxlength="100"
                            />
                          </el-form-item>
                        </el-col>
                        <el-col :span="12">
                          <el-form-item label="节点编码" required>
                            <el-input
                              v-model="node.node_code"
                              placeholder="如：DEPT_MANAGER"
                              maxlength="50"
                            />
                          </el-form-item>
                        </el-col>
                      </el-row>

                      <el-row :gutter="16">
                        <el-col :span="12">
                          <el-form-item label="审批角色" required>
                            <el-select
                              v-model="node.approve_role"
                              placeholder="选择审批角色"
                              filterable
                              :loading="rolesLoading"
                              style="width: 100%"
                            >
                              <el-option
                                v-for="role in roles"
                                :key="role.code"
                                :value="role.code"
                                :label="role.name"
                              />
                            </el-select>
                          </el-form-item>
                        </el-col>
                        <el-col :span="12">
                          <el-form-item label="是否必须审批">
                            <el-switch
                              v-model="node.isRequired"
                              active-text="必须"
                              inactive-text="可选"
                            />
                          </el-form-item>
                        </el-col>
                      </el-row>

                      <el-form-item label="节点描述">
                        <el-input
                          v-model="node.description"
                          type="textarea"
                          placeholder="请输入节点描述"
                          maxlength="200"
                          show-word-limit
                          :autosize="{ minRows: 2, maxRows: 4 }"
                        />
                      </el-form-item>
                    </el-form>
                  </el-card>
                </div>
              </transition-group>
            </div>
          </el-card>
        </el-col>

        <el-col :span="10">
          <el-card header="流程预览" class="preview-card" v-loading="previewLoading">
            <el-steps direction="vertical" :active="form.nodes.length - 1">
              <el-step v-for="node in form.nodes" :key="node.node_order">
                <template #title>
                  <div class="preview-step-title">
                    <span>第 {{ node.node_order }} 步：{{ node.node_name }}</span>
                    <el-tag v-if="node.isRequired" type="warning" size="small">必须</el-tag>
                    <el-tag v-else type="info" size="small">可选</el-tag>
                  </div>
                </template>
                <template #description>
                  <div class="preview-step-description">
                    <p>编码：{{ node.node_code }}</p>
                    <p>角色：{{ getRoleName(node.approve_role) }}</p>
                    <p v-if="node.description">{{ node.description }}</p>
                  </div>
                </template>
              </el-step>
            </el-steps>

            <!-- ✅ P0: Copywriting - Invitation to act（改为明确的 invitation） -->
            <el-empty v-if="form.nodes.length === 0">
              <template #description>
                <div class="wolf-empty-content">
                  <span class="wolf-empty-title">设置审批节点</span>
                  <span class="wolf-empty-desc">点击添加节点，定义审批顺序和权限</span>
                </div>
              </template>
            </el-empty>
          </el-card>
        </el-col>
      </el-row>

      <!-- 表单操作 -->
      <div class="form-actions">
        <el-button @click="handleBack">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Plus,
  ArrowUp,
  ArrowDown,
  Delete
} from '@element-plus/icons-vue'
import approvalFlowApi, { type ApprovalFlow, type ApprovalFlowDetail, type ApprovalNode } from '@/api/approvalFlow'
import roleApi, { type RoleResponse } from '@/api/role'
import { usePageTitle } from '@/composables/usePageTitle'
import { useHeaderStore } from '@/stores/header'

usePageTitle()

const router = useRouter()
const route = useRoute()
const headerStore = useHeaderStore()

onMounted(() => {
  headerStore.setBack(true)
})

onUnmounted(() => {
  headerStore.clear()
})

const formRef = ref()
const submitting = ref(false)
const previewLoading = ref(false)
const roles = ref<RoleResponse[]>([])
const rolesLoading = ref(false)

const isEdit = computed(() => !!route.params.id)

const isActiveSwitch = computed({
  get: () => form.value.is_active === 1,
  set: (val) => {
    form.value.is_active = val ? 1 : 0
  }
})

interface NodeWithRequired extends ApprovalNode {
  isRequired?: boolean
}

const form = ref<ApprovalFlow & { nodes: NodeWithRequired[] }>({
  flow_name: '',
  flow_code: '',
  description: '',
  min_amount: null,
  max_amount: null,
  license_type: '',
  business_type: '' as 'CONTRACT' | 'PAYMENT' | 'INVOICE' | 'LICENSE' | '',
  is_active: 1,
  nodes: []
})

const rules = {
  flow_name: [
    { required: true, message: '请输入流程名称' }
  ],
  flow_code: [
    { required: true, message: '请输入流程编码' },
    { pattern: /^[A-Z_][A-Z0-9_]*$/, message: '流程编码只能包含大写字母、数字和下划线，且必须以字母或下划线开头' }
  ],
  business_type: [
    { required: true, message: '请选择适用单据类型', trigger: 'change' }
  ]
}

let nodeOrderCounter = 0

const fetchRoles = async () => {
  rolesLoading.value = true
  try {
    const data = await roleApi.getRoles()
    roles.value = data
  } catch (error: unknown) {
    console.error('获取角色列表失败', error)
    ElMessage.error('获取角色列表失败')
  } finally {
    rolesLoading.value = false
  }
}

const fetchFlowDetail = async () => {
  const flowId = Number(route.params.id)
  if (!flowId) return

  previewLoading.value = true
  try {
    const response = await approvalFlowApi.getApprovalFlowDetail(flowId) as unknown as ApprovalFlowDetail
    
    form.value = {
      ...response,
      min_amount: response.min_amount !== null && response.min_amount !== undefined 
        ? Number(response.min_amount) 
        : null,
      max_amount: response.max_amount !== null && response.max_amount !== undefined 
        ? Number(response.max_amount) 
        : null,
      nodes: (response.nodes || []).map((node: ApprovalNode): NodeWithRequired => ({
        ...node,
        isRequired: node.is_required === 1
      }))
    }
    
    nodeOrderCounter = Math.max(...form.value.nodes.map(n => n.node_order), 0)
  } catch (error: unknown) {
    ElMessage.error('获取流程详情失败')
    console.error('获取流程详情失败', error)
  } finally {
    previewLoading.value = false
  }
}

const handleBack = () => {
  router.push('/approval-flows')
}

const handleAddNode = () => {
  nodeOrderCounter++
  form.value.nodes.push({
    node_name: '',
    node_code: '',
    node_order: nodeOrderCounter,
    description: '',
    approve_role: '',
    is_required: 1,
    isRequired: true
  })
}

const handleDeleteNode = (index: number) => {
  form.value.nodes.splice(index, 1)
  reorderNodes()
}

const handleMoveNode = (index: number, direction: 'up' | 'down') => {
  const nodes = form.value.nodes
  const newIndex = direction === 'up' ? index - 1 : index + 1

  if (newIndex < 0 || newIndex >= nodes.length) return

  const temp = nodes[index]
  nodes[index] = nodes[newIndex]
  nodes[newIndex] = temp

  reorderNodes()
}

const reorderNodes = () => {
  form.value.nodes.forEach((node, index) => {
    node.node_order = index + 1
  })
  nodeOrderCounter = form.value.nodes.length
}

const handleSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch (error) {
    return
  }

  if (form.value.nodes.length === 0) {
    ElMessage.warning('请至少添加一个审批节点')
    return
  }

  for (const node of form.value.nodes) {
    if (!node.node_name || !node.node_code || !node.approve_role) {
      ElMessage.warning('请完整填写所有节点信息')
      return
    }
  }

  submitting.value = true
  try {
    const data = {
      ...form.value,
      nodes: form.value.nodes.map((node: NodeWithRequired) => ({
        ...node,
        is_required: node.isRequired ? 1 : 0
      }))
    }

    if (isEdit.value) {
      await approvalFlowApi.updateApprovalFlow(Number(route.params.id), data)
      ElMessage.success('更新成功')
    } else {
      await approvalFlowApi.createApprovalFlow(data)
      ElMessage.success('创建成功')
    }

    router.push('/approval-flows')
  } catch (error: unknown) {
    console.error('保存失败', error)
    ElMessage.error(error.response?.data?.detail || '保存失败')
  } finally {
    submitting.value = false
  }
}

const getRoleName = (roleCode: string) => {
  const role = roles.value.find(r => r.code === roleCode)
  return role?.name || roleCode
}

onMounted(() => {
  fetchRoles()
  if (isEdit.value) {
    fetchFlowDetail()
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.approval-flow-form-container {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.form-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: $wolf-page-padding;
}

.form-card {
  margin-bottom: $wolf-space-md;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  border: none;
}

.form-card :deep(.el-card__header) {
  padding: $wolf-card-padding;
  border-bottom: 1px solid $wolf-border-light;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.form-card :deep(.el-card__body) {
  padding: $wolf-card-padding;
}

.preview-card {
  position: sticky;
  top: $wolf-space-md;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  border: none;
}

.preview-card :deep(.el-card__header) {
  padding: $wolf-card-padding;
  border-bottom: 1px solid $wolf-border-light;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.preview-card :deep(.el-card__body) {
  padding: $wolf-card-padding;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.amount-range {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.separator {
  color: $wolf-text-tertiary;
}

.form-item-extra {
  margin-top: $wolf-space-xs;
}

.empty-nodes {
  padding: $wolf-space-lg 0;
  text-align: center;
}

.nodes-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

.node-card {
  transition: all 0.3s;
}

.node-card-title {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.node-actions {
  display: flex;
  gap: $wolf-space-xs;
}

.list-enter-active,
.list-leave-active {
  transition: all 0.3s;
}

.list-enter-from {
  opacity: 0;
  transform: translateY(-30px);
}

.list-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

.preview-step-title {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  flex-wrap: wrap;
}

.preview-step-description p {
  margin: $wolf-space-xs 0;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

// 响应式
@media (max-width: 768px) {
  .form-content {
    padding: $wolf-space-md;
  }

  .form-actions {
    flex-direction: column-reverse;

    .el-button {
      width: 100%;
    }
  }
}

// 表单操作
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
  padding: $wolf-space-md;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  margin-top: $wolf-space-md;
}
</style>
