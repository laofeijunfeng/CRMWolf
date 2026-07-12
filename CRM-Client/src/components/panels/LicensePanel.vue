<script setup lang="ts">
/**
 * LicensePanel.vue - 许可证面板组件
 *
 * 用于 CustomerDetailSheet 中的许可证申请和部署信息展示
 * 整合部署信息和申请记录
 *
 * 技术栈：shadcn-vue + variables-v2.scss
 */
import { Plus, Server, FileText, ExternalLink, Calendar, Hash } from 'lucide-vue-next'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
    <Card class="mb-4">
      <CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
        <div class="flex items-center gap-2">
          <Server class="w-4 h-4 text-wolf-text-secondary-v2" />
          <h3 class="text-sm font-semibold text-wolf-text-primary-v2">部署信息</h3>
        </div>
        <div class="text-xs text-wolf-text-tertiary-v2">
          共 {{ deployments.length }} 个部署
        </div>
      </CardHeader>
      <CardContent class="p-0">
        <!-- Empty State -->
        <div v-if="deployments.length === 0" class="p-8 text-center text-wolf-text-tertiary-v2">
          暂无部署信息
        </div>

        <!-- Deployment List -->
        <div v-else class="divide-y divide-wolf-border-light-v2">
          <div
            v-for="deployment in deployments"
            :key="deployment.id"
            class="p-4 hover:bg-wolf-bg-hover-v2 transition-colors"
          >
            <div class="flex items-start justify-between">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <span class="font-medium text-wolf-text-primary-v2">{{ deployment.deployment_name }}</span>
                  <Badge
                    v-if="deployment.is_default"
                    variant="secondary"
                    class="text-xs"
                  >
                    默认
                  </Badge>
                </div>
                <div class="text-sm text-wolf-text-tertiary-v2 space-y-1">
                  <div class="flex items-center gap-2">
                    <Server class="w-3 h-3" />
                    <span>{{ deployment.server_address }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-wolf-text-tertiary-v2 w-20">授权人数:</span>
                    <span>{{ deployment.authorized_users }} 人</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- License Applications Section -->
    <Card>
      <CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
        <div class="flex items-center gap-2">
          <FileText class="w-4 h-4 text-wolf-text-secondary-v2" />
          <h3 class="text-sm font-semibold text-wolf-text-primary-v2">许可证申请</h3>
        </div>
        <Button size="sm" @click="handleApply">
          <Plus class="w-4 h-4 mr-1" />
          新建申请
        </Button>
      </CardHeader>
      <CardContent class="p-0">
        <!-- Empty State -->
        <div v-if="licenseApplications.length === 0" class="p-8 text-center text-wolf-text-tertiary-v2">
          暂无许可证申请
        </div>

        <!-- Application List -->
        <div v-else class="divide-y divide-wolf-border-light-v2">
          <div
            v-for="application in licenseApplications"
            :key="application.id"
            class="p-4 hover:bg-wolf-bg-hover-v2 transition-colors cursor-pointer"
            @click="handleView(application.id)"
          >
            <!-- Application Header -->
            <div class="flex items-start justify-between mb-2">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <Hash class="w-3 h-3 text-wolf-text-tertiary-v2" />
                  <span class="text-sm text-wolf-text-tertiary-v2">{{ application.application_number }}</span>
                  <Badge :class="getLicenseTypeInfo(application.license_type).color" class="text-xs">
                    {{ getLicenseTypeInfo(application.license_type).label }}
                  </Badge>
                  <Badge :class="getStatusInfo(application.status).color" class="text-xs">
                    {{ getStatusInfo(application.status).label }}
                  </Badge>
                </div>
              </div>
              <Button variant="ghost" size="sm" @click.stop="handleView(application.id)">
                <ExternalLink class="w-4 h-4" />
              </Button>
            </div>

            <!-- Application Details -->
            <div class="text-sm text-wolf-text-secondary-v2 space-y-1">
              <div class="flex items-center gap-2">
                <Server class="w-3 h-3" />
                <span>部署: {{ getDeploymentName(application.deployment_info_id, deployments) }}</span>
              </div>
              <div class="flex items-center gap-2">
                <Calendar class="w-3 h-3" />
                <span>到期日期: {{ formatDate(application.expiry_date) }}</span>
              </div>
              <div v-if="application.contract_name" class="flex items-center gap-2">
                <FileText class="w-3 h-3" />
                <span>合同: {{ application.contract_name }}</span>
              </div>
            </div>

            <!-- Remark -->
            <div v-if="application.remark" class="text-xs text-wolf-text-tertiary-v2 mt-2 p-2 bg-wolf-bg-secondary-v2 rounded">
              {{ application.remark }}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.license-panel {
  display: flex;
  flex-direction: column;
}
</style>