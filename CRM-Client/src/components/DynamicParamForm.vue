<template>
  <div class="dynamic-param-form">
    <!-- 缺失字段提示 -->
    <div v-if="computedMissingParams.length > 0" class="missing-fields-tip">
      <el-icon><WarningFilled /></el-icon>
      <span>以下必填信息未能识别，请手动补充：</span>
      <span class="missing-list">{{ formatMissingParams(computedMissingParams) }}</span>
    </div>

    <!-- 动态表单 -->
    <el-form
      ref="formRef"
      :model="formModel"
      :rules="formRules"
      label-position="top"
      class="param-form"
    >
      <div class="form-grid">
        <el-form-item
          v-for="(def, paramName) in paramDefinitions"
          :key="paramName"
          :label="def?.label"
          :prop="paramName"
          :required="def?.required"
          :class="{ 'full-width': def?.type === 'textarea' }"
        >
          <!-- 文本输入 -->
          <el-input
            v-if="def?.type === 'text'"
            v-model="formModel[paramName]"
            :placeholder="def?.placeholder"
          />

          <!-- 数字输入 -->
          <el-input-number
            v-else-if="def?.type === 'number'"
            v-model="formModel[paramName]"
            :placeholder="def?.placeholder"
            :min="0"
            :controls="false"
            style="width: 100%"
          />

          <!-- 日期选择 -->
          <el-date-picker
            v-else-if="def?.type === 'date'"
            v-model="formModel[paramName]"
            type="date"
            :placeholder="def?.placeholder"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />

          <!-- 下拉选择 -->
          <el-select
            v-else-if="def?.type === 'select'"
            v-model="formModel[paramName]"
            :placeholder="def?.placeholder"
            style="width: 100%"
          >
            <el-option
              v-for="opt in def?.options"
              :key="opt.value"
              :value="opt.value"
              :label="opt.label"
            />
          </el-select>

          <!-- 多行文本 -->
          <el-input
            v-else-if="def?.type === 'textarea'"
            v-model="formModel[paramName]"
            type="textarea"
            :rows="3"
            :placeholder="def?.placeholder"
          />
        </el-form-item>
      </div>
    </el-form>

    <!-- 操作按钮 -->
    <div class="form-actions">
      <el-button @click="handleCancel">取消</el-button>
      <el-button
        type="primary"
        :disabled="hasMissingRequiredFields"
        :loading="loading"
        @click="handleSubmit"
      >
        {{ submitText }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'

interface ParamDefinition {
  label: string
  type: 'text' | 'number' | 'date' | 'select' | 'textarea'
  required: boolean
  placeholder: string
  default_value?: string
  options?: { value: string; label: string }[]
}

interface Props {
  paramDefinitions: Record<string, ParamDefinition>
  initialValues?: Record<string, unknown> | undefined
  missingParams?: string[] | undefined
  loading?: boolean | undefined
  submitText?: string | undefined
}

interface Emits {
  (e: 'submit', values: Record<string, unknown>): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  initialValues: () => ({}),
  missingParams: () => [],
  loading: false,
  submitText: '确认提交'
})

const emit = defineEmits<Emits>()

const formRef = ref()

// 表单模型
const formModel = reactive<Record<string, unknown>>({})

// 计算缺失参数
const computedMissingParams = computed(() => props.missingParams || [])

// 初始化表单值
const initFormModel = () => {
  for (const paramName in props.paramDefinitions) {
    const def = props.paramDefinitions[paramName]
    if (!def) continue

    // 优先使用初始值，其次使用默认值，最后为空
    if (props.initialValues && props.initialValues[paramName] !== undefined) {
      formModel[paramName] = props.initialValues[paramName]
    } else if (def.default_value) {
      formModel[paramName] = def.default_value
    } else {
      // 根据类型设置默认空值
      if (def.type === 'number') {
        formModel[paramName] = undefined
      } else {
        formModel[paramName] = ''
      }
    }
  }
}

// 生成验证规则
const formRules = computed(() => {
  const rules: Record<string, { required: boolean; message: string; trigger: string }[]> = {}
  for (const paramName in props.paramDefinitions) {
    const def = props.paramDefinitions[paramName]
    if (def && def.required) {
      rules[paramName] = [
        { required: true, message: `请输入${def.label}`, trigger: 'blur' }
      ]
    }
  }
  return rules
})

// 计算是否有缺失必填字段
const hasMissingRequiredFields = computed(() => {
  for (const paramName in props.paramDefinitions) {
    const def = props.paramDefinitions[paramName]
    if (def && def.required) {
      const value = formModel[paramName]
      if (value === undefined || value === null || value === '') {
        return true
      }
    }
  }
  return false
})

// 格式化缺失字段
const formatMissingParams = (params: string[]) => {
  const labels: Record<string, string> = {}
  for (const paramName in props.paramDefinitions) {
    const def = props.paramDefinitions[paramName]
    if (def) {
      labels[paramName] = def.label
    }
  }
  return params.map(p => labels[p] || p).join('、')
}

// 处理提交
const handleSubmit = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
    emit('submit', { ...formModel })
  } catch {
    // 验证失败
  }
}

// 处理取消
const handleCancel = () => {
  emit('cancel')
}

// 监听参数定义变化，重新初始化
watch(() => props.paramDefinitions, initFormModel, { deep: true, immediate: true })

// 监听初始值变化，更新表单
watch(() => props.initialValues, (newValues) => {
  if (newValues) {
    for (const paramName in newValues) {
      if (formModel.hasOwnProperty(paramName)) {
        formModel[paramName] = newValues[paramName]
      }
    }
  }
}, { deep: true })

onMounted(initFormModel)
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.dynamic-param-form {
  .missing-fields-tip {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-md;
    background: $wolf-warning-bg;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;
    color: $wolf-warning-text;

    .el-icon {
      color: $wolf-warning;
    }

    .missing-list {
      font-weight: $wolf-font-weight-medium;
    }
  }

  .param-form {
    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: $wolf-space-md;

      .full-width {
        grid-column: span 2;
      }
    }
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: $wolf-space-sm;
    margin-top: $wolf-space-lg;
  }
}
</style>