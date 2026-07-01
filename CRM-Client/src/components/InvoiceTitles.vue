<template>
  <div class="invoice-tiles-wrapper">
    <div class="invoice-titles-toolbar">
      <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="handleCreate">
        <el-icon><Plus /></el-icon>
        添加抬头
      </el-button>
    </div>
    <el-table
      :data="invoiceTitles"
      v-loading="loading"
      :border="false"
      style="width: 100%"
      class="invoice-titles-table"
    >
      <el-table-column label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.title_type === 'COMPANY'" type="primary" size="small">单位</el-tag>
          <el-tag v-else type="success" size="small">个人</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="开票抬头" prop="title" min-width="200" />
      <el-table-column label="纳税人识别号" prop="taxpayer_id" min-width="160" />
      <el-table-column label="开户行" prop="bank_name" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <span :class="{ 'text-muted': !row.bank_name }">{{ row.bank_name || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="开户账号" prop="bank_account" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <span :class="{ 'text-muted': !row.bank_account }">{{ row.bank_account || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="地址" prop="address" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <span :class="{ 'text-muted': !row.address }">{{ row.address || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="电话" prop="phone" width="120">
        <template #default="{ row }">
          <span :class="{ 'text-muted': !row.phone }">{{ row.phone || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="默认" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
          <el-button v-else class="wolf-btn wolf-btn--link" type="primary" link size="small" @click="handleSetDefault(row)">
            设为默认
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right" align="center">
        <template #default="{ row }">
          <el-button class="wolf-btn wolf-btn--link" type="primary" link size="small" @click="handleEdit(row)">
            编辑
          </el-button>
          <el-button class="wolf-btn wolf-btn--link" type="danger" link size="small" @click="handleDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && invoiceTitles.length === 0" description="暂无发票抬头" />

    <el-dialog
      v-model="modalVisible"
      :title="isEditing ? '编辑发票抬头' : '添加发票抬头'"
      width="600px"
      :close-on-click-modal="false"
      class="invoice-title-form-dialog"
    >
      <el-form :model="formData" :rules="formRules" label-width="100px" ref="formRef">
        <el-form-item prop="title_type" label="抬头类型" required>
          <el-radio-group v-model="formData.title_type">
            <el-radio value="COMPANY">单位</el-radio>
            <el-radio value="PERSONAL">个人</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item prop="title" label="开票抬头" required>
          <el-input v-model="formData.title" placeholder="请输入开票抬头" :maxlength="255" show-word-limit />
        </el-form-item>

        <el-form-item prop="taxpayer_id" label="纳税人识别号" required>
          <el-input v-model="formData.taxpayer_id" placeholder="请输入纳税人识别号" :maxlength="100" />
        </el-form-item>

        <el-form-item prop="bank_name" label="开户行">
          <el-input v-model="formData.bank_name" placeholder="选填" :maxlength="255" />
        </el-form-item>

        <el-form-item prop="bank_account" label="开户账号">
          <el-input v-model="formData.bank_account" placeholder="选填" :maxlength="100" />
        </el-form-item>

        <el-form-item prop="address" label="开票地址">
          <el-input v-model="formData.address" placeholder="选填" :maxlength="500" show-word-limit />
        </el-form-item>

        <el-form-item prop="phone" label="电话">
          <el-input v-model="formData.phone" placeholder="选填" :maxlength="50" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modalVisible = false">取消</el-button>
        <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import invoiceApi, { 
  type InvoiceTitleResponse, 
  type InvoiceTitleCreate, 
  type TitleType 
} from '@/api/invoice'

interface Props {
  customerId: number
}

const props = defineProps<Props>()
const emit = defineEmits(['title-updated'])

const loading = ref(false)
const invoiceTitles = ref<InvoiceTitleResponse[]>([])
const modalVisible = ref(false)
const isEditing = ref(false)
const formRef = ref()
const currentEditId = ref<number | null>(null)

const formData = ref<InvoiceTitleCreate>({
  title_type: 'COMPANY',
  title: '',
  taxpayer_id: '',
  bank_name: '',
  bank_account: '',
  address: '',
  phone: ''
})

const formRules = {
  title_type: [{ required: true, message: '请选择抬头类型' }],
  title: [
    { required: true, message: '请输入开票抬头' },
    { min: 1, max: 255, message: '开票抬头长度为1-255个字符' }
  ],
  taxpayer_id: [
    { required: true, message: '请输入纳税人识别号' },
    { min: 1, max: 100, message: '纳税人识别号长度为1-100个字符' }
  ]
}

const fetchInvoiceTitles = async () => {
  loading.value = true
  try {
    const response = await invoiceApi.getInvoiceTitles(props.customerId)
    invoiceTitles.value = response.invoice_titles || []
  } catch (error) {
    console.error('获取开票抬头失败', error)
    ElMessage.error('获取开票抬头失败')
  } finally {
    loading.value = false
  }
}

const handleCreate = () => {
  isEditing.value = false
  currentEditId.value = null
  formData.value = {
    title_type: 'COMPANY',
    title: '',
    taxpayer_id: '',
    bank_name: '',
    bank_account: '',
    address: '',
    phone: ''
  }
  modalVisible.value = true
}

const handleEdit = (record: InvoiceTitleResponse) => {
  isEditing.value = true
  currentEditId.value = record.id
  formData.value = {
    title_type: record.title_type,
    title: record.title,
    taxpayer_id: record.taxpayer_id,
    bank_name: record.bank_name || '',
    bank_account: record.bank_account || '',
    address: record.address || '',
    phone: record.phone || ''
  }
  modalVisible.value = true
}

const handleSubmit = async () => {
  try {
    await formRef.value.validate()
    
    if (isEditing.value && currentEditId.value) {
      await invoiceApi.updateInvoiceTitle(currentEditId.value, formData.value)
      ElMessage.success('更新成功')
    } else {
      await invoiceApi.createInvoiceTitle(props.customerId, formData.value)
      ElMessage.success('添加成功')
    }
    
    modalVisible.value = false
    fetchInvoiceTitles()
    emit('title-updated')
  } catch (error: unknown) {
    if (error.response?.data?.detail) {
      ElMessage.error(error.response.data.detail)
    } else {
      console.error('保存失败', error)
      ElMessage.error('保存失败')
    }
  }
}

const handleDelete = (record: InvoiceTitleResponse) => {
  ElMessageBox.confirm(
    `确定要删除开票抬头"${record.title}"吗？`,
    '确认删除',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await invoiceApi.deleteInvoiceTitle(record.id)
      ElMessage.success('删除成功')
      fetchInvoiceTitles()
      emit('title-updated')
    } catch (error) {
      console.error('删除失败', error)
      ElMessage.error('删除失败')
    }
  }).catch(() => {
  })
}

const handleSetDefault = async (record: InvoiceTitleResponse) => {
  try {
    await invoiceApi.setDefaultInvoiceTitle(record.id)
    ElMessage.success('设置成功')
    fetchInvoiceTitles()
    emit('title-updated')
  } catch (error) {
    console.error('设置失败', error)
    ElMessage.error('设置失败')
  }
}

onMounted(() => {
  fetchInvoiceTitles()
})

defineExpose({
  refresh: fetchInvoiceTitles
})
</script>

<style scoped lang="scss">
.invoice-tiles-wrapper {
  width: 100%;
}

.invoice-titles-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--wolf-space-4);
}

.invoice-titles-table {
  :deep(.el-table__header-wrapper) {
    th {
      background: var(--wolf-bg-secondary);
      color: var(--wolf-text-secondary);
      font-weight: var(--wolf-font-weight-medium);
      font-size: var(--wolf-font-size-small);
    }
  }

  :deep(.el-table__body-wrapper) {
    td {
      color: var(--wolf-text-primary);
      font-size: var(--wolf-font-size-body);
    }
  }
}

.text-muted {
  color: var(--wolf-text-tertiary);
}

.invoice-title-form-dialog {
  :deep(.el-dialog__header) {
    padding: var(--wolf-space-5) var(--wolf-space-6);
    border-bottom: 1px solid var(--wolf-border-color);
    margin: 0;
  }

  :deep(.el-dialog__title) {
    font-size: var(--wolf-font-size-large);
    font-weight: var(--wolf-font-weight-semibold);
    color: var(--wolf-text-primary);
  }

  :deep(.el-dialog__body) {
    padding: var(--wolf-space-6);
  }

  :deep(.el-dialog__footer) {
    padding: var(--wolf-space-4) var(--wolf-space-6);
    border-top: 1px solid var(--wolf-border-color);
  }

  :deep(.el-dialog__headerbtn) {
    top: var(--wolf-space-5);
    right: var(--wolf-space-6);
  }
}
</style>
