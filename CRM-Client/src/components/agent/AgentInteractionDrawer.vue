<script setup lang="ts">
import { computed, ref, watch } from "vue"
import type { AgentInteraction, AgentInteractionChoice } from "@/api/agent"
import { AppDrawer } from "@/components/ui/app-drawer"
import { Button } from "@/components/ui/button"
import { DatePicker } from "@/components/ui/date-picker"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"

const props = defineProps<{
  interaction: AgentInteraction | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  submit: [content: string, metadata?: Record<string, unknown>]
  cancel: []
  "height-change": [height: number]
}>()

const formValues = ref<Record<string, string>>({})
const textValue = ref("")

const open = computed(() => props.interaction !== null)
const title = computed(() => {
  const interactionTitle = props.interaction?.title?.trim()
  if (interactionTitle !== undefined && interactionTitle.length > 0) return interactionTitle
  const prompt = props.interaction?.prompt?.trim()
  return prompt !== undefined && prompt.length > 0 ? prompt : "请补充信息"
})
const canSubmitForm = computed(() => {
  if (props.disabled || props.interaction?.type !== "form") return false
  return (props.interaction.fields ?? []).every((field) => {
    if (field.required === false) return true
    return String(formValues.value[field.key] ?? "").trim().length > 0
  })
})
const canSubmitText = computed(() => !props.disabled && textValue.value.trim().length > 0)

watch(() => props.interaction, (interaction) => {
  formValues.value = {}
  textValue.value = ""
  for (const field of interaction?.fields ?? []) {
    formValues.value[field.key] = String(field.default_value ?? "")
  }
}, { immediate: true })

const fieldValue = (key: string): string => formValues.value[key] ?? ""

const setFieldValue = (key: string, value: unknown): void => {
  formValues.value[key] = String(value ?? "")
}

const parseLocalDate = (value: string): Date | null => {
  const parts = value.split("-").map(part => Number(part))
  const [year, month, day] = parts
  if (
    parts.length !== 3
    || year === undefined
    || month === undefined
    || day === undefined
    || !Number.isInteger(year)
    || !Number.isInteger(month)
    || !Number.isInteger(day)
  ) {
    return null
  }

  const date = new Date(year, month - 1, day)
  if (
    date.getFullYear() !== year
    || date.getMonth() !== month - 1
    || date.getDate() !== day
  ) {
    return null
  }

  return date
}

const formatLocalDate = (date: Date): string => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

const submitChoice = (choice: AgentInteractionChoice): void => {
  if (props.disabled) return
  emit("submit", choice.value, choice.metadata)
}

const submitForm = (): void => {
  const interaction = props.interaction
  if (!interaction || interaction.type !== "form" || !canSubmitForm.value) return
  const parts = (interaction.fields ?? [])
    .map((field) => {
      const value = String(formValues.value[field.key] ?? "").trim()
      if (value.length === 0) return ""
      const optionLabel = field.options?.find(option => option.value === value)?.label
      const displayValue = optionLabel !== undefined && optionLabel !== value
        ? `${optionLabel}（${field.key}=${value}）`
        : value
      return `${field.label}：${displayValue}`
    })
    .filter(Boolean)
  emit("submit", parts.join("，"))
}

const submitText = (): void => {
  if (!canSubmitText.value) return
  emit("submit", textValue.value.trim())
}

const handleOpenChange = (nextOpen: boolean): void => {
  if (!nextOpen && props.interaction !== null && !props.disabled) {
    emit("cancel")
  }
}
</script>

<template>
  <AppDrawer
    :open="open"
    :title="title"
    :portal="false"
    :modal="false"
    :show-overlay="false"
    content-class="agent-interaction-drawer"
    @update:open="handleOpenChange"
    @height-change="emit('height-change', $event)"
  >
    <div v-if="interaction?.type === 'choice'" class="agent-interaction-drawer__actions">
      <Button
        v-for="choice in interaction.choices ?? []"
        :key="choice.value"
        type="button"
        :disabled="disabled"
        @click="submitChoice(choice)"
      >
        {{ choice.label }}
      </Button>
    </div>

    <form v-else-if="interaction?.type === 'form'" class="agent-interaction-drawer__form" @submit.prevent="submitForm">
      <div class="agent-interaction-drawer__fields">
        <label v-for="field in interaction.fields ?? []" :key="field.key" class="agent-interaction-drawer__field">
          <span>{{ field.label }}</span>
          <Select
            v-if="field.type === 'select'"
            :model-value="fieldValue(field.key)"
            :disabled="disabled === true"
            @update:model-value="value => setFieldValue(field.key, value)"
          >
            <SelectTrigger>
              <SelectValue :placeholder="field.placeholder ?? `请选择${field.label}`" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="option in field.options ?? []" :key="option.value" :value="option.value">
                {{ option.label }}
              </SelectItem>
            </SelectContent>
          </Select>
          <DatePicker
            v-else-if="field.type === 'date'"
            :model-value="parseLocalDate(fieldValue(field.key))"
            :placeholder="field.placeholder ?? `请选择${field.label}`"
            :disabled="disabled === true"
            @update:model-value="date => setFieldValue(field.key, date === null ? '' : formatLocalDate(date))"
          />
          <Input
            v-else
            :model-value="fieldValue(field.key)"
            :type="field.type === 'number' ? 'number' : 'text'"
            :placeholder="field.placeholder ?? `请输入${field.label}`"
            :disabled="disabled"
            @update:model-value="value => setFieldValue(field.key, value)"
          />
        </label>
      </div>
      <div class="agent-interaction-drawer__actions">
        <Button type="submit" :disabled="!canSubmitForm">
          {{ interaction.submit_label ?? "提交" }}
        </Button>
      </div>
    </form>

    <form v-else class="agent-interaction-drawer__text" @submit.prevent="submitText">
      <Textarea
        v-model="textValue"
        class="agent-interaction-drawer__textarea"
        rows="3"
        :disabled="disabled"
        :placeholder="interaction?.placeholder ?? '补充一点信息，我接着处理...'"
        aria-label="输入补充信息"
        @keydown.enter.exact.prevent="submitText"
      />
      <div class="agent-interaction-drawer__actions">
        <Button type="submit" :disabled="!canSubmitText">
          {{ interaction?.submit_label ?? "提交" }}
        </Button>
      </div>
    </form>
  </AppDrawer>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.agent-interaction-drawer__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: $wolf-space-sm-v2;
}

.agent-interaction-drawer__form,
.agent-interaction-drawer__text {
  display: grid;
  gap: $wolf-space-md-v2;
}

.agent-interaction-drawer__fields {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: $wolf-space-md-v2;
  width: 100%;
}

.agent-interaction-drawer__field {
  display: grid;
  flex: 0 1 280px;
  gap: $wolf-space-xs-v2;
  width: 280px;
  min-width: 0;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.agent-interaction-drawer__textarea {
  min-height: 76px;
  max-height: 160px;
  resize: vertical;
}

:global(.agent-interaction-drawer) {
  bottom: 0;
  min-height: var(--agent-composer-height, 77px);
}

:global(.agent-interaction-drawer .app-drawer__content) {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: calc(var(--agent-composer-height, 77px) - 24px - 2px);
  padding-bottom: $wolf-space-md-v2;
}

:global(.agent-interaction-drawer .app-drawer__body) {
  display: grid;
  align-items: center;
}

@media (max-width: 767px) {
  .agent-interaction-drawer__field {
    flex-basis: 100%;
    width: 100%;
  }
}
</style>
