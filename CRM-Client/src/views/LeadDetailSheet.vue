<script setup lang="ts">
/**
 * LeadDetailSheet.vue - 线索详情抽屉组件
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - 使用 shadcn-vue Sheet 组件
 * - 宽度：右侧 2/3（66.67%）
 * - V2 Design Tokens
 *
 * 包含：
 * - 基本信息卡片
 * - 热力值卡片（线性进度条）
 * - 跟进记录列表
 * - 添加跟进记录 Dialog
 * - 编辑线索 Dialog
 * - 热力值明细 Dialog
 */
import { ref, reactive, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, Pencil, TrendingUp, Clock, CheckCircle } from 'lucide-vue-next'
import LeadFormDialog from '@/components/LeadFormDialog.vue'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter
} from '@/components/ui/sheet'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Progress } from '@/components/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Table, TableHeader, TableRow, TableCell } from '@/components/ui/table'
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import FollowUpList from '@/components/FollowUpList.vue'
import { leadApi, type LeadDetail, type LeadFollowUp, type LeadFollowUpCreate } from '@/api/lead'
import { getLeadScore, getScoreLevel, type ScoreDetail } from '@/api/score'
import { useUserStore } from '@/stores/user'

// ==================== Props & Emits ====================
interface Props {
  leadId: number | null
  visible: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
}>()

const router = useRouter()
const userStore = useUserStore()

// ==================== State ====================
const loading = ref(false)
const leadData = ref<LeadDetail | null>(null)
const followUps = ref<LeadFollowUp[]>([])
const scoreDetails = ref<ScoreDetail[]>([])

// 添加跟进弹窗
const followUpDialogOpen = ref(false)
const followUpSubmitting = ref(false)
const followUpForm = reactive({
  method: '电话',
  content: '',
  next_follow_time: '',
  next_action: ''
})

// 编辑弹窗
const showEditDialog = ref(false)

const handleEditSuccess = (): void => {
  // 刷新 Sheet 内部数据（遵循 UX Feedback: Submit Feedback）
  fetchLeadDetail()
  // 同时通知父组件刷新列表（保持一致性）
  emit('refresh')
}

// 热力值明细弹窗
const scoreDetailsDialogOpen = ref(false)

// ==================== Methods ====================
const fetchLeadDetail = async () => {
  if (!props.leadId) return

  loading.value = true
  try {
    const res = await leadApi.getLeadDetail(props.leadId)
    leadData.value = res
    followUps.value = res.follow_ups?.reverse() || []

    // 获取热力值明细（使用 score 参数或默认值）
    try {
      const scoreRes = await getLeadScore(props.leadId)
      scoreDetails.value = scoreRes.details || []
    } catch {
      scoreDetails.value = []
    }
  } catch (error) {
    handleApiError(error, '获取线索详情')
  } finally {
    loading.value = false
  }
}

// ==================== 操作方法 ====================
const handleConvert = () => {
  if (!leadData.value) return
  closeSheet()
  router.push(`/leads/${leadData.value.id}/convert`)
}

// ==================== 添加跟进 ====================
const showFollowUpDialog = () => {
  // 设置默认下次跟进时间（3天后）
  const threeDaysLater = new Date()
  threeDaysLater.setDate(threeDaysLater.getDate() + 3)

  Object.assign(followUpForm, {
    method: '电话',
    content: '',
    next_follow_time: formatDateForInput(threeDaysLater),
    next_action: ''
  })
  followUpDialogOpen.value = true
}

const handleFollowUpSubmit = async () => {
  if (!props.leadId || !followUpForm.content.trim()) {
    toast.error('请输入跟进内容')
    return
  }

  followUpSubmitting.value = true
  try {
    const data: LeadFollowUpCreate = {
      content: followUpForm.content,
      method: followUpForm.method,
      next_follow_time: followUpForm.next_follow_time || null,
      next_action: followUpForm.next_action || null
    }
    await leadApi.addFollowUp(props.leadId, data)
    toast.success('跟进记录添加成功')
    followUpDialogOpen.value = false
    await fetchLeadDetail()
  } catch (error) {
    handleApiError(error, '添加跟进')
  } finally {
    followUpSubmitting.value = false
  }
}

