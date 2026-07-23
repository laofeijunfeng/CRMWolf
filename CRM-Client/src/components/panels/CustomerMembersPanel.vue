<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Plus, Pencil, Trash2, Loader2, Users } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import ListCard from '@/components/crmwolf/ListCard.vue'
import customerApi, {
  type CustomerMemberAccessLevel,
  type CustomerMemberCandidate,
  type CustomerMemberResponse,
  type CustomerMemberRole,
} from '@/api/customer'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDialog } from '@/utils/confirmDialog'

interface Props {
  customerId: number
  members: CustomerMemberResponse[]
  canManageMembers?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  refresh: []
}>()

const roleOptions: { value: CustomerMemberRole; label: string }[] = [
  { value: 'SALES', label: '销售' },
  { value: 'PRESALES', label: '售前' },
  { value: 'DELIVERY', label: '交付' },
  { value: 'SUPPORT', label: '支持' },
  { value: 'OTHER', label: '其他' },
]

const accessOptions: { value: CustomerMemberAccessLevel; label: string }[] = [
  { value: 'VIEW', label: '仅查看' },
  { value: 'FOLLOW_UP', label: '可跟进' },
  { value: 'EDIT', label: '可编辑客户' },
]

const dialogOpen = ref(false)
const submitting = ref(false)
const loadingCandidates = ref(false)
const editingMember = ref<CustomerMemberResponse | null>(null)
const candidates = ref<CustomerMemberCandidate[]>([])

const form = reactive({
  userId: '',
  memberRole: 'PRESALES' as CustomerMemberRole,
  accessLevel: 'VIEW' as CustomerMemberAccessLevel,
  remark: '',
})

const canManage = computed(() => props.canManageMembers === true || props.members.some(item => item.can_manage))
const availableCandidates = computed(() => candidates.value.filter(item => !item.already_member || item.id === form.userId))

const getRoleLabel = (value: string): string => roleOptions.find(item => item.value === value)?.label ?? value
const getAccessLabel = (value: string): string => accessOptions.find(item => item.value === value)?.label ?? value

const resetForm = (): void => {
  form.userId = ''
  form.memberRole = 'PRESALES'
  form.accessLevel = 'VIEW'
  form.remark = ''
  editingMember.value = null
}

const loadCandidates = async (): Promise<void> => {
  loadingCandidates.value = true
  try {
    candidates.value = await customerApi.getCustomerMemberCandidates(props.customerId)
  } catch (error) {
    handleApiError(error, '获取客户团队成员候选人')
  } finally {
    loadingCandidates.value = false
  }
}

const openCreateDialog = async (): Promise<void> => {
  resetForm()
  dialogOpen.value = true
  await loadCandidates()
}

const openEditDialog = async (member: CustomerMemberResponse): Promise<void> => {
  editingMember.value = member
  form.userId = member.user_id
  form.memberRole = member.member_role
  form.accessLevel = member.access_level
  form.remark = member.remark ?? ''
  dialogOpen.value = true
  await loadCandidates()
}

const handleSubmit = async (): Promise<void> => {
  if (submitting.value) return
  if (!editingMember.value && form.userId === '') {
    toast.error('请选择团队成员')
    return
  }

  submitting.value = true
  try {
    const payload = {
      member_role: form.memberRole,
      access_level: form.accessLevel,
      remark: form.remark.trim() === '' ? null : form.remark.trim(),
    }
    if (editingMember.value) {
      await customerApi.updateCustomerMember(props.customerId, editingMember.value.id, payload)
      toast.success('客户团队成员已更新')
    } else {
      await customerApi.addCustomerMember(props.customerId, { ...payload, user_id: form.userId })
      toast.success('客户团队成员已添加')
    }
    dialogOpen.value = false
    emit('refresh')
  } catch (error) {
    handleApiError(error, editingMember.value ? '更新客户团队成员' : '添加客户团队成员')
  } finally {
    submitting.value = false
  }
}

