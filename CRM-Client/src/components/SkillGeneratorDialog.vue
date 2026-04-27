<template>
  <el-dialog
    v-model="visible"
    title="AI 辅助生成 Skill"
    width="600px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- Step 1: 输入需求 -->
    <div v-if="step === 1" class="step-content">
      <p class="step-desc">请输入您的需求描述，AI 将自动判断是创建新 Skill 还是为现有 Skill 补充 Action。</p>
      <el-input
        v-model="requirement"
        type="textarea"
        :rows="4"
        placeholder="例如：线索跟进功能、发票管理支持列表查询"
        :disabled="analyzing"
      />
      <div class="step-actions">
        <el-button type="primary" @click="handleAnalyze" :loading="analyzing">
          分析需求
        </el-button>
      </div>
    </div>

    <!-- Step 2: 预览/编辑 Prompt -->
    <div v-if="step === 2" class="step-content">
      <div v-if="analyzeResult?.supported">
        <div v-if="analyzeResult?.operation_type === 'add_action'" class="add-action-tip">
          <el-alert type="info" :closable="false">
            <template #title>
              <span>检测到 Skill "{{ analyzeResult?.skill_display_name }}" 已存在</span>
            </template>
            <template #default>
              <p>现有 Actions: {{ analyzeResult?.existing_actions?.join(', ') || '无' }}</p>
              <p>将补充: {{ analyzeResult?.missing_actions?.join(', ') || '待分析' }}</p>
            </template>
          </el-alert>
        </div>
        <p class="step-desc">AI 已生成配置建议，您可以编辑后确认生成。</p>
        <el-input
          v-model="configPrompt"
          type="textarea"
          :rows="10"
          placeholder="配置 Prompt"
          :disabled="generating"
        />
        <div class="step-actions">
          <el-button @click="step = 1">返回修改</el-button>
          <el-button type="primary" @click="handleGenerate" :loading="generating">
            生成配置
          </el-button>
        </div>
      </div>
      <div v-else class="unsupported">
        <el-alert type="warning" :closable="false">
          <template #title>
            <span>{{ analyzeResult?.message }}</span>
          </template>
        </el-alert>
        <div class="step-actions">
          <el-button @click="step = 1">返回修改</el-button>
          <el-button @click="handleClose">关闭</el-button>
        </div>
      </div>
    </div>

    <!-- Step 3: 生成结果 -->
    <div v-if="step === 3" class="step-content">
      <div v-if="generateResult" class="result-info">
        <el-result icon="success" :title="resultTitle">
          <template #sub-title>
            <p v-if="isNewSkill">Skill: {{ generateResult.display_name }} ({{ generateResult.skill_name }})</p>
            <p v-else>为 Skill "{{ generateResult.display_name }}" 补充了 {{ generateResult.action_count }} 个 Action</p>
            <p v-if="generateResult.skip_count && generateResult.skip_count > 0">跳过 {{ generateResult.skip_count }} 个已存在的 Action</p>
          </template>
        </el-result>
        <div class="action-list">
          <p class="action-title">生成的 Actions：</p>
          <ul>
            <li v-for="action in generatedActions" :key="action.action_id">
              {{ action.action_name }} - {{ action.handler_type }}
            </li>
          </ul>
        </div>
      </div>
      <div v-if="errorMessage" class="error-info">
        <el-result icon="error" title="生成失败">
          <template #sub-title>
            <p>{{ errorMessage }}</p>
          </template>
        </el-result>
      </div>
      <div class="step-actions">
        <el-button type="primary" @click="handleClose">完成</el-button>
      </div>
    </div>

    <!-- 进度提示 -->
    <div v-if="progressMessage && step < 3" class="progress-bar">
      <el-progress :percentage="100" :indeterminate="true" />
      <p class="progress-text">{{ progressMessage }}</p>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { aiSkillsApi, type AnalyzeEvent, type GenerateEvent } from '@/api/aiSkills'

interface Props {
  modelValue: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'success', skillId: number): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const step = ref(1)
