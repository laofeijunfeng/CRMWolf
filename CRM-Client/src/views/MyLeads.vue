<template>
  <div class="my-leads">
    <!-- 筛选区 -->
    <div class="filter-card">
      <div class="filter-row">
        <el-input
          v-model="searchForm.keyword"
          placeholder="请输入线索名称、联系人或手机号"
          clearable
          class="filter-input"
        />
        <el-select v-model="searchForm.status" placeholder="全部状态" clearable class="filter-select">
          <el-option :value="0" label="新建" />
          <el-option :value="1" label="跟进中" />
          <el-option :value="3" label="无效" />
        </el-select>
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="handleReset">重置</el-button>
        <el-button type="primary" :icon="Plus" @click="showCreateModal">新建线索</el-button>
      </div>
    </div>

    <!-- 表格区 -->
    <div class="table-card">
      <el-table
        :data="tableData"
        v-loading="loading"
        :border="false"
        stripe
        style="width: 100%"
      >
        <el-table-column label="线索名称" width="150">
          <template #default="{ row }">
            <el-link type="primary" @click="handleViewDetail(row)">{{ row.lead_name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            <span class="text-secondary">{{ row.source }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="city" label="城市" width="100" />
        <el-table-column prop="contact_name" label="联系人" width="100" />
        <el-table-column prop="contact_phone" label="联系电话" width="130" />
        <el-table-column prop="company_scale" label="公司规模" width="100" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <span :class="['status-tag', getStatusClass(row.status)]">
              {{ getStatusText(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="created_time" label="创建时间" width="160" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
            <el-dropdown trigger="click" @command="(action: string) => handleAction(row, action)">
              <el-button link type="primary" size="small">
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="row.status === 1" command="return">
                    <el-icon><RefreshRight /></el-icon>
                    退回公海
                  </el-dropdown-item>
                  <el-dropdown-item v-if="row.status === 1" command="convert">
                    <el-icon><Select /></el-icon>
                    转化为客户
                  </el-dropdown-item>
                  <el-dropdown-item v-if="row.status !== 2" command="invalid">
                    <el-icon><CircleCloseFilled /></el-icon>
                    标记无效
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <span class="total-text">共 {{ pagination.total }} 条</span>
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="sizes, prev, pager, next"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </div>

    <!-- 新建/编辑对话框 -->
    <el-dialog
      v-model="createModalVisible"
      :title="createModalTitle"
      width="600px"
    >
      <el-form :model="createForm" :rules="createFormRules" label-position="top" ref="createFormRef">
        <el-form-item prop="lead_name" label="线索名称" required>
          <el-input v-model="createForm.lead_name" placeholder="请输入线索名称" />
        </el-form-item>
        <el-form-item prop="source" label="线索来源" required>
          <el-select v-model="createForm.source" placeholder="请选择线索来源" style="width: 100%">
            <el-option value="线上注册" label="线上注册" />
            <el-option value="市场活动" label="市场活动" />
            <el-option value="客户推荐" label="客户推荐" />
            <el-option value="电话营销" label="电话营销" />
            <el-option value="网站咨询" label="网站咨询" />
            <el-option value="展会" label="展会" />
            <el-option value="其他" label="其他" />
          </el-select>
        </el-form-item>
        <el-form-item prop="city" label="所在城市" required>
          <el-input v-model="createForm.city" placeholder="请输入所在城市" />
        </el-form-item>
        <el-form-item prop="contact_name" label="联系人姓名" required>
          <el-input v-model="createForm.contact_name" placeholder="请输入联系人姓名" />
        </el-form-item>
        <el-form-item prop="contact_phone" label="联系电话" required>
          <el-input v-model="createForm.contact_phone" placeholder="请输入联系电话" />
        </el-form-item>
        <el-form-item prop="company_scale" label="公司规模">
          <el-select v-model="createForm.company_scale" placeholder="请选择公司规模" clearable style="width: 100%">
            <el-option value="1-50人" label="1-50人" />
            <el-option value="51-200人" label="51-200人" />
            <el-option value="201-500人" label="201-500人" />
            <el-option value="501-1000人" label="501-1000人" />
            <el-option value="1000人以上" label="1000人以上" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateModalOk">确定</el-button>
      </template>
    </el-dialog>

    <!-- 转化对话框 -->
    <el-dialog
      v-model="convertModalVisible"
      title="转化为客户"
      width="600px"
    >
      <el-form :model="convertForm" label-position="top" ref="convertFormRef">
        <el-form-item prop="account_name" label="客户公司名称">
          <el-input v-model="convertForm.account_name" placeholder="请输入客户公司名称（可选，默认使用线索名称）" />
        </el-form-item>
        <el-form-item prop="industry" label="所属行业">
          <el-input v-model="convertForm.industry" placeholder="请输入所属行业（可选）" />
        </el-form-item>
        <el-form-item prop="address" label="公司地址">
          <el-input v-model="convertForm.address" placeholder="请输入公司地址（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="convertModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleConvertModalOk">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, MoreFilled, RefreshRight, Select, CircleCloseFilled } from '@element-plus/icons-vue'
import { leadApi, type Lead, type LeadCreate, type LeadUpdate } from '@/api/lead'
import customerApi from '@/api/customer'

const router = useRouter()
const loading = ref(false)
const tableData = ref<Lead[]>([])
const createModalVisible = ref(false)
const createModalTitle = ref('新建线索')
const convertModalVisible = ref(false)
const selectedLead = ref<Lead | null>(null)
const createFormRef = ref()
const convertFormRef = ref()

const searchForm = reactive({
  keyword: '',
  status: undefined as number | undefined
})

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const createForm = reactive({
  id: undefined as number | undefined,
  lead_name: '',
  source: '',
  city: '',
  contact_name: '',
  contact_phone: '',
  company_scale: ''
})

const convertForm = reactive({
  account_name: '',
  industry: '',
  address: ''
})

const createFormRules = {
  lead_name: [{ required: true, message: '请输入线索名称' }],
  source: [{ required: true, message: '请选择线索来源' }],
  city: [{ required: true, message: '请输入所在城市' }],
  contact_name: [{ required: true, message: '请输入联系人姓名' }],
  contact_phone: [{ required: true, message: '请输入联系电话' }]
}

const getStatusText = (status: number) => {
  const statusMap: Record<number, string> = {
    0: '新建',
    1: '跟进中',
    2: '已转化',
    3: '无效'
  }
  return statusMap[status] || '未知'
}

const getStatusClass = (status: number) => {
  const classMap: Record<number, string> = {
    0: 'status-new',
    1: 'status-following',
    2: 'status-converted',
    3: 'status-invalid'
  }
  return classMap[status] || 'status-new'
}

const fetchMyLeads = async () => {
  loading.value = true
  try {
    const res = await leadApi.getMyLeads({
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize
    }) as any
    tableData.value = res.filter((item: Lead) => item.status !== 2)
    pagination.total = tableData.value.length
  } catch (error) {
    console.error('获取我的线索列表失败', error)
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.current = 1
  fetchMyLeads()
}

const handleReset = () => {
  searchForm.keyword = ''
  searchForm.status = undefined
  handleSearch()
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchMyLeads()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  fetchMyLeads()
}

const showCreateModal = () => {
  createModalTitle.value = '新建线索'
  Object.assign(createForm, {
    id: undefined,
    lead_name: '',
    source: '',
    city: '',
    contact_name: '',
    contact_phone: '',
    company_scale: ''
  })
  createModalVisible.value = true
}

const handleViewDetail = (record: Lead) => {
  router.push(`/leads/${record.id}`)
}

const handleEdit = (record: Lead) => {
  createModalTitle.value = '编辑线索'
  Object.assign(createForm, {
    id: record.id,
    lead_name: record.lead_name,
    source: record.source,
    city: record.city,
    contact_name: record.contact_name,
    contact_phone: record.contact_phone,
    company_scale: record.company_scale || ''
  })
  createModalVisible.value = true
}

const handleAction = (record: Lead, action: string) => {
  selectedLead.value = record

  if (action === 'return') {
    handleReturn(record.id)
  } else if (action === 'convert') {
    convertForm.account_name = ''
    convertForm.industry = ''
    convertForm.address = ''
    convertModalVisible.value = true
  } else if (action === 'invalid') {
    handleMarkInvalid(record.id)
  }
}

const handleReturn = async (id: number) => {
  try {
    await leadApi.returnLead(id)
    ElMessage.success('退回成功')
    fetchMyLeads()
  } catch (error: unknown) {
    ElMessage.error(error.response?.data?.detail || error.message || '退回失败')
  }
}

const handleMarkInvalid = async (id: number) => {
  try {
    await leadApi.markInvalid(id)
    ElMessage.success('已标记为无效')
    fetchMyLeads()
  } catch (error: unknown) {
    ElMessage.error(error.response?.data?.detail || error.message || '操作失败')
  }
}

const handleConvertModalOk = async () => {
  if (!selectedLead.value) return

  try {
    await convertFormRef.value?.validate()
  } catch {
    return
  }

  try {
    const data = {
      lead_id: selectedLead.value.id,
      account_name: convertForm.account_name || undefined,
      industry: convertForm.industry || undefined,
      address: convertForm.address || undefined
    }
    const result = await customerApi.convertLeadToCustomer(data) as any
    ElMessage.success(`转化成功！客户ID：${result.customer_id}，联系人ID：${result.contact_id}`)
    convertModalVisible.value = false
    fetchMyLeads()
  } catch (error: unknown) {
    ElMessage.error(error.response?.data?.detail || error.message || '转化失败')
  }
}

const handleCreateModalOk = async () => {
  try {
    await createFormRef.value?.validate()
  } catch {
    return
  }

  try {
    if (createForm.id) {
      const updateData: LeadUpdate = {
        lead_name: createForm.lead_name,
        source: createForm.source,
        city: createForm.city,
        contact_name: createForm.contact_name,
        contact_phone: createForm.contact_phone,
        company_scale: createForm.company_scale || undefined
      }
      await leadApi.updateLead(createForm.id, updateData)
      ElMessage.success('更新成功')
    } else {
      const createData: LeadCreate = {
        lead_name: createForm.lead_name,
        source: createForm.source,
        city: createForm.city,
        contact_name: createForm.contact_name,
        contact_phone: createForm.contact_phone,
        company_scale: createForm.company_scale || undefined
      }
      await leadApi.createLead(createData)
      ElMessage.success('创建成功')
    }
    createModalVisible.value = false
    fetchMyLeads()
  } catch (error: unknown) {
    ElMessage.error(error.response?.data?.detail || error.message || '操作失败')
  }
}

onMounted(() => {
  fetchMyLeads()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.my-leads {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.filter-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.filter-row {
  display: flex;
  gap: $wolf-space-sm;
  align-items: center;
}

.filter-input {
  width: 240px;
}

.filter-select {
  width: 120px;
}

.table-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
}

.pagination-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: $wolf-space-md;
}

.total-text {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
}

.text-secondary {
  color: $wolf-text-secondary;
}

// 状态标签
.status-tag {
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  border-radius: $wolf-radius-sm;
  display: inline-block;
}

.status-new {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-following {
  background: $wolf-warning-bg;
  color: $wolf-warning-text;
}

.status-converted {
  background: $wolf-success-bg;
  color: $wolf-success-text;
}

.status-invalid {
  background: $wolf-danger-bg;
  color: $wolf-danger-text;
}
</style>