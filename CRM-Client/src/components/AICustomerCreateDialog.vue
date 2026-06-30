<template>
  <el-dialog
    v-model="visible"
    title="AI 智能创建客户"
    width="600px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 阶段 1：输入 -->
    <div v-if="stage === 'input'">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="4"
        placeholder="例如：阿里巴巴，杭州，张三 13800138000 技术总监，大概500人，互联网公司"
        :disabled="isParsing"
        @keydown.ctrl.enter="handleParse"
      />
      <div class="actions">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" :loading="isParsing" @click="handleParse">
          <el-icon><MagicStick /></el-icon>
          智能识别
        </el-button>
      </div>
    </div>

    <!-- 阶段 2：解析 -->
    <div v-if="stage === 'parsing'">
      <el-icon class="loading"><Loading /></el-icon>
      <span>{{ statusMessage }}</span>
    </div>

    <!-- 阶段 3：预览 -->
    <div v-if="stage === 'preview'">
      <el-form ref="formRef" :model="form" label-position="top">
        <el-form-item label="客户名称" required>
          <el-input v-model="form.account_name" />
        </el-form-item>
        <el-form-item label="所在城市" required>
          <el-input v-model="form.city" />
        </el-form-item>
        <el-form-item label="联系人姓名" required>
          <el-input v-model="form.contact_name" />
        </el-form-item>
        <el-form-item label="联系电话" required>
          <el-input v-model="form.contact_phone" />
        </el-form-item>
      </el-form>
      <div class="actions">
        <el-button @click="stage = 'input'">返回</el-button>
        <el-button type="primary" :loading="isCreating" @click="handleCreate">
          创建客户
        </el-button>
      </div>
    </div>

    <!-- 阶段 4：成功 -->
    <div v-if="stage === 'success'">
      <el-icon><CircleCheckFilled /></el-icon>
      <p>客户创建成功！AI 正在生成客户档案</p>
      <el-button type="primary" @click="handleViewCustomer">查看客户</el-button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick, Loading, CircleCheckFilled } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { customerAiCreateApi } from '@/api/customerAICreate'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'success'): void }>()
const router = useRouter()
const userStore = useUserStore()

const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })
const stage = ref<'input' | 'parsing' | 'preview' | 'success'>('input')
const inputText = ref('')
const isParsing = ref(false)
const isCreating = ref(false)
const statusMessage = ref('')
const customerId = ref<number | null>(null)

const form = ref({
  account_name: '',
  city: '',
  contact_name: '',
  contact_phone: ''
})

const handleClose = () => {
  stage.value = 'input'
  inputText.value = ''
  visible.value = false
}

const handleParse = async () => {
  if (!inputText.value.trim()) return
  
  stage.value = 'parsing'
  isParsing.value = true
  statusMessage.value = '正在解析...'

  try {
    await customerAiCreateApi.parseSSE(
      { content: inputText.value },
      (event) => {
        if (event.event === 'status') statusMessage.value = event.message || ''
        if (event.event === 'parsed' && event.customer_info) {
          form.value = {
            account_name: event.customer_info.account_name || '',
            city: event.customer_info.city || '',
            contact_name: event.contact_info?.contact_name || '',
            contact_phone: event.contact_info?.contact_phone || ''
          }
          stage.value = 'preview'
        }
        if (event.event === 'error') {
          ElMessage.error(event.message || '解析失败')
          stage.value = 'input'
        }
      },
      userStore.token || ''
    )
  } catch (error) {
    ElMessage.error('解析请求失败')
    stage.value = 'input'
  } finally {
    isParsing.value = false
  }
}

const handleCreate = async () => {
  isCreating.value = true
  try {
    const response = await customerAiCreateApi.createFromAI({
      customer_info: { account_name: form.value.account_name, city: form.value.city, missing_fields: [] },
      contact_info: { contact_name: form.value.contact_name, contact_phone: form.value.contact_phone }
    })
    if (response.id) {
      customerId.value = response.id
      stage.value = 'success'
      emit('success')
    }
  } catch (error) {
    ElMessage.error('创建失败')
  } finally {
    isCreating.value = false
  }
}

const handleViewCustomer = () => {
  if (customerId.value) router.push(`/customers/${customerId.value}`)
  handleClose()
}
</script>

<style scoped>
.actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.loading { animation: spin 1s infinite; }
@keyframes spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }
</style>
