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
 * - 跟进记录列表
 * - 添加跟进记录 Dialog
 * - 编辑线索 Dialog
 */
import { ref, reactive, watch } from 'vue'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, Pencil } from 'lucide-vue-next'
import LeadFormDialog from '@/components/LeadFormDialog.vue'
import LeadConvertDialog from '@/components/LeadConvertDialog.vue'
import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import {
  DateField,
  SegmentedChoiceControl,
  TextareaField,
} from '@/components/crmwolf'
import FollowUpList from '@/components/FollowUpList.vue'
import { leadApi, type LeadDetail, type LeadFollowUp, type LeadFollowUpCreate } from '@/api/lead'
import { useUserStore } from '@/stores/user'
import { formatLocalDate } from '@/utils/format'

// ==================== Props & Emits ====================
interface Props {
  leadId: string | null
  visible: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
}>()

const userStore = useUserStore()

// ==================== State ====================
const loading = ref(false)
const leadData = ref<LeadDetail | null>(null)
const followUps = ref<LeadFollowUp[]>([])

// 添加跟进弹窗
const followUpDialogOpen = ref(false)
const followUpSubmitting = ref(false)
const followUpForm = reactive({
  method: '电话',
  content: '',
  next_follow_time: '',
  next_action: ''
})
const followUpMethodOptions: { value: string; label: string }[] = [
  { value: '电话', label: '电话' },
  { value: '微信', label: '微信' },
  { value: '拜访', label: '拜访' },
  { value: '邮件', label: '邮件' },
  { value: '其他', label: '其他' }
]

// 编辑弹窗
const showEditDialog = ref(false)

// 转化为客户弹窗
const showConvertDialog = ref(false)

const handleEditSuccess = (): void => {
  // 刷新 Sheet 内部数据（遵循 UX Feedback: Submit Feedback）
  fetchLeadDetail()
  // 同时通知父组件刷新列表（保持一致性）
  emit('refresh')
}

// ==================== Methods ====================
const fetchLeadDetail = async (): Promise<void> => {
  const leadId = props.leadId
  if (leadId == null) return

  loading.value = true
  try {
    const res = await leadApi.getLeadDetail(leadId)
    leadData.value = res
    followUps.value = [...(res.follow_ups ?? [])].reverse()
  } catch (error) {
    handleApiError(error, '获取线索详情')
  } finally {
    loading.value = false
  }
}

// ==================== 操作方法 ====================
const handleConvert = (): void => {
  if (!leadData.value) return
  showConvertDialog.value = true
}

const handleConvertSuccess = (): void => {
  // 关闭 Sheet
  closeSheet()
  // 通知父组件刷新列表
  emit('refresh')
}

// ==================== 添加跟进 ====================
const showFollowUpDialog = (): void => {
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

const handleFollowUpSubmit = async (): Promise<void> => {
  const leadId = props.leadId
  const content = followUpForm.content.trim()
  if (leadId == null || content.length === 0) {
    toast.error('请输入跟进内容')
    return
  }

  followUpSubmitting.value = true
  try {
    const data: LeadFollowUpCreate = {
      content,
      method: followUpForm.method,
      next_follow_time: followUpForm.next_follow_time.length > 0 ? followUpForm.next_follow_time : null,
      next_action: followUpForm.next_action.length > 0 ? followUpForm.next_action : null
    }
    await leadApi.addFollowUp(leadId, data)
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
const handleFollowUpDelete = async (followUp: { id: number }): Promise<void> => {
  const leadId = props.leadId
  if (leadId == null) return

  try {
    await leadApi.deleteFollowUp(leadId, followUp.id)
    toast.success('跟进记录删除成功')
    await fetchLeadDetail()
  } catch (error) {
    handleApiError(error, '删除跟进')
  }
}

const closeSheet = (): void => {
  emit('update:visible', false)
}

// ==================== 格式化函数 ====================
const formatDate = (dateStr: string | undefined): string => {
  if (dateStr == null || dateStr.length === 0) return '-'
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
  return map[status] ?? '未知'
}

const getStatusClass = (status: number | undefined): string => {
  if (status === undefined) return ''
  const map: Record<number, string> = {
    0: 'status-default',
    1: 'status-warning',
    2: 'status-success',
    3: 'status-danger'
  }
  return map[status] ?? 'status-default'
}

// ==================== Watch ====================
watch(() => props.visible, (visible): void => {
  if (visible && props.leadId != null) {
    fetchLeadDetail()
  }
})
</script>

<template>
  <!-- 线索详情抽屉 -->
  <Sheet :open="visible" @update:open="$emit('update:visible', $event)">
    <DetailSheetContent>
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

            <!-- 跟进记录卡片 -->
            <Card class="follow-up-card">
              <CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
                <h3 class="text-sm font-semibold text-wolf-text-primary-v2">跟进记录</h3>
                <Button size="sm" @click="showFollowUpDialog">
                  <Plus class="w-4 h-4 mr-1" />
                  添加跟进
                </Button>
              </CardHeader>
              <CardContent class="p-0 max-h-[400px] overflow-y-auto">
                <FollowUpList
                  :follow-ups="followUps"
                  :loading="false"
                  :current-user-id="String(userStore.userInfo?.id)"
                  @delete="handleFollowUpDelete"
                />
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
    </DetailSheetContent>
  </Sheet>

  <!-- 添加跟进记录弹窗 -->
  <Dialog v-model:open="followUpDialogOpen">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>添加跟进记录</DialogTitle>
        <DialogDescription class="sr-only">记录本次跟进的详细信息</DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit.prevent="handleFollowUpSubmit">
        <div class="space-y-2">
          <p id="lead-follow-up-method-label" class="text-wolf-caption font-wolf-medium text-wolf-text-primary">
            跟进方式 <span class="text-wolf-danger" aria-hidden="true">*</span>
          </p>
          <SegmentedChoiceControl
            v-model="followUpForm.method"
            :options="followUpMethodOptions"
            labelled-by="lead-follow-up-method-label"
            id-prefix="lead-follow-up-method"
            style="--segmented-choice-columns: 5;"
          />
        </div>

        <TextareaField
          id="lead-follow-up-content"
          v-model="followUpForm.content"
          label="跟进内容"
          required
          :rows="4"
          :maxlength="500"
          placeholder="请输入跟进内容"
          control-class="resize-none"
        />

        <DateField
          id="lead-follow-up-next-time"
          :model-value="followUpForm.next_follow_time ? new Date(followUpForm.next_follow_time) : null"
          label="下次跟进时间"
          placeholder="请选择下次跟进时间"
          @update:model-value="(date: Date | null) => followUpForm.next_follow_time = date ? formatLocalDate(date) : ''"
        />

        <TextareaField
          id="lead-follow-up-next-action"
          v-model="followUpForm.next_action"
          label="下一步动作"
          :rows="3"
          :maxlength="200"
          placeholder="请输入下一步动作（可选）"
          control-class="resize-none"
        />

        <DialogFooter class="mt-6 pt-4 border-t">
          <Button variant="outline" type="button" @click="followUpDialogOpen = false">取消</Button>
          <Button type="submit" :loading="followUpSubmitting">
            提交
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>

  <!-- 编辑线索弹窗 -->
  <LeadFormDialog
    v-model:open="showEditDialog"
    mode="edit"
    :lead-id="leadId ?? undefined"
    @success="handleEditSuccess"
  />

  <!-- 转化为客户弹窗 -->
  <LeadConvertDialog
    v-model:open="showConvertDialog"
    :lead-id="leadId"
    @success="handleConvertSuccess"
  />
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
