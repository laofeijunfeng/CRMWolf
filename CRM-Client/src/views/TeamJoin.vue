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
import { teamJoinSchema, type TeamJoinFormValues } from '@/schemas/team-join.schema'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const router = useRouter()
const teamStore = useTeamStore()
const userStore = useUserStore()

const loading = ref(false)

const { handleSubmit, errors, defineField } = useForm<TeamJoinFormValues>({
  validationSchema: toTypedSchema(teamJoinSchema),
  initialValues: {
    code: '',
  },
})
const [code] = defineField('code')

// UI/UX Pro Max: 验证失败后聚焦第一个无效字段
const focusFirstInvalidField = async (): Promise<void> => {
  await nextTick()
  const firstInvalid = document.querySelector<HTMLInputElement>('input[aria-invalid="true"]')
  firstInvalid?.focus()
}

const onSubmit = handleSubmit(async (values): Promise<void> => {
  loading.value = true
  try {
    await teamStore.joinTeam(values.code)
    toast.success('加入团队成功')
    router.replace(getSafeAuthReturnPath(route.query['redirect']) ?? '/assistant')
  } catch (error: unknown) {
    handleApiError(error, '加入团队')
  } finally {
    loading.value = false
  }
}, focusFirstInvalidField)

const goBack = (): void => {
  router.push('/onboarding')
}

const handleLogout = async (): Promise<void> => {
  if (!(await confirmLogout())) return
  userStore.logout()
  router.push('/login')
}
</script>

<template>
  <AuthShell title="加入已有团队" description="请输入团队邀请码，加入您的团队" show-logout @logout="handleLogout">
    <form class="grid gap-space-4" novalidate @submit.prevent="onSubmit">
      <InputField
        id="invite-code"
        v-model="code"
        label="邀请码"
        placeholder="请输入邀请码"
        maxlength="20"
        helper-text="邀请码长度为 4-20 个字符"
        required
        :disabled="loading"
        :error="errors.code ?? ''"
      />
      <Button type="submit" size="lg" class="w-full" :disabled="loading" :aria-busy="loading">
        {{ loading ? '加入中...' : '加入团队' }}
      </Button>
    </form>

    <template #footer>
      <p class="m-0 text-caption">邀请码由团队管理员提供，通常为6-8位字母数字组合</p>
      <Button variant="ghost" size="sm" class="text-muted-foreground" @click="goBack">
        <ArrowLeft class="size-icon-sm" aria-hidden="true" />
        返回上一步
      </Button>
    </template>
  </AuthShell>
</template>
