<template>
  <div class="leads-container">
    <div class="header">
      <h1 class="title">待跟进线索</h1>
      <div class="header-actions">
        <el-select v-model="days" @change="handleDaysChange" style="width: 150px">
          <el-option :value="3" label="3天内" />
          <el-option :value="7" label="7天内" />
          <el-option :value="14" label="14天内" />
          <el-option :value="30" label="30天内" />
        </el-select>
      </div>
    </div>

    <el-card class="table-card">
      <el-empty v-if="!loading && tableData.length === 0" description="跟进线索，推动销售进展" />
      <el-table
        v-else
        :data="tableData"
        v-loading="loading"
        :border="false"
        style="width: 100%"
      >
        <el-table-column label="线索名称" width="150">
          <template #default="{ row }">
            <el-link type="primary" @click="handleViewDetail(row)">{{ row.lead_name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            <el-tag :type="getSourceType(row.source)">
              {{ row.source }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="city" label="城市" width="100" />
        <el-table-column prop="contact_name" label="联系人" width="100" />
        <el-table-column prop="contact_phone" label="联系电话" width="130" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="next_follow_time" label="下次跟进时间" width="160" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="handleAddFollowUp(row)">添加跟进</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="followUpModalVisible"
      title="添加跟进记录"
      width="600px"
    >
      <el-form :model="followUpForm" :rules="followUpFormRules" label-position="top" ref="followUpFormRef">
        <el-form-item prop="content" label="跟进内容" required>
          <el-input
            v-model="followUpForm.content"
            type="textarea"
            placeholder="请输入跟进内容"
            :maxlength="500"
            :autosize="{ minRows: 4, maxRows: 6 }"
          />
        </el-form-item>
        <el-form-item prop="method" label="跟进方式" required>
          <el-radio-group v-model="followUpForm.method">
            <el-radio value="电话">电话</el-radio>
            <el-radio value="微信">微信</el-radio>
            <el-radio value="邮件">邮件</el-radio>
            <el-radio value="拜访">拜访</el-radio>
            <el-radio value="其他">其他</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item prop="next_follow_time" label="下次跟进时间">
          <el-date-picker
            v-model="followUpForm.next_follow_time"
            placeholder="请选择下次跟进时间"
            type="datetime"
            format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="followUpModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleFollowUpModalOk">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { leadApi, type Lead, type LeadFollowUpCreate } from '@/api/lead'

const router = useRouter()
const loading = ref(false)
const tableData = ref<Lead[]>([])
const followUpModalVisible = ref(false)
const selectedLead = ref<Lead | null>(null)
const followUpFormRef = ref()
const days = ref<number>(7)

const followUpForm = reactive({
  content: '',
  method: '电话',
  next_follow_time: ''
})

const followUpFormRules = {
  content: [{ required: true, message: '请输入跟进内容' }],
  method: [{ required: true, message: '请选择跟进方式' }]
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

const getStatusType = (status: number) => {
  const typeMap: Record<number, any> = {
    0: 'primary',
    1: 'warning',
    2: 'success',
    3: 'info'
  }
  return typeMap[status] || 'info'
}

const getSourceType = (source: string) => {
  const typeMap: Record<string, any> = {
    '线上注册': 'primary',
    '市场活动': '',
    '客户推荐': 'success',
    '电话营销': 'warning',
    '网站咨询': 'info',
    '展会': 'danger',
    '其他': 'info'
  }
  return typeMap[source] || 'info'
}

const fetchFollowUpReminder = async () => {
  loading.value = true
  try {
    const res = await leadApi.getFollowUpReminder(days.value) as any
    tableData.value = res.filter((item: Lead) => item.status !== 2)
  } catch (error) {
    console.error('获取待跟进线索列表失败', error)
  } finally {
    loading.value = false
  }
}

const handleDaysChange = () => {
  fetchFollowUpReminder()
}

const handleViewDetail = (record: Lead) => {
  router.push(`/leads/${record.id}`)
}

const handleAddFollowUp = (record: Lead) => {
  selectedLead.value = record
  Object.assign(followUpForm, {
    content: '',
    method: '电话',
    next_follow_time: ''
  })
  followUpModalVisible.value = true
}

const handleFollowUpModalOk = async () => {
  if (!selectedLead.value) return
  
  try {
    await followUpFormRef.value?.validate()
  } catch {
    return
  }

  try {
    const data: LeadFollowUpCreate = {
      content: followUpForm.content,
      method: followUpForm.method,
      next_follow_time: followUpForm.next_follow_time || null,
      next_action: null
    }
    await leadApi.addFollowUp(selectedLead.value.id, data)
    ElMessage.success('添加成功')
    followUpModalVisible.value = false
    fetchFollowUpReminder()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || error.message || '添加失败')
  }
}

onMounted(() => {
  fetchFollowUpReminder()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.leads-container {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-section-gap;
}

.header-actions {
  display: flex;
  gap: $wolf-button-gap;
}

.title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
}

.table-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  box-shadow: $wolf-shadow-card;
}
</style>
