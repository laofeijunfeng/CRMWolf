<template>
  <div class="approval-flows-container">
    <!-- 搜索/操作区 -->
    <div class="wolf-card search-card">
      <el-form :inline="true">
        <el-form-item>
          <el-input
            v-model="searchText"
            placeholder="搜索流程名称、编码"
            clearable
            style="width: 200px"
            @change="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-select
            v-model="filterStatus"
            placeholder="筛选状态"
            clearable
            style="width: 120px"
            @change="handleSearch"
          >
            <el-option :value="true" label="启用" />
            <el-option :value="false" label="禁用" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-select
            v-model="filterLicenseType"
            placeholder="授权类型"
            clearable
            style="width: 120px"
            @change="handleSearch"
          >
            <el-option value="SUBSCRIPTION" label="订阅" />
            <el-option value="PERPETUAL" label="买断" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="handleCreate">
            <el-icon><Plus /></el-icon>
            新建流程
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="wolf-card table-card">
      <div class="wolf-table-wrapper">
        <el-table
          :data="approvalFlows"
          v-loading="loading"
          class="wolf-table"
          :border="false"
          row-key="id"
          style="width: 100%"
        >
          <el-table-column prop="flow_name" label="流程名称" min-width="150">
            <template #default="{ row }">
              <span class="wolf-link">{{ row.flow_name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="flow_code" label="流程编码" min-width="120" />
          <el-table-column label="金额范围" min-width="150">
            <template #default="{ row }">
              <span v-if="row.min_amount || row.max_amount">
                ¥{{ formatAmount(row.min_amount) }} - ¥{{ formatAmount(row.max_amount) }}
              </span>
              <span v-else class="text-gray">不限</span>
            </template>
          </el-table-column>
          <el-table-column label="授权类型" width="120">
            <template #default="{ row }">
              <el-tag v-if="row.license_type === 'SUBSCRIPTION'" class="wolf-tag wolf-tag--info" size="small">订阅</el-tag>
              <el-tag v-else-if="row.license_type === 'PERPETUAL'" class="wolf-tag wolf-tag--success" size="small">买断</el-tag>
              <span v-else class="text-gray">不限</span>
            </template>
          </el-table-column>
          <el-table-column label="节点数" width="100">
            <template #default="{ row }">
              <el-badge :value="row.nodes?.length || 0" type="primary" />
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag v-if="row.is_active" class="wolf-tag wolf-tag--success" size="small">启用</el-tag>
              <el-tag v-else class="wolf-tag wolf-tag--gray" size="small">禁用</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" min-width="160">
            <template #default="{ row }">
              {{ formatDate(row.created_time) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <div class="wolf-table-actions">
                <el-button type="primary" size="small" class="wolf-btn wolf-btn--primary-sm" @click="handleView(row)">
                  查看
                </el-button>
                <el-button type="default" size="small" class="wolf-btn wolf-btn--default-sm" @click="handleEdit(row)">
                  编辑
                </el-button>
                <el-button
                  text
                  size="small"
                  class="wolf-btn"
                  :class="row.is_active ? 'wolf-btn--text-warning' : 'wolf-btn--text-success'"
                  @click="handleToggleStatus(row)"
                >
                  {{ row.is_active ? '禁用' : '启用' }}
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="pagination-bar">
        <span class="total-text">共 {{ pagination.total }} 条</span>
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </div>

    <el-dialog
      v-model="detailVisible"
      :title="`流程详情 - ${currentFlow?.flow_name}`"
      width="800px"
      :close-on-click-modal="false"
    >
      <el-descriptions v-if="currentFlow" :column="2" border>
        <el-descriptions-item label="流程名称">
          {{ currentFlow.flow_name }}
        </el-descriptions-item>
        <el-descriptions-item label="流程编码">
          {{ currentFlow.flow_code }}
        </el-descriptions-item>
        <el-descriptions-item label="金额范围">
          <span v-if="currentFlow.min_amount || currentFlow.max_amount">
            ¥{{ formatAmount(currentFlow.min_amount) }} - ¥{{ formatAmount(currentFlow.max_amount) }}
          </span>
          <span v-else>不限</span>
        </el-descriptions-item>
        <el-descriptions-item label="授权类型">
          <el-tag v-if="currentFlow.license_type === 'SUBSCRIPTION'">订阅</el-tag>
          <el-tag v-else-if="currentFlow.license_type === 'PERPETUAL'">买断</el-tag>
          <span v-else>不限</span>
        </el-descriptions-item>
        <el-descriptions-item label="状态" :span="2">
          <el-tag v-if="currentFlow.is_active" type="success">启用</el-tag>
          <el-tag v-else type="info">禁用</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="描述" :span="2" v-if="currentFlow.description">
          {{ currentFlow.description }}
        </el-descriptions-item>
        <el-descriptions-item label="审批节点" :span="2">
          <el-timeline v-if="currentFlow.nodes && currentFlow.nodes.length > 0">
            <el-timeline-item
              v-for="node in currentFlow.nodes.sort((a, b) => a.node_order - b.node_order)"
              :key="node.id"
            >
              <div class="node-item">
                <div class="node-header">
                  <el-tag class="wolf-tag wolf-tag--info" size="small">{{ node.node_order }}</el-tag>
                  <strong>{{ node.node_name }}</strong>
                  <el-tag v-if="node.is_required" class="wolf-tag wolf-tag--warning" size="small">必须</el-tag>
                  <el-tag v-else class="wolf-tag wolf-tag--gray" size="small">可选</el-tag>
                </div>
                <div class="node-body">
                  <p>编码：{{ node.node_code }}</p>
                  <p>审批角色：{{ node.approve_role }}</p>
                  <p v-if="node.description">描述：{{ node.description }}</p>
                </div>
              </div>
            </el-timeline-item>
          </el-timeline>
          <!-- ✅ P0: Copywriting - Invitation to act（不是 mood） -->
          <WolfEmpty
            v-else
            title="设置审批流程"
            description="点击上方按钮添加审批节点"
          />
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { showError, showSuccess, getEmptyStateMessage } from '@/utils/errorMessages'
import WolfEmpty from '@/components/WolfEmpty.vue'
import { Plus, Search, ArrowLeft } from '@element-plus/icons-vue'
import approvalFlowApi, { type ApprovalFlow, type ApprovalFlowDetail } from '@/api/approvalFlow'

const router = useRouter()

const handleBack = () => {
  router.push('/settings')
}

const loading = ref(false)
const approvalFlows = ref<ApprovalFlowDetail[]>([])
const searchText = ref('')
const filterStatus = ref<boolean | null>(null)
const filterLicenseType = ref<string | null>(null)
const detailVisible = ref(false)
const currentFlow = ref<ApprovalFlowDetail | null>(null)

const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0
})

const fetchApprovalFlows = async () => {
  loading.value = true
  try {
    const params: any = {
      skip: (pagination.value.current - 1) * pagination.value.pageSize,
      limit: pagination.value.pageSize
    }

    if (filterStatus.value !== null) {
      params.is_active = filterStatus.value
    }

    const data = await approvalFlowApi.getApprovalFlows(params) as any

    let flows = Array.isArray(data) ? data : []

    if (searchText.value) {
      const keyword = searchText.value.toLowerCase()
      flows = flows.filter((flow: any) =>
        flow.flow_name.toLowerCase().includes(keyword) ||
        flow.flow_code.toLowerCase().includes(keyword)
      )
    }

    if (filterLicenseType.value) {
      flows = flows.filter((flow: any) => flow.license_type === filterLicenseType.value)
    }

    approvalFlows.value = flows
    pagination.value.total = flows.length
  } catch (error: unknown) {
    const err = error as Error
    console.error('获取审批流程失败', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '获取审批流程')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.value.current = 1
  fetchApprovalFlows()
}

const handlePageChange = (page: number) => {
  pagination.value.current = page
  fetchApprovalFlows()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.value.pageSize = pageSize
  pagination.value.current = 1
  fetchApprovalFlows()
}

const handleCreate = () => {
  router.push('/approval-flows/create')
}

const handleView = async (flow: ApprovalFlowDetail) => {
  try {
    const data = await approvalFlowApi.getApprovalFlowDetail(flow.id!) as any
    currentFlow.value = data
    detailVisible.value = true
  } catch (error: unknown) {
    const err = error as Error
    console.error('[ApprovalFlows] handleView error:', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '获取流程详情')
  }
}

const handleEdit = (flow: ApprovalFlowDetail) => {
  router.push(`/approval-flows/${flow.id}/edit`)
}

const handleToggleStatus = (flow: ApprovalFlowDetail) => {
  const action = flow.is_active ? '禁用' : '启用'
  ElMessageBox.confirm(
    `确定要${action}流程"${flow.flow_name}"吗？`,
    `确认${action}`,
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await approvalFlowApi.updateApprovalFlow(flow.id!, { is_active: flow.is_active ? 0 : 1 })
      // ✅ P0: Copywriting - 具体化的成功提示
      showSuccess(action, '审批流程')
      fetchApprovalFlows()
    } catch (error: unknown) {
      const err = error as Error
      console.error('[ApprovalFlows] handleToggleStatus error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, `${action}审批流程`)
    }
  }).catch(() => {
    // 用户取消操作
  })
}

const formatAmount = (amount: number | null | undefined) => {
  if (amount === null || amount === undefined) return '0'
  return amount.toLocaleString()
}

const formatDate = (dateStr: string | undefined) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  fetchApprovalFlows()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.approval-flows-container {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.wolf-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  padding: 0;
  margin-bottom: $wolf-space-md;
}

.search-card {
  padding: $wolf-space-md;
}

.table-card {
  padding: $wolf-space-md;
  overflow: hidden;
}

.wolf-table-wrapper {
  border-radius: $wolf-radius-md;
  overflow-x: auto;
}

.wolf-table :deep(.el-table__header th) {
  background-color: $wolf-bg-hover !important;
  color: $wolf-text-secondary;
  font-weight: $wolf-font-weight-medium;
  font-size: $wolf-font-size-auxiliary;
  padding: 12px $wolf-space-md;
  border-bottom: 1px solid $wolf-border-light;
}

.wolf-table :deep(.el-table__row td) {
  padding: 12px $wolf-space-md;
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  border-bottom: 1px solid $wolf-border-light;
}

.wolf-table :deep(.el-table__row:hover td) {
  background-color: $wolf-bg-hover !important;
}

.wolf-link {
  color: $wolf-text-link;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium;
}

.wolf-link:hover {
  text-decoration: underline;
}

.wolf-table-actions {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
}

.wolf-btn--text-warning {
  color: $wolf-warning-text !important;
  border: 1px solid $wolf-warning-border !important;
  background-color: $wolf-bg-card !important;
  padding: 8px 12px !important;
  border-radius: $wolf-radius-sm !important;
}

.wolf-btn--text-warning:hover {
  background-color: $wolf-warning-bg !important;
}

.wolf-btn--text-success {
  color: $wolf-success-text !important;
  border: 1px solid $wolf-success-border !important;
  background-color: $wolf-bg-card !important;
  padding: 8px 12px !important;
  border-radius: $wolf-radius-sm !important;
}

.wolf-btn--text-success:hover {
  background-color: $wolf-success-bg !important;
}

.text-gray {
  color: $wolf-text-tertiary;
}

.pagination-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: $wolf-space-md;
  border-top: 1px solid $wolf-border-light;
}

.total-text {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.node-item {
  padding: $wolf-space-sm 0;
}

.node-header {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  margin-bottom: $wolf-space-sm;
}

.node-body p {
  margin: $wolf-space-xs 0;
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-body;
}

.wolf-tag {
  border-radius: $wolf-radius-sm !important;
  padding: 2px 8px !important;
  font-size: $wolf-font-size-caption !important;
  font-weight: $wolf-font-weight-medium !important;
  height: auto !important;
  line-height: 1.5 !important;
  border-width: 1px !important;
}

.wolf-tag--success {
  background-color: $wolf-success-bg !important;
  border-color: $wolf-success-border !important;
  color: $wolf-success-text !important;
}

.wolf-tag--gray {
  background-color: $wolf-purple-bg !important;
  border-color: $wolf-purple-border !important;
  color: $wolf-purple !important;
}

.wolf-tag--info {
  background-color: $wolf-info-bg !important;
  border-color: $wolf-info-border !important;
  color: $wolf-info !important;
}

.wolf-tag--warning {
  background-color: $wolf-warning-bg !important;
  border-color: $wolf-warning-border !important;
  color: $wolf-warning-text !important;
}

.wolf-btn--primary-sm {
  background: $wolf-primary !important;
  border-color: $wolf-primary !important;
  color: $wolf-text-inverse !important;
  font-weight: $wolf-font-weight-medium !important;
}

.wolf-btn--default-sm {
  background: $wolf-bg-card !important;
  border: 1px solid $wolf-border-default !important;
  color: $wolf-text-secondary !important;
}
</style>