// ==================== 删除跟进 ====================
const handleFollowUpDelete = async (followUp: { id: number }) => {
  if (!props.leadId) return

  try {
    await leadApi.deleteFollowUp(props.leadId, followUp.id)
    toast.success('跟进记录删除成功')
    await fetchLeadDetail()
  } catch (error) {
    handleApiError(error, '删除跟进')
  }
}

const closeSheet = () => {
  emit('update:visible', false)
}

// ==================== 辅助属性 ====================
// score 属性（LeadDetail 类型已包含 score 字段）
const leadScore = computed(() => leadData.value?.score ?? null)

// ==================== 格式化函数 ====================
const formatDate = (dateStr: string | undefined): string => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

const formatDateForInput = (date: Date): string => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const getStatusText = (status: number | undefined): string => {
  if (status === undefined) return '-'
  const map: Record<number, string> = { 0: '新建', 1: '跟进中', 2: '已转化', 3: '无效' }
  return map[status] || '未知'
}

const getStatusClass = (status: number | undefined): string => {
  if (status === undefined) return ''
  const map: Record<number, string> = {
    0: 'status-default',
    1: 'status-warning',
    2: 'status-success',
    3: 'status-danger'
  }
  return map[status] || 'status-default'
}

const getScoreColorValue = (score: number | undefined): string => {
  if (score === undefined || score === null) return '#94A3B8'
  if (score >= 80) return '#10B981'
  if (score >= 60) return '#F59E0B'
  if (score >= 40) return '#3B82F6'
  return '#64748B'
}

const getScoreIconEmoji = (score: number | undefined): string => {
  if (score === undefined || score === null) return '📋'
  if (score >= 80) return '🔥'
  if (score >= 60) return '⭐'
  if (score >= 40) return '📈'
  return '📋'
}

// ==================== Watch ====================
watch(() => props.visible, (visible) => {
  if (visible && props.leadId) {
    fetchLeadDetail()
  }
})
</script>

