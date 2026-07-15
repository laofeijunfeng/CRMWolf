<script setup lang="ts">
/**
 * LicensePanel.vue - 许可证面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 */
import { Plus, Server, FileText, ExternalLink, Calendar, Hash } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { LicenseApplicationResponse, LicenseApplicationStatus, LicenseType } from '@/api/licenseApplication'
import type { DeploymentInfoResponse } from '@/api/deployment'

// ==================== Props & Emits ====================
interface Props {
  customerId: number
  licenseApplications: LicenseApplicationResponse[]
  deployments: DeploymentInfoResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'apply': []
  'view': [applicationId: number]
}>()

// ==================== Methods ====================
const handleApply = (): void => {
  emit('apply')
}

const handleView = (applicationId: number): void => {
  emit('view', applicationId)
}

// Format date
const formatDate = (dateStr: string): string => {
  if (dateStr === null || dateStr === undefined || dateStr === '') {
    return '-'
  }
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

// Get status label and color
const getStatusInfo = (status: LicenseApplicationStatus): { label: string; color: string } => {
  const statusMap: Record<LicenseApplicationStatus, { label: string; color: string }> = {
    DRAFT: { label: '草稿', color: 'bg-slate-100 text-slate-700' },
    PENDING: { label: '待审批', color: 'bg-amber-100 text-amber-700' },
    APPROVED: { label: '已批准', color: 'bg-emerald-100 text-emerald-700' },
    REJECTED: { label: '已拒绝', color: 'bg-red-100 text-red-700' },
    ISSUED: { label: '已签发', color: 'bg-blue-100 text-blue-700' }
  }
  return statusMap[status] ?? { label: status, color: 'bg-gray-100 text-gray-700' }
}

// Get license type label and color
const getLicenseTypeInfo = (type: LicenseType | string): { label: string; color: string } => {
  const typeMap: Record<string, { label: string; color: string }> = {
    TRIAL: { label: '试用', color: 'bg-purple-100 text-purple-700' },
    OFFICIAL: { label: '正式', color: 'bg-blue-100 text-blue-700' }
  }
  return typeMap[type] ?? { label: type, color: 'bg-gray-100 text-gray-700' }
}

// Get deployment name by ID
const getDeploymentName = (deploymentId: number | null, deployments: DeploymentInfoResponse[]): string => {
  if (deploymentId === null) {
    return '未关联'
  }
  const deployment = deployments.find(d => d.id === deploymentId)
  return deployment?.deployment_name ?? '未知部署'
}
</script>

<template>
  <div class="license-panel">
    <!-- Deployments Section -->
    <ListCard
      title="部署信息"
      :items="deployments"
      empty-text="暂无部署信息"
      class="mb-4"
    >
      <template #itemMain="{ item }">
        <div class="flex items-center gap-2 mb-1">
          <span class="font-medium text-wolf-text-primary-v2">{{ item.deployment_name }}</span>
          <Badge
            v-if="item.is_default"
            variant="secondary"
            class="text-xs"
          >
            默认
          </Badge>
        </div>
        <div class="text-sm text-wolf-text-tertiary-v2 space-y-1">
          <div class="flex items-center gap-2">
            <Server class="w-3 h-3" />
            <span>{{ item.server_address }}</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-wolf-text-tertiary-v2 w-20">授权人数:</span>
            <span>{{ item.authorized_users }} 人</span>
          </div>
        </div>
      </template>
    </ListCard>

    <!-- License Applications Section -->
    <ListCard
      title="许可证申请"
      :items="licenseApplications"
      empty-text="暂无许可证申请"
    >
      <template #headerActions>
        <Button size="sm" @click="handleApply">
          <Plus class="w-4 h-4 mr-1" />
          新建申请
        </Button>
      </template>

      <template #itemMain="{ item }">
        <div class="flex items-center gap-2 mb-1">
          <Hash class="w-3 h-3 text-wolf-text-tertiary-v2" />
          <span class="text-sm text-wolf-text-tertiary-v2">{{ item.application_number }}</span>
          <Badge :class="getLicenseTypeInfo(item.license_type).color" class="text-xs">
            {{ getLicenseTypeInfo(item.license_type).label }}
          </Badge>
          <Badge :class="getStatusInfo(item.status).color" class="text-xs">
            {{ getStatusInfo(item.status).label }}
          </Badge>
        </div>

        <!-- Application Details -->
        <div class="text-sm text-wolf-text-secondary-v2 space-y-1">
          <div class="flex items-center gap-2">
            <Server class="w-3 h-3" />
            <span>部署: {{ getDeploymentName(item.deployment_info_id, deployments) }}</span>
          </div>
          <div class="flex items-center gap-2">
            <Calendar class="w-3 h-3" />
            <span>到期日期: {{ formatDate(item.expiry_date) }}</span>
          </div>
          <div v-if="item.contract_name" class="flex items-center gap-2">
            <FileText class="w-3 h-3" />
            <span>合同: {{ item.contract_name }}</span>
          </div>
        </div>

        <!-- Remark -->
        <div v-if="item.remark" class="text-xs text-wolf-text-tertiary-v2 mt-2 p-2 bg-wolf-bg-secondary-v2 rounded">
          {{ item.remark }}
        </div>
      </template>

      <template #itemActions="{ item }">
        <Button
          variant="ghost"
          size="sm"
          :aria-label="`查看申请 ${item.application_number} 详情`"
          @click.stop="handleView(item.id)"
        >
          <ExternalLink class="w-4 h-4" />
        </Button>
      </template>
    </ListCard>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.license-panel {
  display: flex;
  flex-direction: column;
}
</style>