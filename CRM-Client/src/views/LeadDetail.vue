<template>
  <div class="lead-detail">
    <!-- 页面标题栏 -->
    <div class="page-header">
      <div class="page-header-left">
        <el-button class="back-btn" @click="router.back()">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="wolf-page-title">{{ leadData?.lead_name || '线索详情' }}</h1>
      </div>
      <div class="page-header-right">
        <el-button type="primary" @click="handleEdit">编辑</el-button>
      </div>
    </div>

    <!-- 内容区 -->
    <div v-loading="loading" class="detail-content">
      <div v-if="!leadData" class="empty-state">
        <el-empty description="线索信息加载失败" />
      </div>

      <template v-else>
        <!-- 基本信息卡片 -->
        <div class="info-card">
          <!-- 标题区 -->
          <div class="info-header">
            <div class="info-left">
              <div class="avatar">{{ leadData?.lead_name?.charAt(0) || '线' }}</div>
              <div class="title-section">
                <h2 class="entity-name">{{ leadData?.lead_name }}</h2>
                <span :class="['status-tag', getStatusClass(leadData.status)]">
                  {{ getStatusText(leadData.status) }}
                </span>
              </div>
            </div>
            <div class="info-right">
              <div class="stat-item">
                <div class="stat-label">跟进次数</div>
                <div class="stat-value">{{ followUps.length }} 次</div>
              </div>
            </div>
          </div>

          <!-- 分隔线 -->
          <div class="info-divider"></div>

          <!-- 属性网格 -->
          <div class="attributes-grid">
            <div class="attribute-item">
              <div class="attribute-label">线索来源</div>
              <div class="attribute-value">{{ leadData.source || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">所在城市</div>
              <div class="attribute-value">{{ leadData.city || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">联系人</div>
              <div class="attribute-value">{{ leadData.contact_name || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">联系电话</div>
              <div class="attribute-value">{{ leadData.contact_phone || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">公司规模</div>
              <div class="attribute-value">{{ leadData.company_scale || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">负责人</div>
              <div class="attribute-value">{{ leadData.owner_info?.name || '-' }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">创建时间</div>
              <div class="attribute-value">{{ formatDate(leadData.created_time) }}</div>
            </div>

            <div class="attribute-item">
              <div class="attribute-label">创建人</div>
              <div class="attribute-value">{{ leadData.creator_info?.name || '-' }}</div>
            </div>
          </div>
        </div>

        <!-- 热力值卡片（紧凑布局） -->
        <div class="score-card-compact">
          <div class="score-mini-circle">
            <el-progress
              type="circle"
              :percentage="leadData.score || 0"
              :color="getScoreColor(leadData.score)"
              :width="60"
              :stroke-width="4"
            />
          </div>
          <div class="score-mini-info">
            <div class="score-mini-header">
              <span class="score-mini-icon">{{ getScoreIcon(leadData.score) }}</span>
              <span class="score-mini-value">{{ leadData.score ?? '--' }}</span>
              <span class="score-mini-level">{{ getScoreLevel(leadData.score) }}</span>
            </div>
            <div class="score-mini-details">
              <span v-for="(detail, idx) in scoreDetails.slice(0, 2)" :key="detail.id" class="detail-mini-item">
                {{ detail.factor_name }}: <span :class="detail.score_change >= 0 ? 'pos' : 'neg'">{{ detail.score_change >= 0 ? '+' : '' }}{{ detail.score_change }}</span>
                <span v-if="idx < 1 && scoreDetails.length > 1"> · </span>
              </span>
              <el-button link size="small" @click="showScoreDetails = true" v-if="scoreDetails.length > 0">详情</el-button>
            </div>
          </div>
        </div>

        <!-- 跟进记录卡片 -->
        <div class="follow-up-card">
          <div class="card-header">
            <span class="card-title">跟进记录</span>
            <el-button type="primary" @click="showFollowUpModal">
              <el-icon><Plus /></el-icon>
              添加跟进
            </el-button>
          </div>

          <FollowUpList
            :follow-ups="followUps"
            :loading="loading"
            :current-user-id="String(userStore.userInfo?.id)"
            @delete="handleFollowUpDelete"
          />
        </div>
      </template>
    </div>

    <!-- 添加跟进记录对话框 -->
    <el-dialog
      v-model="followUpModalVisible"
      title="添加跟进记录"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="followUpForm" :rules="followUpFormRules" label-position="top" ref="followUpFormRef">
        <el-form-item label="跟进方式" prop="method" required>
          <el-radio-group v-model="followUpForm.method">
            <el-radio value="电话">电话</el-radio>
            <el-radio value="微信">微信</el-radio>
            <el-radio value="拜访">拜访</el-radio>
            <el-radio value="邮件">邮件</el-radio>
            <el-radio value="其他">其他</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="跟进内容" prop="content" required>
          <el-input
            v-model="followUpForm.content"
            type="textarea"
            placeholder="请输入跟进内容"
            :maxlength="500"
            :rows="4"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="下次跟进时间" prop="next_follow_time">
          <el-date-picker
            v-model="followUpForm.next_follow_time"
            type="datetime"
            placeholder="请选择下次跟进时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="下一步动作" prop="next_action">
          <el-input
            v-model="followUpForm.next_action"
            type="textarea"
            placeholder="请输入下一步动作计划"
            :maxlength="200"
            :rows="2"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="followUpModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleFollowUpModalOk">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑线索对话框 -->
    <el-dialog
      v-model="editModalVisible"
      title="编辑线索"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="editForm" :rules="editFormRules" label-position="top" ref="editFormRef">
        <el-form-item label="线索名称" prop="lead_name" required>
          <el-input v-model="editForm.lead_name" placeholder="请输入线索名称" />
        </el-form-item>
        <el-form-item label="线索来源" prop="source" required>
          <el-select v-model="editForm.source" placeholder="请选择线索来源" style="width: 100%">
            <el-option value="线上注册" label="线上注册" />
            <el-option value="市场活动" label="市场活动" />
            <el-option value="客户推荐" label="客户推荐" />
            <el-option value="电话营销" label="电话营销" />
            <el-option value="网站咨询" label="网站咨询" />
            <el-option value="展会" label="展会" />
            <el-option value="其他" label="其他" />
          </el-select>
        </el-form-item>
        <el-form-item label="所在城市" prop="city" required>
          <el-input v-model="editForm.city" placeholder="请输入所在城市" />
        </el-form-item>
        <el-form-item label="联系人姓名" prop="contact_name" required>
          <el-input v-model="editForm.contact_name" placeholder="请输入联系人姓名" />
        </el-form-item>
        <el-form-item label="联系电话" prop="contact_phone" required>
          <el-input v-model="editForm.contact_phone" placeholder="请输入联系电话" />
        </el-form-item>
        <el-form-item label="公司规模" prop="company_scale">
          <el-select v-model="editForm.company_scale" placeholder="请选择公司规模" clearable style="width: 100%">
            <el-option value="1-50人" label="1-50人" />
            <el-option value="51-200人" label="51-200人" />
            <el-option value="201-500人" label="201-500人" />
            <el-option value="501-1000人" label="501-1000人" />
            <el-option value="1000人以上" label="1000人以上" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleEditModalOk">确定</el-button>
      </template>
    </el-dialog>

    <!-- 热力值明细弹窗 -->
    <el-dialog v-model="showScoreDetails" title="热力值计算明细" width="600px">
      <el-table :data="scoreDetails" stripe>
        <el-table-column prop="factor_name" label="因子" width="150" />
        <el-table-column prop="actual_value" label="实际值" width="120">
          <template #default="{ row }">
            {{ row.actual_value || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="weight_value" label="权重" width="80" />
        <el-table-column label="分数变化" width="100">
          <template #default="{ row }">
            <span :class="row.score_change >= 0 ? 'positive' : 'negative'">
              {{ row.score_change >= 0 ? '+' : '' }}{{ row.score_change }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="原因说明">
          <template #default="{ row }">
            {{ row.reason || '-' }}
          </template>
        </el-table-column>
      </el-table>
      <div v-if="scoreDetails.length === 0" class="score-details-empty">
        <el-empty description="查看计算明细，了解评分依据" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { showError, showSuccess } from '@/utils/errorMessages'
import {
  ArrowLeft,
  Plus
} from '@element-plus/icons-vue'
import { leadApi, type LeadDetail, type LeadUpdate, type LeadFollowUpCreate } from '@/api/lead'
import { getLeadScore, getScoreIcon, getScoreColor, getScoreLevel, type ScoreDetail } from '@/api/score'
import FollowUpList from '@/components/FollowUpList.vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const leadId = Number(route.params['id'])
const userStore = useUserStore()

const loading = ref(false)
const leadData = ref<LeadDetail | null>(null)
const followUps = ref<any[]>([])

// 热力值相关
const showScoreDetails = ref(false)
const scoreDetails = ref<ScoreDetail[]>([])

const followUpModalVisible = ref(false)
const editModalVisible = ref(false)
const followUpFormRef = ref()
const editFormRef = ref()

const followUpForm = reactive({
  method: '电话',
  content: '',
  next_follow_time: '',
  next_action: ''
})

const editForm = reactive({
  lead_name: '',
  source: '',
  city: '',
  contact_name: '',
  contact_phone: '',
  company_scale: ''
})

const followUpFormRules = {
  content: [{ required: true, message: '请输入跟进内容', trigger: 'blur' }],
  method: [{ required: true, message: '请选择跟进方式', trigger: 'change' }]
}

const editFormRules = {
  lead_name: [{ required: true, message: '请输入线索名称', trigger: 'blur' }],
  source: [{ required: true, message: '请选择线索来源', trigger: 'change' }],
  city: [{ required: true, message: '请输入所在城市', trigger: 'blur' }],
  contact_name: [{ required: true, message: '请输入联系人姓名', trigger: 'blur' }],
  contact_phone: [{ required: true, message: '请输入联系电话', trigger: 'blur' }]
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

const formatDate = (dateStr: string) => {
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

const fetchLeadDetail = async () => {
  loading.value = true
  try {
    const res = await leadApi.getLeadDetail(leadId) as any
    leadData.value = res
    followUps.value = res.follow_ups?.reverse() || []

    // 获取热力值明细
    if (res.score !== null) {
      try {
        const scoreRes = await getLeadScore(leadId)
        scoreDetails.value = scoreRes.details || []
      } catch {
        // 热力值明细获取失败不影响主流程
        scoreDetails.value = []
      }
    }
  } catch (error: any) {
    showError(error, '获取线索详情')
  } finally {
    loading.value = false
  }
}

const handleEdit = () => {
  router.push(`/leads/${leadId}/edit`)
}

const handleEditModalOk = async () => {
  try {
    await editFormRef.value?.validate()
  } catch {
    return
  }

  try {
    const updateData: LeadUpdate = {
      lead_name: editForm.lead_name,
      source: editForm.source,
      city: editForm.city,
      contact_name: editForm.contact_name,
      contact_phone: editForm.contact_phone,
      company_scale: editForm.company_scale || undefined
    }
    await leadApi.updateLead(leadId, updateData)
    showSuccess('更新', '线索')
    editModalVisible.value = false
    await fetchLeadDetail()
  } catch (error: any) {
    showError(error, '更新线索')
  }
}

const showFollowUpModal = () => {
  let nextFollowTime = ''
  if (followUps.value.length > 0 && followUps.value[0]?.next_follow_time) {
    const lastNextTime = new Date(followUps.value[0].next_follow_time)
    const today = new Date()
    if (lastNextTime > today) {
      nextFollowTime = lastNextTime.toISOString().split('T')[0]
    }
  }

  if (!nextFollowTime) {
    const threeDaysLater = new Date()
    threeDaysLater.setDate(threeDaysLater.getDate() + 3)
    nextFollowTime = threeDaysLater.toISOString().split('T')[0]
  }

  Object.assign(followUpForm, {
    method: '电话',
    content: '',
    next_follow_time: nextFollowTime,
    next_action: ''
  })
  followUpModalVisible.value = true
}

const handleFollowUpModalOk = async () => {
  try {
    await followUpFormRef.value?.validate()
  } catch {
    return
  }

  try {
    const data: LeadFollowUpCreate = {
      content: followUpForm.content,
      method: followUpForm.method,
      next_follow_time: followUpForm.next_follow_time ? new Date(followUpForm.next_follow_time).toISOString() : null,
      next_action: followUpForm.next_action || null
    }
    await leadApi.addFollowUp(leadId, data)
    showSuccess('添加', '跟进记录')
    followUpModalVisible.value = false
    // 刷新跟进记录
    await fetchLeadDetail()
  } catch (error: any) {
    showError(error, '添加跟进')
  }
}

const handleFollowUpDelete = async (followUp: any) => {
  try {
    await leadApi.deleteFollowUp(leadId, followUp['id'])
    showSuccess('删除', '跟进记录')
    // 刷新跟进记录
    await fetchLeadDetail()
  } catch (error: any) {
    showError(error, '删除跟进')
  }
}

onMounted(() => {
  fetchLeadDetail()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.lead-detail {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.page-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: $wolf-bg-card;
  border-bottom: 1px solid $wolf-border-default;
  height: $wolf-header-height;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 $wolf-page-padding;
}

.page-header-left,
.page-header-right {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.page-header-left {
  flex: 1;
  min-width: 0;
}

.page-header-right {
  flex-shrink: 0;
}


.back-btn {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: $wolf-radius-md !important;
  background: transparent !important;
  border: none !important;

  &:hover {
    background: $wolf-bg-hover !important;
  }
}

.page-title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.detail-content {
  padding: $wolf-page-padding;
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
}

// 信息卡片
.info-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.info-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: $wolf-space-md;
}

.info-left {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.avatar {
  width: 48px;
  height: 48px;
  border-radius: $wolf-radius-full;
  background: $wolf-primary-light;
  color: $wolf-primary;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold;
  flex-shrink: 0;
}

.title-section {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
}

.entity-name {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
}

.info-right {
  flex-shrink: 0;
}

.stat-item {
  text-align: right;
}

.stat-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-bottom: $wolf-space-xs;
}

.stat-value {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.info-divider {
  height: 1px;
  background: $wolf-border-light;
  margin: $wolf-space-md 0;
}

// 属性网格
.attributes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: $wolf-space-md;
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
}

.attribute-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.attribute-value {
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
}

// 跟进记录卡片
.follow-up-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.follow-up-card :deep(.follow-up-list-container) {
  padding: 0;
  background: transparent;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-md;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
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

// 响应式
@media (max-width: 768px) {
  .detail-content {
    padding: $wolf-space-md;
  }

  .info-card,
  .follow-up-card,
  .score-card {
    padding: $wolf-space-md;
  }

  .info-header {
    flex-direction: column;
    gap: $wolf-space-md;
  }

  .info-right {
    align-self: flex-start;
  }

  .attributes-grid {
    grid-template-columns: 1fr;
  }
}

// 热力值卡片样式（紧凑布局）
.score-card-compact {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.score-mini-circle {
  flex-shrink: 0;
}

.score-mini-info {
  flex: 1;
  min-width: 0;
}

.score-mini-header {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  margin-bottom: $wolf-space-xs;
}

.score-mini-icon {
  font-size: 18px;
}

.score-mini-value {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.score-mini-level {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
  background: $wolf-bg-page;
  padding: 2px $wolf-space-xs;
  border-radius: $wolf-radius-sm;
}

.score-mini-details {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
}

.detail-mini-item {
  white-space: nowrap;
}

.pos {
  color: $wolf-success-text;
  font-weight: $wolf-font-weight-medium;
}

.neg {
  color: $wolf-danger-text;
  font-weight: $wolf-font-weight-medium;
}

.score-details-empty {
  padding: $wolf-space-lg;
}
</style>