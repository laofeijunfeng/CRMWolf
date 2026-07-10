<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { GenericObject } from 'vee-validate'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { leadApi } from '@/api/lead'
import { leadSchema, type LeadForm } from '@/schemas/lead-form'

interface Props {
  open: boolean
  mode: 'create' | 'edit'
  leadId?: number
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 状态
const submitting = ref(false)
const loading = ref(false)
const initialValues = ref<Partial<LeadForm>>({})
const isDirty = ref(false)
const showConfirmDialog = ref(false)

// 计算属性
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

// 选项配置
const sourceOptions: { value: LeadForm['source']; label: string }[] = [
  { value: '线上注册', label: '线上注册' },
  { value: '市场活动', label: '市场活动' },
  { value: '客户推荐', label: '客户推荐' },
  { value: '电话营销', label: '电话营销' },
  { value: '网站咨询', label: '网站咨询' },
  { value: '展会', label: '展会' },
  { value: '其他', label: '其他' }
]

const companyScaleOptions: { value: NonNullable<LeadForm['company_scale']>; label: string }[] = [
  { value: '1-50人', label: '1-50人' },
  { value: '51-200人', label: '51-200人' },
  { value: '201-500人', label: '201-500人' },
  { value: '501-1000人', label: '501-1000人' },
  { value: '1000人以上', label: '1000人以上' }
]

// 监听表单变化（UX 优化：Escape Route）
watch(initialValues, (): void => {
  isDirty.value = true
}, { deep: true })

// 编辑模式：加载线索详情
watch([(): boolean => props.open, (): number | undefined => props.leadId], async ([open, leadId]): void => {
  if (open && props.mode === 'edit' && leadId !== undefined && leadId !== null) {
    loading.value = true
    try {
      const lead = await leadApi.getLeadDetail(leadId)
      initialValues.value = {
        lead_name: lead.lead_name,
        source: lead.source as LeadForm['source'],
        city: lead.city,
        company_scale: lead.company_scale as LeadForm['company_scale'] | undefined,
        contact_name: lead.contact_name,
        contact_phone: lead.contact_phone
        // remark is optional - will be undefined if not supported by API yet
      }
      // 重置 dirty 状态
      setTimeout(() => {
        isDirty.value = false
      }, 100)
    } catch {
      toast.error('加载线索详情失败')
      visible.value = false
    } finally {
      loading.value = false
    }
  }
}, { immediate: true })

// 表单提交处理
const handleSubmit = async (values: GenericObject): void => {
  submitting.value = true
  try {
    const formData = values as LeadForm
    // Build API payload - remark field is optional and may not be in API types yet
    const payload = {
      lead_name: formData.lead_name,
      source: formData.source,
      city: formData.city,
      contact_name: formData.contact_name,
      contact_phone: formData.contact_phone,
      company_scale: formData.company_scale ?? undefined
    }

    if (props.mode === 'create') {
      // Cast to include remark if present (backend may support it)
      await leadApi.createLead({ ...payload, remark: formData.remark } as unknown as { lead_name: string; source: string; city: string; contact_name: string; contact_phone: string; company_scale?: string })
      toast.success('线索创建成功')
    } else if (props.leadId !== undefined) {
      // Cast to include remark if present (backend may support it)
      await leadApi.updateLead(props.leadId, { ...payload, remark: formData.remark } as unknown as { lead_name?: string; source?: string; city?: string; contact_name?: string; contact_phone?: string; company_scale?: string })
      toast.success('线索更新成功')
    }

    isDirty.value = false
    visible.value = false
    emit('success')
  } catch {
    toast.error(props.mode === 'create' ? '创建线索失败' : '更新线索失败')

    // UX 优化：Focus Management - 提交失败后自动聚焦第一个错误字段
    nextTick(() => {
      const errorElement = document.querySelector('[data-invalid="true"]') as HTMLInputElement
      if (errorElement !== null && errorElement !== undefined) {
        errorElement.focus()
      }
    })
  } finally {
    submitting.value = false
  }
}

// 取消操作（UX 优化：Escape Route）
const handleCancel = (): void => {
  if (isDirty.value) {
    showConfirmDialog.value = true
  } else {
    visible.value = false
  }
}

// 确认放弃更改
const confirmCancel = (): void => {
  showConfirmDialog.value = false
  visible.value = false
}

// 继续编辑
const continueEditing = (): void => {
  showConfirmDialog.value = false
}
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="sm:max-w-[600px]">
      <DialogHeader>
        <DialogTitle>{{ mode === 'create' ? '新建线索' : '编辑线索' }}</DialogTitle>
      </DialogHeader>

      <div v-if="loading" class="flex justify-center py-8">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>

      <Form
        v-else
        :schema="leadSchema"
        :initial-values="initialValues"
        @submit="handleSubmit"
      >
        <!-- 基本信息 Section -->
        <div class="space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <!-- 线索名称 -->
            <FormField v-slot="{ componentField }" name="lead_name">
              <FormItem>
                <FormLabel>线索名称 *</FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField"
                    autocomplete="organization"
                    class="h-11 sm:h-8"
                    placeholder="请输入线索名称"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- 线索来源 -->
            <FormField v-slot="{ componentField }" name="source">
              <FormItem>
                <FormLabel>线索来源 *</FormLabel>
                <Select v-bind="componentField">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择来源" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      v-for="option in sourceOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- 所在城市 -->
            <FormField v-slot="{ componentField }" name="city">
              <FormItem>
                <FormLabel>所在城市 *</FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField"
                    autocomplete="address-level2"
                    class="h-11 sm:h-8"
                    placeholder="请输入城市"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- 公司规模 -->
            <FormField v-slot="{ componentField }" name="company_scale">
              <FormItem>
                <FormLabel>公司规模</FormLabel>
                <Select v-bind="componentField">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择规模" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      v-for="option in companyScaleOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- 联系人姓名 -->
            <FormField v-slot="{ componentField }" name="contact_name">
              <FormItem>
                <FormLabel>联系人姓名 *</FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField"
                    autocomplete="name"
                    class="h-11 sm:h-8"
                    placeholder="请输入联系人姓名"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- 联系电话（UX 优化：Input Types） -->
            <FormField v-slot="{ componentField }" name="contact_phone">
              <FormItem>
                <FormLabel>联系电话 *</FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField"
                    type="tel"
                    autocomplete="tel"
                    class="h-11 sm:h-8"
                    placeholder="请输入联系电话"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>
          </div>

          <!-- 备注（全宽） -->
          <FormField v-slot="{ componentField }" name="remark">
            <FormItem>
              <FormLabel>备注</FormLabel>
              <FormControl>
                <Textarea
                  v-bind="componentField"
                  :rows="4"
                  placeholder="请输入备注信息（可选）"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>
        </div>

        <!-- DialogFooter 在 Form 内部 -->
        <DialogFooter class="mt-6 pt-4 border-t">
          <Button variant="outline" type="button" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :loading="submitting">
            {{ mode === 'create' ? '创建' : '保存' }}
          </Button>
        </DialogFooter>
      </Form>
    </DialogContent>
  </Dialog>

  <!-- UX 优化：Escape Route - 未保存更改确认对话框 -->
  <AlertDialog v-model:open="showConfirmDialog">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>放弃更改？</AlertDialogTitle>
        <AlertDialogDescription>
          您有未保存的更改，确定要关闭吗？
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel @click="continueEditing">
          继续编辑
        </AlertDialogCancel>
        <AlertDialogAction @click="confirmCancel">
          放弃更改
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>