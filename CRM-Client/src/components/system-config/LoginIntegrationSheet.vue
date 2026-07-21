<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Copy, Save } from 'lucide-vue-next'
import { Sheet, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { oauthApi, type OAuthProviderConfigResponse, type OAuthProviderConfigUpdate } from '@/api/oauth'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  open: boolean
}

type Emits = (e: 'update:open', value: boolean) => void

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const loading = ref(false)
const saving = ref(false)
const config = ref<OAuthProviderConfigResponse | null>(null)

const callbackUrl = computed(() => `${window.location.origin}/auth/feishu/callback`)

const schema = toTypedSchema(z.object({
  enabled: z.boolean().default(false),
  app_id: z.string().trim().min(1, '请输入 App ID').max(128, 'App ID 不能超过128个字符'),
  app_secret: z.string().trim().max(255, 'App Secret 不能超过255个字符').optional(),
  redirect_uri: z.string().trim().url('请输入有效的重定向 URL').max(500, '重定向 URL 不能超过500个字符'),
}))

const { handleSubmit, resetForm, setFieldValue, values } = useForm({
  validationSchema: schema,
  initialValues: {
    enabled: false,
    app_id: '',
    app_secret: '',
    redirect_uri: callbackUrl.value,
  }
})

const fetchConfig = async (): Promise<void> => {
  loading.value = true
  try {
    const response = await oauthApi.getFeishuConfig()
    config.value = response
    resetForm({
      values: {
        enabled: response.enabled,
        app_id: response.app_id ?? '',
        app_secret: '',
        redirect_uri: response.redirect_uri ?? callbackUrl.value,
      }
    })
  } catch (error) {
    handleApiError(error, '获取登录集成配置')
  } finally {
    loading.value = false
  }
}

const onSubmit = handleSubmit(async (formValues) => {
  saving.value = true
  try {
    const payload: OAuthProviderConfigUpdate = {
      enabled: formValues.enabled ?? false,
      app_id: formValues.app_id ?? '',
      redirect_uri: formValues.redirect_uri ?? callbackUrl.value,
    }
    if (formValues.app_secret !== undefined && formValues.app_secret.trim().length > 0) {
      payload.app_secret = formValues.app_secret
    }
    const response = await oauthApi.updateFeishuConfig(payload)
    config.value = response
    resetForm({
      values: {
        enabled: response.enabled,
        app_id: response.app_id ?? '',
        app_secret: '',
        redirect_uri: response.redirect_uri ?? callbackUrl.value,
      }
    })
    toast.success('登录集成配置已保存')
  } catch (error) {
    handleApiError(error, '保存登录集成配置')
  } finally {
    saving.value = false
  }
})

const copyCallbackUrl = async (): Promise<void> => {
  try {
    await navigator.clipboard.writeText(values.redirect_uri ?? callbackUrl.value)
    toast.success('重定向 URL 已复制')
  } catch {
    toast.warning('复制失败，请手动复制')
  }
}

watch(() => props.open, (open) => {
  if (open) void fetchConfig()
})
</script>

<template>
  <Sheet :open="open" @update:open="emit('update:open', $event)">
    <DetailSheetContent>
      <SheetHeader class="system-config-sheet-header">
        <SheetTitle class="text-base font-semibold text-wolf-text-primary">登录集成</SheetTitle>
        <SheetDescription class="text-sm text-wolf-text-secondary">配置当前团队的飞书授权登录</SheetDescription>
      </SheetHeader>

      <ScrollArea class="h-full">
        <div class="p-4 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle class="text-base">飞书登录</CardTitle>
              <CardDescription>当前配置只对本团队生效。</CardDescription>
            </CardHeader>
            <CardContent>
              <form class="space-y-4" @submit.prevent="onSubmit">
                <FormField v-slot="{ value }" name="enabled">
                  <FormItem>
                    <div class="flex items-center justify-between gap-4">
                      <div class="space-y-0.5">
                        <FormLabel>启用飞书登录</FormLabel>
                        <p class="text-xs text-muted-foreground">启用后，团队邀请链接将使用飞书登录。</p>
                      </div>
                      <FormControl>
                        <Switch
                          :model-value="value ?? false"
                          :disabled="loading || saving"
                          @update:model-value="(checked: boolean) => setFieldValue('enabled', checked)"
                        />
                      </FormControl>
                    </div>
                  </FormItem>
                </FormField>

                <FormField v-slot="{ value, handleChange, handleBlur }" name="app_id">
                  <FormItem>
                    <FormLabel>App ID</FormLabel>
                    <FormControl>
                      <Input :model-value="value" :disabled="loading || saving" autocomplete="off" @update:model-value="handleChange" @blur="handleBlur" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                </FormField>

                <FormField v-slot="{ value, handleChange, handleBlur }" name="app_secret">
                  <FormItem>
                    <FormLabel>App Secret</FormLabel>
                    <FormControl>
                      <Input
                        :model-value="value"
                        :placeholder="config?.app_secret_configured ? '已配置，留空则不修改' : '请输入 App Secret'"
                        :disabled="loading || saving"
                        type="password"
                        autocomplete="new-password"
                        @update:model-value="handleChange"
                        @blur="handleBlur"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                </FormField>

                <FormField v-slot="{ value, handleChange, handleBlur }" name="redirect_uri">
                  <FormItem>
                    <FormLabel>重定向 URL</FormLabel>
                    <div class="flex items-start gap-2">
                      <FormControl>
                        <Input class="flex-1" :model-value="value" :disabled="loading || saving" @update:model-value="handleChange" @blur="handleBlur" />
                      </FormControl>
                      <Button type="button" variant="outline" size="icon" aria-label="复制重定向 URL" @click="copyCallbackUrl">
                        <Copy class="h-4 w-4" />
                      </Button>
                    </div>
                    <FormMessage />
                  </FormItem>
                </FormField>

                <div class="flex justify-end pt-4">
                  <Button type="submit" :disabled="loading || saving">
                    <Save class="mr-2 h-4 w-4" />
                    {{ saving ? '正在保存...' : '保存配置' }}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      </ScrollArea>
    </DetailSheetContent>
  </Sheet>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.system-config-sheet-header {
  padding: $wolf-space-xl-v2;
  padding-bottom: $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-default-v2;
  background: $wolf-bg-card-v2;
}
</style>
