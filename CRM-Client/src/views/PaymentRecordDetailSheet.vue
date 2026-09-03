<script setup lang="ts">
import { computed } from 'vue'
import { Sheet } from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import PaymentRecordDetailContent from '@/components/panels/PaymentRecordDetailContent.vue'
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
}

const props = withDefaults(defineProps<Props>(), {
  record: null,
  stageName: '',
  approval: null
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  refresh: []
  edit: []
  resubmit: []
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
  <Sheet v-model:open="visibleModel">
    <DetailSheetContent>
      <PaymentRecordDetailContent
        :record-id="recordId"
        :visible="visible"
        :record="record ?? null"
        :stage-name="stageName ?? ''"
        :approval="approval ?? null"
        @update:visible="emit('update:visible', $event)"
        @refresh="emit('refresh')"
        @edit="emit('edit')"
        @resubmit="emit('resubmit')"
        @close="closeSheet"
      />
    </DetailSheetContent>
  </Sheet>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// The detail content owns the visual implementation; this wrapper only provides the Sheet boundary.
</style>
