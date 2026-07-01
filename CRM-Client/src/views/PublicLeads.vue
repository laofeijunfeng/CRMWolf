<template>
  <div class="public-leads">
    <!-- 操作区 -->
    <div class="action-bar">
      <el-button type="primary" @click="showCreateModal">
        <el-icon><Plus /></el-icon>
        新建线索
      </el-button>
    </div>

    <!-- 表格区 -->
    <div class="table-card">
      <el-table
        :data="tableData"
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="lead_name" label="线索名称" width="150">
          <template #default="{ row }">
            <el-link type="primary" @click="handleViewDetail(row)">{{ row.lead_name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="100">
          <template #default="{ row }">
            <span class="text-secondary">{{ row.source }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="city" label="城市" width="100" />
        <el-table-column prop="contact_name" label="联系人" width="100" />
        <el-table-column prop="contact_phone" label="联系电话" width="130" />
        <el-table-column prop="company_scale" label="公司规模" width="100" />
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }">
            <span :class="['status-tag', getStatusClass(row.status)]">
              {{ getStatusText(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="created_time" label="创建时间" width="160" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="handleClaim(row.id)">领取</el-button>
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
          layout="sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </div>

    <!-- 新建线索对话框 -->
    <el-dialog
      v-model="createModalVisible"
      title="新建线索"
      width="600px"
      :close-on-click-modal="false"
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { leadApi, type Lead, type LeadCreate } from '@/api/lead'

const router = useRouter()
const loading = ref(false)
const tableData = ref<Lead[]>([])
const createModalVisible = ref(false)
const createFormRef = ref<FormInstance>()

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const createForm = reactive({
  lead_name: '',
  source: '',
  city: '',
  contact_name: '',
  contact_phone: '',
  company_scale: ''
})

const createFormRules: FormRules = {
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

const fetchPublicLeads = async () => {
  loading.value = true
  try {
    const res = await leadApi.getPublicLeads({
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize
    })
    tableData.value = res.filter((item: Lead) => item.status !== 2)
    pagination.total = tableData.value.length
  } catch (error) {
    console.error('获取公海线索列表失败', error)
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchPublicLeads()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  fetchPublicLeads()
}

const showCreateModal = () => {
  Object.assign(createForm, {
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

const handleClaim = async (id: number) => {
  try {
    await leadApi.claimLead(id)
    ElMessage.success('领取成功')
    fetchPublicLeads()
  } catch (error: unknown) {
    ElMessage.error(error.response?.data?.detail || error.message || '领取失败')
  }
}

const handleCreateModalOk = async () => {
  if (!createFormRef.value) return

  try {
    await createFormRef.value.validate()

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
    createModalVisible.value = false
    fetchPublicLeads()
  } catch (error: unknown) {
    ElMessage.error(error.response?.data?.detail || error.message || '操作失败')
  }
}

onMounted(() => {
  fetchPublicLeads()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.public-leads {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.action-bar {
  margin-bottom: $wolf-space-md;
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