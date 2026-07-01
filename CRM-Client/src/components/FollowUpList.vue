<template>
  <div class="follow-up-list-container">
    <div v-if="loading && followUps.length === 0" class="follow-up-skeleton">
      <el-skeleton :rows="3" animated />
    </div>

    <div v-else-if="followUps.length === 0" class="follow-up-empty">
      <el-empty description="暂无跟进记录" />
    </div>

    <div v-else class="follow-up-list">
      <div
        v-for="(followUp, index) in followUps"
        :key="followUp.id"
        class="follow-up-item"
        :class="{ 'is-last': index === followUps.length - 1 }"
      >
        <!-- 左侧垂直线 -->
        <div class="follow-up-item-tail"></div>
        <!-- 左侧圆点 -->
        <div class="follow-up-item-dot">
          <el-icon :size="12">
            <ChatDotRound />
          </el-icon>
        </div>

        <!-- 内容卡片 -->
        <div class="follow-up-item-content">
          <div class="follow-up-card">
            <!-- 时间和删除按钮 -->
            <div class="follow-up-header">
              <span class="follow-up-time">{{ formatTime(followUp.created_time) }}</span>
              <el-button
                v-if="canDelete(followUp)"
                class="delete-btn"
                type="danger"
                :icon="Delete"
                circle
                size="small"
                @click.stop="handleDelete(followUp)"
              />
            </div>

            <!-- 跟进详情 -->
            <div class="follow-up-details">
              <div class="follow-up-tags">
                <span class="meta-tag type-tag">跟进记录</span>
                <span class="meta-tag operator-tag">
                  <el-icon class="tag-icon"><User /></el-icon>
                  <span>{{ followUp.creator_info?.name || '系统' }}</span>
                </span>
                <span class="meta-tag method-tag">
                  <el-icon class="tag-icon"><Phone /></el-icon>
                  <span>{{ followUp.method }}</span>
                </span>
              </div>

              <div class="follow-up-main">
                <span class="content-value">{{ followUp.content }}</span>
              </div>

              <div v-if="followUp.next_follow_time || followUp.next_action" class="follow-up-plan">
                <div v-if="followUp.next_follow_time" class="plan-item">
                  <span class="plan-label">下次跟进</span>
                  <span class="plan-value">{{ formatDate(followUp.next_follow_time) }}</span>
                </div>
                <div v-if="followUp.next_action" class="plan-item plan-action">
                  <span class="plan-label">下一步动作</span>
                  <span class="plan-value">{{ followUp.next_action }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus'
import { Delete, User, Phone, ChatDotRound } from '@element-plus/icons-vue'

interface FollowUp {
  id: number
  lead_id?: number
  customer_id?: number | null
  original_lead_id?: number | null
  content: string
  method: string
  next_follow_time?: string | null
  next_action?: string | null
  creator_id: string
  creator_info?: { id: string; name: string; avatar_url?: string | null }
  customer_info?: { id: number; account_name: string }
  created_time: string
}

interface Props {
  followUps: FollowUp[]
  loading: boolean
  currentUserId?: string
}

type Emits = (e: 'delete', followUp: FollowUp) => void

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const canDelete = (followUp: FollowUp) => {
  const creatorIdStr = String(followUp.creator_id || '')
  const currentUserIdStr = String(props.currentUserId || '')

  return props.currentUserId && creatorIdStr === currentUserIdStr
}

const handleDelete = async (followUp: FollowUp) => {
  try {
    await ElMessageBox.confirm(
      '确定要删除这条跟进记录吗？',
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )
    emit('delete', followUp)
  } catch {
    // 用户取消删除
  }
}

const formatTime = (dateStr: string) => {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))

  if (days === 0) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } else if (days === 1) {
    return '昨天 ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } else if (days < 7) {
    return date.toLocaleDateString('zh-CN', { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  } else {
    return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  }
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}
</script>

<style scoped>
.follow-up-list-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: transparent;
}

.follow-up-skeleton {
  padding: 16px;
}

.follow-up-empty {
  padding: 40px 0;
  text-align: center;
}

.follow-up-list {
  position: relative;
  padding-left: 20px;
}

.follow-up-item {
  position: relative;
  padding-bottom: 24px;
  padding-left: 24px;
}

/* 左侧垂直线 */
.follow-up-item-tail {
  position: absolute;
  left: 0;
  top: 12px;
  height: calc(100% - 12px);
  width: 2px;
  background: #e8e8e8;
}

.follow-up-item.is-last .follow-up-item-tail {
  display: none;
}

/* 左侧圆点 */
.follow-up-item-dot {
  position: absolute;
  left: -6px;
  top: 0;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid #1890ff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #1890ff;
  z-index: 1;
}

/* 内容卡片 */
.follow-up-item-content {
  background: #fafafa;
  border-radius: 8px;
  padding: 12px;
  transition: all 0.3s;
}

.follow-up-item-content:hover {
  background: #f0f0f0;
}

.follow-up-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.follow-up-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.follow-up-time {
  font-size: 12px;
  color: #999;
}

.follow-up-details {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.follow-up-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.follow-up-main {
  flex: 1;
}

.content-value {
  color: var(--wolf-text-primary, #1D2129);
  font-size: 14px;
  line-height: 1.6;
  font-weight: 500;
}

.meta-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--wolf-radius-sm, 4px);
  font-size: 12px;
}

.type-tag {
  background: var(--wolf-primary-light, #E8F3FF);
  color: var(--wolf-primary, #165DFF);
  font-weight: 500;
}

.operator-tag {
  background: var(--wolf-bg-elevated, #FFFFFF);
  color: var(--wolf-text-secondary, #4E5969);
  border: 1px solid var(--wolf-border-default, #E5E6EB);
}

.operator-tag .tag-icon {
  color: var(--wolf-text-tertiary, #909399);
}

.method-tag {
  background: var(--wolf-bg-elevated, #FFFFFF);
  color: var(--wolf-text-secondary, #4E5969);
  border: 1px solid var(--wolf-border-default, #E5E6EB);
}

.method-tag .tag-icon {
  color: var(--wolf-primary, #165DFF);
}

.follow-up-plan {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--wolf-bg-hover, #F7F8FA);
  border-radius: var(--wolf-radius-sm, 4px);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.plan-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
}

.plan-label {
  color: var(--wolf-text-tertiary, #909399);
  min-width: 70px;
}

.plan-value {
  color: var(--wolf-text-secondary, #4E5969);
  flex: 1;
}

.plan-action .plan-value {
  color: var(--wolf-text-primary, #1D2129);
}

.tag-icon {
  font-size: 12px;
}

.delete-btn {
  width: 24px !important;
  height: 24px !important;
  padding: 0 !important;
  min-width: 24px !important;
  opacity: 0;
  transition: opacity 0.2s;
  background: transparent !important;
  border: 1px solid var(--el-color-danger) !important;
  color: var(--el-color-danger) !important;
}

.delete-btn:hover {
  background: var(--el-color-danger-light-9) !important;
}

.follow-up-card:hover .delete-btn {
  opacity: 1;
}
</style>