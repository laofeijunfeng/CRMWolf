<template>
  <AuthShell title="创建新团队" description="创建团队后，您将成为团队管理员" show-logout @logout="handleLogout">
    <form class="grid gap-space-4" novalidate @submit.prevent="onSubmit">
      <InputField
        id="team-name"
        v-model="name"
        label="团队名称"
        placeholder="请输入团队名称"
        maxlength="50"
        helper-text="团队名称长度为 2-50 个字符"
        required
        :disabled="loading"
        :error="errors.name ?? ''"
      />
      <Button type="submit" size="lg" class="w-full" :disabled="loading" :aria-busy="loading">
        {{ loading ? '创建中...' : '创建团队' }}
      </Button>
    </form>

    <template #footer>
      <Button variant="ghost" size="sm" class="text-muted-foreground" @click="goBack">
        <ArrowLeft class="size-icon-sm" aria-hidden="true" />
        返回上一步
      </Button>
    </template>
  </AuthShell>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { ArrowLeft } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/crmwolf'
import AuthShell from '@/layouts/AuthShell.vue'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { confirmLogout } from '@/utils/confirmDialog'
import { getSafeAuthReturnPath } from '@/utils/authRecovery'
import { teamCreateSchema, type TeamCreateFormValues } from '@/schemas/team-create.schema'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const router = useRouter()
const teamStore = useTeamStore()
const userStore = useUserStore()

const loading = ref(false)

const { handleSubmit, errors, defineField } = useForm<TeamCreateFormValues>({
  validationSchema: toTypedSchema(teamCreateSchema),
  initialValues: {
    name: '',
  },
})
const [name] = defineField('name')

// UI/UX Pro Max: 验证失败后聚焦第一个无效字段
const focusFirstInvalidField = async (): Promise<void> => {
  await nextTick()
  const firstInvalid = document.querySelector<HTMLInputElement>('input[aria-invalid="true"]')
  firstInvalid?.focus()
}

const onSubmit = handleSubmit(async (values): Promise<void> => {
  loading.value = true
  try {
    await teamStore.createTeam(values.name)
    toast.success('团队创建成功')
    router.replace(getSafeAuthReturnPath(route.query['redirect']) ?? '/assistant')
  } catch (error: unknown) {
    handleApiError(error, '创建团队')
  } finally {
    loading.value = false
  }
}, focusFirstInvalidField) // 验证失败时聚焦

const goBack = (): void => {
  router.push('/onboarding')
}

const handleLogout = async (): Promise<void> => {
  if (!(await confirmLogout())) return
  userStore.logout()
  router.push('/login')
}
</script>
