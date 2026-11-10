<script setup lang="ts">
import { computed } from 'vue'
import DetailSheetSurface from '@/components/ui/detail-sheet/DetailSheetSurface.vue'
import PaymentRecordDetailContent from '@/components/panels/PaymentRecordDetailContent.vue'
import ApprovalSourceHeader from '@/components/ApprovalSourceHeader.vue'
import ApprovalSourceFooter from '@/components/ApprovalSourceFooter.vue'
import type { ApprovalSourceContext } from '@/types/approvalSource'
import type {
  ApprovalInfo,
  ApprovalInfoLite,
  PaymentRecordInfo
} from '@/api/payment'

type PaymentRecordDetailInfo = PaymentRecordInfo & {
  record_number?: string
  creator_id?: string
  payment_plan_id?: number
  contract_name?: string
  stage_name?: string
  updated_time?: string | null
}

type ApprovalInfoInput = ApprovalInfo | ApprovalInfoLite

interface Props {
  recordId: number | null
  visible: boolean
  record?: PaymentRecordDetailInfo | null
  stageName?: string
  approval?: ApprovalInfoInput | null
  elevated?: boolean
  embedded?: boolean
  /** 从审批详情下钻时的来源审批；设置后进入只读查看模式。 */
  sourceApproval?: ApprovalSourceContext | null
}

const props = withDefaults(defineProps<Props>(), {
  record: null,
  stageName: '',
  approval: null,
  embedded: false,
  sourceApproval: null
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  refresh: []
  edit: []
  resubmit: []
  back: []
}>()

const visibleModel = computed<boolean>({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value)
})

const closeSheet = (): void => {
  emit('update:visible', false)
}
</script>

<template>
  <DetailSheetSurface v-model:open="visibleModel" :embedded="embedded" v-bind="elevated ? { elevated: true } : {}">
      <ApprovalSourceHeader
        v-if="sourceApproval"
        :source="sourceApproval"
        subject-label="回款详情"
        @back="emit('back')"
      />
      <PaymentRecordDetailContent v-bind="elevated ? { elevated: true } : {}"
        :class="sourceApproval ? 'flex-1 min-h-0' : undefined"
        :record-id="recordId"
        :visible="visible"
        :record="record ?? null"
        :stage-name="stageName ?? ''"
        :approval="approval ?? null"
        :readonly="!!sourceApproval"
        @update:visible="emit('update:visible', $event)"
        @refresh="emit('refresh')"
        @edit="emit('edit')"
        @resubmit="emit('resubmit')"
        @close="closeSheet"
      />
      <ApprovalSourceFooter v-if="sourceApproval" @back="emit('back')" />
  </DetailSheetSurface>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// The detail content owns the visual implementation; this wrapper only provides the Sheet boundary.
</style>
