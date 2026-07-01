<template>
  <div class="roles-container">
    <!-- P1: Typography - 页面标题（IBM Plex Sans） -->
    <h1 class="wolf-page-title">角色管理</h1>

    <!-- 搜索/操作区 -->
    <div class="wolf-card search-card">
      <el-form :inline="true">
        <el-form-item>
          <el-button type="primary" @click="showCreateModal">
            <el-icon><Plus /></el-icon>
            新建角色
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="wolf-card table-card">
      <div class="wolf-table-wrapper">
        <el-table
          :data="tableData"
          v-loading="loading"
          class="wolf-table"
          :pagination="paginationProps"
          @page-change="handlePageChange"
          style="width: 100%"
        >
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="code" label="角色代码" min-width="150">
            <template #default="{ row }">
              <span class="wolf-link">{{ row.code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="角色名称" min-width="150" />
          <el-table-column prop="description" label="描述" min-width="250" />
          <el-table-column prop="created_at" label="创建时间" min-width="160">
            <template #default="{ row }">
              {{ formatDate(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" fixed="right" width="260">
            <template #default="{ row }">
              <div class="wolf-table-actions">
                <el-button type="primary" size="small" class="wolf-btn wolf-btn--primary-sm" @click="handleEdit(row)">
                  编辑
                </el-button>
                <el-button type="default" size="small" class="wolf-btn wolf-btn--default-sm" @click="handleConfigPermissions(row)">
                  配置权限
                </el-button>
                <el-button type="text" size="small" class="wolf-btn wolf-btn--text-danger" @click="handleDelete(row)">
                  删除
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
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

    <el-dialog
      v-model="createModalVisible"
      :title="isEditMode ? '编辑角色' : '新建角色'"
      width="600px"
      @close="createModalVisible = false"
    >
      <el-form :model="createForm" :rules="createFormRules" label-position="top" ref="createFormRef">
        <el-form-item prop="code" label="角色代码" required>
          <el-input v-model="createForm.code" placeholder="请输入角色代码（如：SALES_DIRECTOR）" :disabled="isEditMode" />
        </el-form-item>
        <el-form-item prop="name" label="角色名称" required>
          <el-input v-model="createForm.name" placeholder="请输入角色名称（如：销售总监）" />
        </el-form-item>
        <el-form-item prop="description" label="描述">
          <el-input v-model="createForm.description" type="textarea" placeholder="请输入角色描述" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button class="wolf-btn wolf-btn--default" @click="createModalVisible = false">取消</el-button>
        <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleCreateModalOk">确定</el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="permissionsModalVisible"
      title="配置角色权限"
      direction="rtl"
      size="700px"
    >
      <div v-if="currentRole" class="permissions-drawer">
        <div class="role-info-section">
          <div class="role-info-card">
            <div class="role-avatar">{{ currentRole.name?.charAt(0) || '角' }}</div>
            <div class="role-info">
              <div class="role-name">{{ currentRole.name }}</div>
              <div class="role-meta">
                <span class="role-code">{{ currentRole.code }}</span>
                <span v-if="currentRole.description" class="role-desc">{{ currentRole.description }}</span>
              </div>
              <div class="role-count">已选择 {{ selectedPermissionIds.length }} 项权限</div>
            </div>
          </div>
        </div>

        <div class="permissions-section">
          <div v-if="allPermissions.length > 0" class="permissions-config">
            <div v-for="group in permissionGroups" :key="group.resource" class="permission-group">
              <div class="group-header">
                <span class="group-title">{{ getResourceName(group.resource) }}</span>
                <el-checkbox
                  :model-value="isGroupAllSelected(group.resource)"
                  :indeterminate="isGroupIndeterminate(group.resource)"
                  @change="handleGroupSelect(group.resource, $event)"
                >
                  全选
                </el-checkbox>
              </div>
              <div class="group-permissions">
                <el-checkbox
                  v-for="permission in group.permissions"
                  :key="permission.id"
                  :model-value="selectedPermissionIds.includes(permission.id)"
                  :label="permission.id"
                  @change="handlePermissionSelect(permission.id, $event)"
                >
                  <span class="permission-label">
                    <span class="permission-action-tag">{{ permission.action }}</span>
                    <span class="permission-name-text">{{ permission.name }}</span>
                  </span>
                </el-checkbox>
              </div>
            </div>
          </div>
          <el-empty v-else description="添加权限，配置角色权限范围" />
        </div>

        <div class="drawer-footer">
          <el-button class="wolf-btn wolf-btn--default" @click="permissionsModalVisible = false">取消</el-button>
          <el-button type="primary" class="wolf-btn wolf-btn--primary" :loading="savingPermissions" @click="handleSavePermissions">
            保存
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, ArrowLeft } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import roleApi, { type RoleResponse, type RoleCreate, type RoleUpdate, type RoleWithPermissions, type PermissionResponse } from '@/api/role'
import permissionApi from '@/api/permissions'

const router = useRouter()
const loading = ref(false)
const tableData = ref<RoleResponse[]>([])
const selectedRole = ref<RoleResponse | null>(null)
const isEditMode = ref(false)
const currentRole = ref<RoleWithPermissions | null>(null)
const permissionsModalVisible = ref(false)
const allPermissions = ref<PermissionResponse[]>([])
const selectedPermissionIds = ref<number[]>([])
const savingPermissions = ref(false)

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showTotal: true
})

const paginationProps = computed(() => ({
  pageSize: pagination.pageSize,
  total: pagination.total
}))

const handleBack = () => {
  router.push('/settings')
}

const createModalVisible = ref(false)
const createFormRef = ref()
const createForm = reactive<RoleCreate & { description?: string }>({
  code: '',
  name: '',
  description: ''
})

const createFormRules = {
  code: [{ required: true, message: '请输入角色代码' }],
  name: [{ required: true, message: '请输入角色名称' }]
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

const fetchRoles = async () => {
  loading.value = true
  try {
    const params = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize
    }

    const data = await roleApi.getRoles(params)
    tableData.value = data
    pagination.total = data.length
  } catch (error: unknown) {
    console.error('获取角色列表失败', error)
    showError(error, '获取角色列表')
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchRoles()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchRoles()
}

const showCreateModal = () => {
  isEditMode.value = false
  Object.assign(createForm, {
    code: '',
    name: '',
    description: ''
  })
  createModalVisible.value = true
}

const handleEdit = (record: RoleResponse) => {
  selectedRole.value = record
  isEditMode.value = true
  Object.assign(createForm, {
    code: record.code,
    name: record.name,
    description: record.description
  })
  createModalVisible.value = true
}

const handleConfigPermissions = async (record: RoleResponse) => {
  try {
    // 获取角色详情（包含当前权限）
    const roleData = await roleApi.getRole(record.id)
    currentRole.value = roleData

    // 获取所有权限列表
    const permsData = await permissionApi.getAllPermissions()
    allPermissions.value = permsData

    // 设置当前已选权限
    selectedPermissionIds.value = roleData.permissions?.map((p: PermissionResponse) => p.id) || []

    permissionsModalVisible.value = true
  } catch (error: unknown) {
    console.error('获取角色权限失败', error)
    showError(error, '获取角色权限')
  }
}

// 权限分组（按资源分组）
const permissionGroups = computed(() => {
  const groups: Record<string, PermissionResponse[]> = {}
  allPermissions.value.forEach(permission => {
    const resource = permission.resource
    if (!groups[resource]) {
      groups[resource] = []
    }
    groups[resource]!.push(permission)
  })
  return Object.entries(groups).map(([resource, permissions]) => ({
    resource,
    permissions
  }))
})

// 资源名称映射
const resourceNames: Record<string, string> = {
  lead: '线索',
  customer: '客户',
  opportunity: '商机',
  contract: '合同',
  invoice: '发票',
  product: '产品',
  user: '用户',
  role: '角色',
  permission: '权限',
  system: '系统'
}

const getResourceName = (resource: string) => {
  return resourceNames[resource] || resource
}

// 检查分组是否全选
const isGroupAllSelected = (resource: string) => {
  const group = permissionGroups.value.find(g => g.resource === resource)
  if (!group) return false
  return group.permissions.every(p => selectedPermissionIds.value.includes(p.id))
}

// 检查分组是否部分选中
const isGroupIndeterminate = (resource: string) => {
  const group = permissionGroups.value.find(g => g.resource === resource)
  if (!group) return false
  const selectedCount = group.permissions.filter(p => selectedPermissionIds.value.includes(p.id)).length
  return selectedCount > 0 && selectedCount < group.permissions.length
}

// 处理分组全选
const handleGroupSelect = (resource: string, checked: boolean) => {
  const group = permissionGroups.value.find(g => g.resource === resource)
  if (!group) return

  if (checked) {
    // 添加该分组所有权限
    const newIds = group.permissions.map(p => p.id)
    selectedPermissionIds.value = [...new Set([...selectedPermissionIds.value, ...newIds])]
  } else {
    // 移除该分组所有权限
    const groupIds = group.permissions.map(p => p.id)
    selectedPermissionIds.value = selectedPermissionIds.value.filter(id => !groupIds.includes(id))
  }
}

// 处理单个权限选择
const handlePermissionSelect = (permissionId: number, checked: boolean) => {
  if (checked) {
    selectedPermissionIds.value = [...selectedPermissionIds.value, permissionId]
  } else {
    selectedPermissionIds.value = selectedPermissionIds.value.filter(id => id !== permissionId)
  }
}

// 保存权限配置
const handleSavePermissions = async () => {
  if (!currentRole.value) return

  savingPermissions.value = true
  try {
    await roleApi.updateRolePermissions(currentRole.value.id, selectedPermissionIds.value)
    showSuccess('保存', '权限配置')
    permissionsModalVisible.value = false
  } catch (error: unknown) {
    console.error('保存权限失败', error)
    showError(error, '保存权限配置')
  } finally {
    savingPermissions.value = false
  }
}

const handleCreateModalOk = async () => {
  try {
    await createFormRef.value?.validate()
    
    if (isEditMode.value && selectedRole.value) {
      const updateData: RoleUpdate = {
        role_name: createForm.name,
        description: createForm.description || null
      }
      await roleApi.updateRole(selectedRole.value.id, updateData)
      showSuccess('更新', '角色')
    } else {
      await roleApi.createRole(createForm)
      showSuccess('创建', '角色')
    }

    createModalVisible.value = false
    fetchRoles()
  } catch (error: unknown) {
    console.error('操作失败', error)
    showError(error, isEditMode.value ? '更新角色' : '创建角色')
  }
}

const handleDelete = (record: RoleResponse) => {
  ElMessageBox.confirm(
    `确定要删除角色"${record.name}"吗？删除后不可恢复。`,
    '确认删除',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await roleApi.deleteRole(record.id)
      showSuccess('删除', '角色')
      fetchRoles()
    } catch (error: unknown) {
      console.error('删除失败', error)
      showError(error, '删除角色')
    }
  })
}

onMounted(() => {
  fetchRoles()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.roles-container {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.search-card {
  padding: $wolf-space-md;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  margin-bottom: $wolf-space-md;
}

.wolf-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  padding: 0;
  margin-bottom: $wolf-space-md;
}

.table-card {
  padding: $wolf-space-md;
  overflow: hidden;
}

.wolf-table-wrapper {
  border-radius: $wolf-radius-md;
  overflow-x: auto;
}

.wolf-table :deep(.el-table__header th) {
  background-color: $wolf-bg-hover !important;
  color: $wolf-text-secondary;
  font-weight: $wolf-font-weight-medium;
  font-size: $wolf-font-size-auxiliary;
  padding: 12px $wolf-space-md;
  border-bottom: 1px solid $wolf-border-light;
}

.wolf-table :deep(.el-table__row td) {
  padding: 12px $wolf-space-md;
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  border-bottom: 1px solid $wolf-border-light;
}

.wolf-table :deep(.el-table__row:hover td) {
  background-color: $wolf-bg-hover !important;
}

.wolf-link {
  color: $wolf-text-link;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium;
}

.wolf-link:hover {
  text-decoration: underline;
}

.wolf-table-actions {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
}

.wolf-btn--text-danger {
  color: $wolf-danger-text !important;
  border: 1px solid $wolf-danger-border !important;
  background-color: $wolf-bg-card !important;
  padding: 8px 12px !important;
}

.wolf-btn--text-danger:hover {
  background-color: $wolf-danger-bg !important;
}

.permissions-list {
  max-height: 300px;
  overflow-y: auto;
}

.pagination-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: $wolf-space-md;
  border-top: 1px solid $wolf-border-light;
}

.total-text {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.permissions-drawer {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: $wolf-page-padding;
}

.role-info-section {
  margin-bottom: $wolf-space-md;
}

.role-info-card {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-card-padding;
  background: $wolf-bg-page;
  border-radius: $wolf-radius-md;
  border: 1px solid $wolf-border-default;
}

.role-avatar {
  width: 48px;
  height: 48px;
  border-radius: $wolf-radius-md;
  background: $wolf-primary;
  color: $wolf-text-inverse;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold;
  flex-shrink: 0;
}

.role-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
}

.role-name {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.role-meta {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  flex-wrap: wrap;
}

.role-code {
  padding: 2px 8px;
  background: $wolf-primary-light;
  color: $wolf-primary;
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-medium;
}

.role-desc {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.role-count {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  font-weight: $wolf-font-weight-medium;
}

.permissions-section {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.permissions-config {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm;
}

.permission-group {
  margin-bottom: $wolf-space-md;
  padding: $wolf-space-md;
  background: $wolf-bg-card;
  border: 1px solid $wolf-border-default;
  border-radius: $wolf-radius-md;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;
  margin-bottom: $wolf-space-sm;
}

.group-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.group-permissions {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-sm;
}

.permission-label {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.permission-action-tag {
  display: inline-block;
  padding: 2px 8px;
  background: $wolf-primary-light;
  color: $wolf-primary;
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-medium;
}

.permission-name-text {
  color: $wolf-text-primary;
  font-size: $wolf-font-size-body;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
  padding: $wolf-space-md 0;
  border-top: 1px solid $wolf-border-default;
  margin-top: $wolf-space-md;
}

.wolf-btn--primary-sm {
  background: $wolf-primary !important;
  border-color: $wolf-primary !important;
  color: $wolf-text-inverse !important;
  font-weight: $wolf-font-weight-medium !important;
}

.wolf-btn--default-sm {
  background: $wolf-bg-card !important;
  border: 1px solid $wolf-border-default !important;
  color: $wolf-text-secondary !important;
}

.wolf-btn--default {
  background: $wolf-bg-card !important;
  border: 1px solid $wolf-border-default !important;
  color: $wolf-text-secondary !important;
}

.wolf-btn--primary {
  background: $wolf-primary !important;
  border-color: $wolf-primary !important;
  color: $wolf-text-inverse !important;
  font-weight: $wolf-font-weight-medium !important;
}
</style>