const handleRemove = async (member: CustomerMemberResponse): Promise<void> => {
  const confirmed = await confirmDialog(
    `确定移除 ${member.user_info?.name ?? '该成员'} 吗？移除后该成员将无法通过协作关系访问客户。`,
    '移除成员',
    { variant: 'destructive', confirmText: '移除' }
  )
  if (!confirmed) return

  try {
    await customerApi.removeCustomerMember(props.customerId, member.id)
    toast.success('客户团队成员已移除')
    emit('refresh')
  } catch (error) {
    handleApiError(error, '移除客户团队成员')
  }
}

watch(
  () => props.customerId,
  () => {
    if (dialogOpen.value) {
      dialogOpen.value = false
    }
  }
)
</script>

<template>
  <div class="customer-members-panel">
    <ListCard
      title="客户团队成员"
      :items="members"
      empty-text="暂无协作成员"
    >
      <template #headerActions>
        <Button v-if="canManage" size="sm" variant="outline" @click="openCreateDialog">
          <Plus class="w-4 h-4 mr-1" />
          添加成员
        </Button>
      </template>

      <template #empty>
        <div class="customer-members-panel__empty">
          <Users class="w-5 h-5" />
          <span>暂无协作成员</span>
        </div>
      </template>

      <template #itemMain="{ item }">
        <span class="font-medium text-wolf-text-primary-v2 truncate">{{ item.user_info?.name ?? '-' }}</span>
      </template>

      <template #itemMeta="{ item }">
        <span>{{ getRoleLabel(item.member_role) }}</span>
        <span v-if="item.remark"> · {{ item.remark }}</span>
      </template>

      <template #itemBadges="{ item }">
        <Badge variant="secondary" class="text-xs">{{ getAccessLabel(item.access_level) }}</Badge>
      </template>

      <template #itemActions="{ item }">
        <Button v-if="item.can_manage" variant="ghost" size="icon" class="h-8 w-8" aria-label="编辑成员" @click="openEditDialog(item)">
          <Pencil class="w-4 h-4" />
        </Button>
        <Button v-if="item.can_manage" variant="ghost" size="icon" class="h-8 w-8 text-wolf-danger-text-v2" aria-label="移除成员" @click="handleRemove(item)">
          <Trash2 class="w-4 h-4" />
        </Button>
      </template>
    </ListCard>

    <Dialog v-model:open="dialogOpen">
      <DialogContent class="customer-member-dialog">
        <DialogHeader>
          <DialogTitle>{{ editingMember ? '编辑团队成员' : '添加团队成员' }}</DialogTitle>
        </DialogHeader>

        <form class="customer-member-dialog__form" @submit.prevent="handleSubmit">
          <div class="customer-member-dialog__field">
            <Label for="customer-member-user">成员</Label>
            <Select v-model="form.userId" :disabled="editingMember !== null || loadingCandidates || submitting">
              <SelectTrigger id="customer-member-user">
                <SelectValue :placeholder="loadingCandidates ? '加载中' : '请选择成员'" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="candidate in availableCandidates" :key="candidate.id" :value="candidate.id">
                  {{ candidate.name }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="customer-member-dialog__field">
            <Label for="customer-member-role">角色</Label>
            <Select v-model="form.memberRole" :disabled="submitting">
              <SelectTrigger id="customer-member-role">
                <SelectValue placeholder="请选择角色" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="option in roleOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="customer-member-dialog__field">
            <Label for="customer-member-access">权限</Label>
            <Select v-model="form.accessLevel" :disabled="submitting">
              <SelectTrigger id="customer-member-access">
                <SelectValue placeholder="请选择权限" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="option in accessOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="customer-member-dialog__field">
            <Label for="customer-member-remark">备注</Label>
            <Input id="customer-member-remark" v-model="form.remark" maxlength="500" :disabled="submitting" />
          </div>
        </form>

        <DialogFooter>
          <Button variant="outline" :disabled="submitting" @click="dialogOpen = false">取消</Button>
          <Button :disabled="submitting" @click="handleSubmit">
            <Loader2 v-if="submitting" class="w-4 h-4 mr-1 animate-spin" />
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped lang="scss">
.customer-members-panel {
  margin-top: 0;
}

.customer-members-panel__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 72px;
  color: var(--wolf-text-tertiary-v2);
  font-size: 13px;
}

.customer-member-dialog__form {
  display: grid;
  gap: 14px;
}

.customer-member-dialog__field {
  display: grid;
  gap: 6px;
}
</style>
