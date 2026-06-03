<template>
  <div class="users-container">
    <div class="wolf-card search-card">
      <el-form :model="searchForm" :inline="true">
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部" style="width: 120px" clearable>
            <el-option value="active" label="活跃" />
            <el-option value="inactive" label="停用" />
          </el-select>
        </el-form-item>
        <el-form-item label="地区">
          <el-input
            v-model="searchForm.region"
            placeholder="所在地区"
            clearable
            style="width: 150px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="handleSearch">
            <el-icon><Search /></el-icon>
            搜索
          </el-button>
          <el-button class="wolf-btn wolf-btn--default" @click="handleReset">
            <el-icon><Refresh /></el-icon>
            重置
          </el-button>
          <el-button v-if="canManageUser" type="primary" class="wolf-btn wolf-btn--primary-sm" @click="showCreateModal">
            <el-icon><Plus /></el-icon>
            新建用户
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
          style="width: 100%"
        >
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="name" label="姓名" min-width="120">
            <template #default="{ row }">
              <span class="wolf-link">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="email" label="邮箱" min-width="180" />
          <el-table-column prop="mobile" label="手机" min-width="120" />
          <el-table-column prop="region" label="地区" min-width="100" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag v-if="row.status === 'active'" class="wolf-tag wolf-tag--success" size="small">活跃</el-tag>
              <el-tag v-else class="wolf-tag wolf-tag--gray" size="small">停用</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="roles" label="角色" min-width="180">
            <template #default="{ row }">
              <template v-if="row.roles && row.roles.length > 0">
                <el-tag v-for="role in row.roles" :key="role.code" class="wolf-tag wolf-tag--info" size="small" style="margin: 2px">
                  {{ role.name }}
                </el-tag>
              </template>
              <span v-else class="text-gray">未分配</span>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" min-width="160">
            <template #default="{ row }">
              {{ formatDate(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" fixed="right" width="200">
            <template #default="{ row }">
              <div class="wolf-table-actions">
                <el-button v-if="canManageUser" type="primary" size="small" class="wolf-btn wolf-btn--primary-sm" @click="handleEdit(row)">
                  编辑
                </el-button>
                <el-button v-if="canAssignRoles" type="default" size="small" class="wolf-btn wolf-btn--default-sm" @click="handleAssignRoles(row)">
                  分配角色
                </el-button>
                <el-button v-if="canManageUser" type="text" size="small" class="wolf-btn wolf-btn--text-danger" @click="handleDelete(row)">
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
      :title="isEditMode ? '编辑用户' : '新建用户'"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="createForm" :rules="createFormRules" label-width="140px" ref="createFormRef">
        <el-form-item prop="name" label="姓名" required>
          <el-input v-model="createForm.name" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item prop="email" label="邮箱" required>
          <el-input v-model="createForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item prop="mobile" label="手机">
          <el-input v-model="createForm.mobile" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item prop="region" label="地区">
          <el-input v-model="createForm.region" placeholder="请输入所在地区" />
        </el-form-item>
        <el-form-item prop="status" label="状态">
          <el-select v-model="createForm.status" placeholder="请选择状态" style="width: 100%">
            <el-option value="active" label="活跃" />
            <el-option value="inactive" label="停用" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button class="wolf-btn wolf-btn--default" @click="createModalVisible = false">取消</el-button>
        <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleCreateModalOk">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="roleModalVisible"
      title="分配角色"
      width="600px"
      :close-on-click-modal="false"
    >
      <div v-if="selectedUser">
        <p style="margin-bottom: 16px">
          为用户 <strong>{{ selectedUser.name }}</strong> 分配角色
        </p>
        <el-select
          v-model="selectedRoles"
          multiple
          placeholder="请选择角色"
          style="width: 100%"
          clearable
        >
          <el-option v-for="role in allRoles" :key="role.id" :value="role.id" :label="`${role.name} (${role.code})`" />
        </el-select>
      </div>
      <template #footer>
        <el-button class="wolf-btn wolf-btn--default" @click="roleModalVisible = false">取消</el-button>
        <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleRoleModalOk">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Search, Refresh, ArrowLeft } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import userApi, { type UserResponse, type UserCreate, type UserUpdate, UserStatus } from '@/api/user'
import roleApi, { type RoleResponse } from '@/api/role'
import { usePermissionStore } from '@/stores/permissions'
import { useTeamStore } from '@/stores/team'

const router = useRouter()
const permissionStore = usePermissionStore()
const teamStore = useTeamStore()
const loading = ref(false)
const tableData = ref<UserResponse[]>([])
const selectedUser = ref<UserResponse | null>(null)
const isEditMode = ref(false)

const searchForm = reactive({
  status: null as UserStatus | null,
  region: ''
})

const canManageUser = computed(() => 
  permissionStore.hasPermission('user:manage')
)

const canAssignRoles = computed(() => 
  permissionStore.hasPermission('role:manage')
)

const handleBack = () => {
  router.push('/settings')
}

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

const createModalVisible = ref(false)
const createFormRef = ref<FormInstance>()
const roleModalVisible = ref(false)
const allRoles = ref<RoleResponse[]>([])
const selectedRoles = ref<number[]>([])
const createForm = reactive<UserCreate & { status?: UserStatus }>({
  name: '',
  email: '',
  mobile: '',
  avatar_url: '',
  region: '',
  status: UserStatus.ACTIVE
})

const createFormRules: FormRules = {
  name: [{ required: true, message: '请输入姓名' }],
  email: [{ required: true, message: '请输入邮箱' }, { type: 'email', message: '请输入正确的邮箱格式' }]
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

const fetchUsers = async () => {
  loading.value = true
  try {
    const params: any = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize
    }

    if (searchForm.status) {
      params.status = searchForm.status
    }
    if (searchForm.region) {
      params.region = searchForm.region
    }

    const data = await userApi.getUsers(params) as any
    tableData.value = data
    pagination.total = data.length
  } catch (error: any) {
    console.error('获取用户列表失败', error)
    ElMessage.error('获取用户列表失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.current = 1
  fetchUsers()
}

const handleReset = () => {
  searchForm.status = null
  searchForm.region = ''
  pagination.current = 1
  fetchUsers()
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchUsers()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchUsers()
}

const showCreateModal = () => {
  isEditMode.value = false
  Object.assign(createForm, {
    name: '',
    email: '',
    mobile: '',
    avatar_url: '',
    region: '',
    status: UserStatus.ACTIVE
  })
  createModalVisible.value = true
}

const handleEdit = (record: UserResponse) => {
  selectedUser.value = record
  isEditMode.value = true
  Object.assign(createForm, {
    name: record.name,
    email: record.email || '',
    mobile: record.mobile || '',
    avatar_url: record.avatar_url || '',
    region: record.region || '',
    status: record.status
  })
  createModalVisible.value = true
}

const handleCreateModalOk = async () => {
  if (!createFormRef.value) return
  
  try {
    await createFormRef.value.validate()
    
    if (isEditMode.value && selectedUser.value) {
      const updateData: UserUpdate = {
        name: createForm.name,
        email: createForm.email,
        mobile: createForm.mobile,
        avatar_url: createForm.avatar_url,
        region: createForm.region,
        status: createForm.status
      }
      await userApi.updateUser(selectedUser.value.id, updateData)
      ElMessage.success('更新成功')
    } else {
      await userApi.createUser(createForm)
      ElMessage.success('创建成功')
    }
    
    createModalVisible.value = false
    fetchUsers()
  } catch (error: any) {
    console.error('操作失败', error)
    ElMessage.error(error.response?.data?.detail || error.message || '操作失败')
  }
}

const handleDelete = (record: UserResponse) => {
  ElMessageBox.confirm(
    `确定要删除用户"${record.name}"吗？删除后不可恢复。`,
    '确认删除',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await userApi.deleteUser(record.id)
      ElMessage.success('删除成功')
      fetchUsers()
    } catch (error: any) {
      console.error('删除失败', error)
      ElMessage.error(error.response?.data?.detail || error.message || '删除失败')
    }
  }).catch(() => {
    
  })
}

const fetchAllRoles = async () => {
  try {
    const data = await roleApi.getRoles() as any
    allRoles.value = data
  } catch (error: any) {
    console.error('获取角色列表失败', error)
  }
}

const handleAssignRoles = async (record: UserResponse) => {
  selectedUser.value = record
  await fetchAllRoles()
  
  const userRoles = record.roles || []
  const userRoleCodes = userRoles.map(role => role.code)
  
  if (userRoleCodes.length === 0) {
    selectedRoles.value = []
  } else {
    selectedRoles.value = allRoles.value
      .filter(role => userRoleCodes.includes(role.code))
      .map(role => role.id)
  }
  
  roleModalVisible.value = true
}

const handleRoleModalOk = async () => {
  if (!selectedUser.value) return

  const teamId = teamStore.currentTeam?.id
  if (!teamId) {
    ElMessage.error('请先选择团队')
    return
  }

  try {
    const userId = selectedUser.value.id
    const userRoleCodes = selectedUser.value.roles.map(role => role.code)

    for (const role of allRoles.value) {
      const hasRole = selectedRoles.value.includes(role.id)
      const userHadRole = userRoleCodes.includes(role.code)

      if (hasRole && !userHadRole) {
        await roleApi.assignRoleToUser(role.id, userId, teamId)
      } else if (!hasRole && userHadRole) {
        await roleApi.removeRoleFromUser(role.id, userId, teamId)
      }
    }

    ElMessage.success('角色分配成功')
    roleModalVisible.value = false
    fetchUsers()
  } catch (error: any) {
    console.error('角色分配失败', error)
    ElMessage.error(error.response?.data?.detail || error.message || '角色分配失败')
  }
}

onMounted(() => {
  fetchUsers()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.users-container {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.wolf-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  padding: 0;
  margin-bottom: $wolf-space-md;
}

.search-card {
  padding: $wolf-space-md;
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

.text-gray {
  color: $wolf-text-tertiary;
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

.wolf-tag {
  border-radius: $wolf-radius-sm !important;
  padding: 2px 8px !important;
  font-size: $wolf-font-size-caption !important;
  font-weight: $wolf-font-weight-medium !important;
  height: auto !important;
  line-height: 1.5 !important;
  border-width: 1px !important;
}

.wolf-tag--success {
  background-color: $wolf-success-bg !important;
  border-color: $wolf-success-border !important;
  color: $wolf-success-text !important;
}

.wolf-tag--gray {
  background-color: $wolf-purple-bg !important;
  border-color: $wolf-purple-border !important;
  color: $wolf-purple !important;
}

.wolf-tag--info {
  background-color: $wolf-info-bg !important;
  border-color: $wolf-info-border !important;
  color: $wolf-info !important;
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
</style>