<template>
  <!-- 线索详情抽屉 -->
  <Sheet :open="visible" @update:open="$emit('update:visible', $event)">
    <SheetContent
      side="right"
      class="w-2/3 max-w-[880px] sm:max-w-[880px] p-0 flex flex-col bg-white dark:bg-slate-900"
    >
      <!-- Header -->
      <SheetHeader class="p-6 pb-4 border-b border-wolf-border-default-v2">
        <div class="flex items-center gap-4">
          <div v-if="leadData" class="title-avatar">
            {{ leadData.lead_name?.charAt(0) || '线' }}
          </div>
          <div class="flex-1 min-w-0">
            <SheetTitle class="text-lg font-semibold truncate">
              {{ leadData?.lead_name || '线索详情' }}
            </SheetTitle>
            <SheetDescription class="flex items-center gap-2 mt-1">
              <Badge v-if="leadData" :class="['status-badge', getStatusClass(leadData.status)]">
                {{ getStatusText(leadData.status) }}
              </Badge>
            </SheetDescription>
          </div>
          <div v-if="leadData" class="text-right">
            <div class="text-xs text-wolf-text-tertiary-v2">跟进次数</div>
            <div class="text-lg font-semibold text-wolf-text-primary-v2">
              {{ followUps.length }}
            </div>
          </div>
        </div>
      </SheetHeader>

      <!-- Content -->
      <ScrollArea class="flex-1">
        <div class="p-6 space-y-6 min-h-[600px] transition-opacity duration-200">
          <!-- 加载骨架屏（保持与实际内容相近的高度，避免加载时抖动）-->
          <template v-if="loading">
            <div class="space-y-4">
              <Skeleton class="h-32 w-full" />
              <Skeleton class="h-24 w-full" />
              <Skeleton class="h-48 w-full" />
            </div>
          </template>

          <template v-else-if="leadData">
            <!-- 基本信息卡片 -->
            <Card class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">基本信息</h3>
                </div>
                <div class="p-4">
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
              </CardContent>
            </Card>

            <!-- 热力值卡片 -->
            <Card class="score-card">
              <CardContent class="p-4">
                <div class="flex items-center gap-4">
                  <div class="flex-shrink-0 text-2xl">
                    {{ getScoreIconEmoji(leadScore) }}
                  </div>
                  <div class="flex-1">
                    <div class="flex items-center gap-2 mb-2">
                      <span class="text-2xl font-bold text-wolf-text-primary-v2">
                        {{ leadScore ?? '--' }}
                      </span>
                      <span class="text-sm text-wolf-text-tertiary-v2 bg-wolf-bg-muted-v2 px-2 py-0.5 rounded">
                        {{ getScoreLevel(leadScore) }}
                      </span>
                    </div>
                    <Progress
                      :model-value="leadScore || 0"
                      class="h-2"
                      :style="{ '--progress-background': getScoreColorValue(leadScore) }"
                    />
                    <div class="flex items-center gap-2 mt-2 text-xs text-wolf-text-tertiary-v2">
                      <template v-for="(detail, idx) in scoreDetails.slice(0, 2)" :key="detail.id">
                        <span>
                          {{ detail.factor_name }}:
                          <span :class="detail.score_change >= 0 ? 'text-wolf-success-text-v2' : 'text-wolf-danger-text-v2'">
                            {{ detail.score_change >= 0 ? '+' : '' }}{{ detail.score_change }}
                          </span>
                        </span>
                        <span v-if="idx < 1 && scoreDetails.length > 1">·</span>
                      </template>
                      <Button
                        v-if="scoreDetails.length > 0"
                        variant="link"
                        size="sm"
                        class="h-auto p-0 text-xs"
                        @click="scoreDetailsDialogOpen = true"
                      >
                        详情
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <!-- 跟进记录卡片 -->
            <Separator />
            <Card class="follow-up-card">
              <CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
                <h3 class="text-sm font-semibold text-wolf-text-primary-v2">跟进记录</h3>
                <Button size="sm" @click="showFollowUpDialog">
                  <Plus class="w-4 h-4 mr-1" />
                  添加跟进
                </Button>
              </CardHeader>
              <CardContent class="p-0">
                <FollowUpList
                  :follow-ups="followUps"
                  :loading="false"
                  :current-user-id="String(userStore.userInfo?.id)"
                  @delete="handleFollowUpDelete"
                />
                <Empty v-if="followUps.length === 0" class="py-8">
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <Clock class="w-10 h-10" />
                    </EmptyMedia>
                  </EmptyHeader>
                  <EmptyTitle>暂无跟进记录</EmptyTitle>
                  <EmptyDescription>点击上方按钮添加跟进记录</EmptyDescription>
                </Empty>
              </CardContent>
            </Card>
          </template>

          <!-- 空状态 -->
          <Empty v-else>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <TrendingUp class="w-10 h-10" />
              </EmptyMedia>
            </EmptyHeader>
            <EmptyTitle>线索信息加载失败</EmptyTitle>
            <EmptyDescription>请稍后重试</EmptyDescription>
          </Empty>
        </div>
      </ScrollArea>

      <!-- Footer -->
      <SheetFooter class="p-4 border-t border-wolf-border-default-v2 flex flex-row gap-2">
        <Button
          v-if="leadData?.status === 0 || leadData?.status === 1"
          variant="default"
          @click="handleConvert"
        >
          <CheckCircle class="w-4 h-4 mr-2" />
          转化为客户
        </Button>
        <Button variant="outline" @click="showEditDialog = true">
          <Pencil class="w-4 h-4 mr-2" />
          编辑
        </Button>
      </SheetFooter>
    </SheetContent>
  </Sheet>

  <!-- 添加跟进记录弹窗 -->
  <Dialog v-model:open="followUpDialogOpen">
    <DialogContent class="sm:max-w-[500px]">
      <DialogHeader>
        <DialogTitle>添加跟进记录</DialogTitle>
        <DialogDescription>记录本次跟进的详细信息</DialogDescription>
      </DialogHeader>

      <div class="grid gap-4 py-4">
        <div class="grid gap-2">
          <Label>跟进方式</Label>
          <RadioGroup v-model="followUpForm.method" class="flex flex-wrap gap-4">
            <div class="flex items-center space-x-2">
              <RadioGroupItem id="phone" value="电话" />
              <Label for="phone" class="font-normal">电话</Label>
            </div>
            <div class="flex items-center space-x-2">
              <RadioGroupItem id="wechat" value="微信" />
              <Label for="wechat" class="font-normal">微信</Label>
            </div>
            <div class="flex items-center space-x-2">
              <RadioGroupItem id="visit" value="拜访" />
              <Label for="visit" class="font-normal">拜访</Label>
            </div>
            <div class="flex items-center space-x-2">
              <RadioGroupItem id="email" value="邮件" />
              <Label for="email" class="font-normal">邮件</Label>
            </div>
            <div class="flex items-center space-x-2">
              <RadioGroupItem id="other" value="其他" />
              <Label for="other" class="font-normal">其他</Label>
            </div>
          </RadioGroup>
        </div>

        <div class="grid gap-2">
          <Label for="content">跟进内容</Label>
          <Textarea
            id="content"
            v-model="followUpForm.content"
            placeholder="请输入跟进内容"
            :rows="4"
            :maxlength="500"
          />
        </div>

        <div class="grid gap-2">
          <Label for="next_follow_time">下次跟进时间</Label>
          <Input
            id="next_follow_time"
            type="date"
            v-model="followUpForm.next_follow_time"
          />
        </div>

        <div class="grid gap-2">
          <Label for="next_action">下一步动作</Label>
          <Textarea
            id="next_action"
            v-model="followUpForm.next_action"
            placeholder="请输入下一步动作计划"
            :rows="2"
            :maxlength="200"
          />
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="followUpDialogOpen = false">取消</Button>
        <Button :disabled="followUpSubmitting" @click="handleFollowUpSubmit">
          {{ followUpSubmitting ? '提交中...' : '确定' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 编辑线索弹窗 -->
  <LeadFormDialog
    v-model:open="showEditDialog"
    mode="edit"
    :lead-id="leadId"
    @success="handleEditSuccess"
  />

  <!-- 热力值明细弹窗 -->
  <Dialog v-model:open="scoreDetailsDialogOpen">
    <DialogContent class="sm:max-w-[600px]">
      <DialogHeader>
        <DialogTitle>热力值计算明细</DialogTitle>
        <DialogDescription>了解热力值的计算依据</DialogDescription>
      </DialogHeader>

      <Table v-if="scoreDetails.length > 0">
        <TableRow>
          <TableHeader>因子</TableHeader>
          <TableHeader>实际值</TableHeader>
          <TableHeader>权重</TableHeader>
          <TableHeader>分数变化</TableHeader>
          <TableHeader>原因说明</TableHeader>
        </TableRow>
        <TableRow v-for="detail in scoreDetails" :key="detail.id">
          <TableCell>{{ detail.factor_name }}</TableCell>
          <TableCell>{{ detail.actual_value || '-' }}</TableCell>
          <TableCell>{{ detail.weight_value }}</TableCell>
          <TableCell>
            <span :class="detail.score_change >= 0 ? 'text-wolf-success-text-v2' : 'text-wolf-danger-text-v2'">
              {{ detail.score_change >= 0 ? '+' : '' }}{{ detail.score_change }}
            </span>
          </TableCell>
          <TableCell>{{ detail.reason || '-' }}</TableCell>
        </TableRow>
      </Table>

      <Empty v-else class="py-8">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <TrendingUp class="w-10 h-10" />
          </EmptyMedia>
        </EmptyHeader>
        <EmptyTitle>暂无明细数据</EmptyTitle>
        <EmptyDescription>查看计算明细，了解评分依据</EmptyDescription>
      </Empty>

      <DialogFooter>
        <Button @click="scoreDetailsDialogOpen = false">关闭</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.title-avatar {
  width: 48px;
  height: 48px;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold-v2;
  flex-shrink: 0;
}

.attributes-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $wolf-space-md-v2 $wolf-space-lg-v2;

  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.attribute-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.attribute-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  font-weight: $wolf-font-weight-medium-v2;
  word-break: break-all;
}

// 状态 Badge
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-full-v2;
  white-space: nowrap;
}

.status-default {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.status-warning {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-success {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.status-danger {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

// 跟进记录卡片
.follow-up-card {
  :deep(.follow-up-list-container) {
    padding: 0;
    background: transparent;
  }
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>