const requirement = ref('')
const configPrompt = ref('')
const analyzing = ref(false)
const generating = ref(false)
const progressMessage = ref('')
const analyzeResult = ref<AnalyzeEvent | null>(null)
const generateResult = ref<GenerateEvent | null>(null)
const errorMessage = ref('')
const generatedActions = ref<GenerateEvent[]>([])

// 计算属性
const isNewSkill = computed(() => generateResult.value?.operation_type === 'create_skill')
const resultTitle = computed(() => isNewSkill.value ? 'Skill 创建成功' : 'Action 补充成功')

const handleAnalyze = async () => {
  if (!requirement.value.trim()) {
    ElMessage.warning('请输入需求描述')
    return
  }

  analyzing.value = true
  progressMessage.value = '正在分析需求...'
  analyzeResult.value = null

  try {
    await aiSkillsApi.analyzeSkill(requirement.value, (event: AnalyzeEvent) => {
      if (event.event === 'progress') {
        progressMessage.value = event.message || '正在分析...'
      } else if (event.event === 'result') {
        analyzeResult.value = event
        if (event.supported && event.config_prompt) {
          configPrompt.value = event.config_prompt
          step.value = 2
        } else {
          step.value = 2
        }
      } else if (event.event === 'error') {
        errorMessage.value = event.message || '分析失败'
        step.value = 3
      }
    })
  } catch {
    errorMessage.value = '分析请求失败'
    step.value = 3
  } finally {
    analyzing.value = false
    progressMessage.value = ''
  }
}

const handleGenerate = async () => {
  if (!configPrompt.value.trim()) {
    ElMessage.warning('请输入配置 Prompt')
    return
  }

  generating.value = true
  progressMessage.value = '正在生成配置...'
  generateResult.value = null
  generatedActions.value = []
  errorMessage.value = ''

  try {
    await aiSkillsApi.generateSkill(configPrompt.value, (event: GenerateEvent) => {
      if (event.event === 'progress') {
        progressMessage.value = event.message || '正在生成...'
      } else if (event.event === 'skill') {
        progressMessage.value = `Skill ${event.display_name} 创建成功`
      } else if (event.event === 'action') {
        generatedActions.value.push(event)
        progressMessage.value = `Action ${event.action_name} 创建成功`
      } else if (event.event === 'skip') {
        progressMessage.value = event.message || '跳过已存在的 Action'
      } else if (event.event === 'complete') {
        generateResult.value = event
        step.value = 3
        emit('success', event.skill_id || 0)
      } else if (event.event === 'error') {
        errorMessage.value = event.message || '生成失败'
        step.value = 3
      }
    })
  } catch {
    errorMessage.value = '生成请求失败'
    step.value = 3
  } finally {
    generating.value = false
    progressMessage.value = ''
  }
}

const handleClose = () => {
  visible.value = false
  step.value = 1
  requirement.value = ''
  configPrompt.value = ''
  analyzeResult.value = null
  generateResult.value = null
  errorMessage.value = ''
  generatedActions.value = []
  progressMessage.value = ''
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.step-content {
  padding: $wolf-space-sm 0;
}

.step-desc {
  margin-bottom: $wolf-space-md;
  color: $wolf-text-secondary;
}

.step-actions {
  margin-top: $wolf-space-md;
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
}

.unsupported {
  .el-alert {
    margin-bottom: $wolf-space-md;
  }
}

.progress-bar {
  margin-top: $wolf-space-md;
  padding: $wolf-space-sm;

  .progress-text {
    margin-top: $wolf-space-xs;
    text-align: center;
    color: $wolf-text-tertiary;
  }
}

.result-info {
  .action-list {
    margin-top: $wolf-space-md;
    padding: $wolf-space-sm;
    background: $wolf-bg-hover;
    border-radius: $wolf-radius-sm;

    .action-title {
      font-weight: $wolf-font-weight-medium;
      margin-bottom: $wolf-space-xs;
    }

    ul {
      list-style: none;
      padding: 0;
      margin: 0;

      li {
        padding: $wolf-space-xs 0;
        color: $wolf-text-secondary;
      }
    }
  }
}

.error-info {
  margin-top: $wolf-space-md;
}
</style>