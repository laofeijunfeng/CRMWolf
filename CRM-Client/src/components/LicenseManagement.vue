<template>
  <div class="license-management">
    <!-- 部署信息区域 -->
    <el-divider content-position="left">
      <el-icon><Monitor /></el-icon> 部署信息配置
    </el-divider>
    <div class="deployment-section">
      <el-button type="primary" size="small" @click="showDeploymentDialog()">
        <el-icon><Plus /></el-icon> 新增部署信息
      </el-button>
      <el-row :gutter="16" class="deployment-grid" v-loading="loadingDeployments">
        <el-col :xs="24" :sm="12" :md="8" :lg="6" v-for="deployment in deployments" :key="deployment.id">
          <el-card shadow="hover" class="deployment-card">
            <template #header>
              <div class="card-header">
                <span class="deployment-name">{{ deployment.deployment_name }}</span>
                <el-tag v-if="deployment.is_default" type="success" size="small">默认</el-tag>
              </div>
            </template>
            <div class="card-content">
              <p class="server-address">
                <el-icon><Link /></el-icon>
                <span>{{ deployment.server_address }}</span>
              </p>
              <p class="authorized-users">
                <el-icon><User /></el-icon>
                授权人数: {{ deployment.authorized_users }}
              </p>
            </div>
            <template #footer>
              <div class="card-footer">
                <el-button size="small" text @click="showDeploymentDialog(deployment)">编辑</el-button>
                <el-button size="small" text type="danger" @click="handleDeleteDeployment(deployment.id)">删除</el-button>
                <el-button
                  v-if="!deployment.is_default"
                  size="small"
                  text
                  type="success"
                  @click="handleSetDefault(deployment.id)"
                >设为默认</el-button>
              </div>
            </template>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :md="8" :lg="6" v-if="deployments.length === 0 && !loadingDeployments">
          <el-empty description="暂无部署信息" :image-size="80" />
        </el-col>
      </el-row>
    </div>

    <!-- License 申请区域 -->
    <el-divider content-position="left" style="margin-top: 32px">
      <el-icon><Key /></el-icon> License 申请记录
    </el-divider>
    <div class="application-section">
      <el-button type="primary" size="small" @click="showApplicationDialog()">
        <el-icon><Plus /></el-icon> 申请 License
      </el-button>
      <el-table :data="applications" style="margin-top: 16px" v-loading="loadingApplications">
        <el-table-column prop="application_number" label="申请单号" width="150" />
        <el-table-column prop="license_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.license_type === 'TRIAL' ? 'warning' : 'success'" size="small">
              {{ row.license_type === 'TRIAL' ? '试用' : '正式' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="expiry_date" label="到期时间" width="120" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" show-overflow-tooltip />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="showApplicationDialog(row)" v-if="row.status === 'DRAFT'">编辑</el-button>
            <el-button size="small" text type="danger" @click="handleDeleteApplication(row.id)" v-if="row.status === 'DRAFT'">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 部署信息对话框 -->
    <DeploymentInfoDialog
      v-model:visible="deploymentDialogVisible"
      :customer-id="customerId"
      :deployment="currentDeployment"
      @success="handleDeploymentSuccess"
    />

    <!-- License 申请对话框 -->
    <LicenseApplicationDialog
      v-model:visible="applicationDialogVisible"
      :customer-id="customerId"
      :application="currentApplication"
      :deployments="deployments"
      @success="handleApplicationSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Monitor, Key, Plus, Link, User } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import deploymentApi from '@/api/deployment'
import licenseApplicationApi from '@/api/licenseApplication'
import type { DeploymentInfo } from '@/schemas/deployment'
import type { LicenseApplication } from '@/schemas/licenseApplication'
import DeploymentInfoDialog from './DeploymentInfoDialog.vue'
import LicenseApplicationDialog from './LicenseApplicationDialog.vue'

const props = defineProps<{
  customerId: number
}>()

const deployments = ref<DeploymentInfo[]>([])
const applications = ref<LicenseApplication[]>([])
const loadingDeployments = ref(false)
const loadingApplications = ref(false)

const deploymentDialogVisible = ref(false)
const applicationDialogVisible = ref(false)
const currentDeployment = ref<DeploymentInfo | undefined>()
const currentApplication = ref<LicenseApplication | undefined>()

const loadDeployments = async () => {
  loadingDeployments.value = true
  try {
    deployments.value = await deploymentApi.list(props.customerId)
  } catch (error: any) {
    ElMessage.error(error.message || '加载部署信息失败')
  } finally {
    loadingDeployments.value = false
  }
}

const loadApplications = async () => {
  loadingApplications.value = true
  try {
    applications.value = await licenseApplicationApi.list(props.customerId)
  } catch (error: any) {
    ElMessage.error(error.message || '加载 License 申请失败')
  } finally {
    loadingApplications.value = false
  }
}

const showDeploymentDialog = (deployment?: DeploymentInfo) => {
  currentDeployment.value = deployment
  deploymentDialogVisible.value = true
}

const showApplicationDialog = (application?: LicenseApplication) => {
  currentApplication.value = application
  applicationDialogVisible.value = true
}

const handleDeploymentSuccess = () => {
  deploymentDialogVisible.value = false
  currentDeployment.value = undefined
  loadDeployments()
}

const handleApplicationSuccess = () => {
  applicationDialogVisible.value = false
  currentApplication.value = undefined
  loadApplications()
}

const handleDeleteDeployment = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定删除该部署信息？', '确认', { type: 'warning' })
    await deploymentApi.deleteDeployment(id)
    ElMessage.success('删除成功')
    loadDeployments()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '删除失败')
    }
  }
}

const handleSetDefault = async (id: number) => {
  try {
    await deploymentApi.setDefault(id, props.customerId)
    ElMessage.success('设置默认成功')
    loadDeployments()
  } catch (error: any) {
    ElMessage.error(error.message || '设置默认失败')
  }
}

const handleDeleteApplication = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定删除该 License 申请？', '确认', { type: 'warning' })
    await licenseApplicationApi.deleteApplication(id)
    ElMessage.success('删除成功')
    loadApplications()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '删除失败')
    }
  }
}

const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    DRAFT: 'info',
    PENDING: 'warning',
    APPROVED: 'success',
    REJECTED: 'danger',
    ISSUED: 'success'
  }
  return types[status] || 'info'
}

const getStatusText = (status: string) => {
  const texts: Record<string, string> = {
    DRAFT: '草稿',
    PENDING: '待审批',
    APPROVED: '已批准',
    REJECTED: '已驳回',
    ISSUED: '已发放'
  }
  return texts[status] || status
}

onMounted(() => {
  loadDeployments()
  loadApplications()
})

watch(() => props.customerId, () => {
  loadDeployments()
  loadApplications()
})
</script>

<style scoped lang="scss">
.license-management {
  padding: 16px;
}

.deployment-grid {
  margin-top: 16px;
}

.deployment-card {
  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .card-content {
    p {
      margin: 8px 0;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .server-address {
      font-family: monospace;
      background: var(--el-fill-color-light);
      padding: 4px 8px;
      border-radius: 4px;
    }
  }

  .card-footer {
    display: flex;
    gap: 8px;
  }
}
</style>