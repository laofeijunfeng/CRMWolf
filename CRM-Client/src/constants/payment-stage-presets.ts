// CRM-Client/src/constants/payment-stage-presets.ts

/**
 * 回款计划阶段名称预设
 * 根据业务场景提供常见阶段名称建议
 */
export interface StagePreset {
  label: string
  value: string
  suggestedPercentage?: number | undefined // 建议金额占比（0-100）
  description?: string
}

export const STAGE_PRESETS: StagePreset[] = [
  {
    label: '首付款',
    value: '首付款',
    suggestedPercentage: 30,
    description: '合同签署后的首款支付'
  },
  {
    label: '进度款',
    value: '进度款',
    suggestedPercentage: 40,
    description: '项目中期按进度支付'
  },
  {
    label: '尾款',
    value: '尾款',
    suggestedPercentage: 30,
    description: '项目完成后的尾款支付'
  },
  {
    label: '验收款',
    value: '验收款',
    suggestedPercentage: 10,
    description: '验收通过后支付'
  },
  {
    label: '全款',
    value: '全款',
    suggestedPercentage: 100,
    description: '一次性全额支付'
  },
  {
    label: '里程碑款',
    value: '里程碑款',
    suggestedPercentage: undefined,
    description: '按里程碑节点支付'
  },
  {
    label: '维护费',
    value: '维护费',
    suggestedPercentage: 20,
    description: '年度维护服务费'
  }
]

/**
 * 根据现有阶段推断下一个建议阶段
 * @param existingStages 已有阶段名称列表
 * @returns 建议的下一个阶段预设
 */
export function suggestNextStage(existingStages: string[]): StagePreset {
  if (existingStages.length === 0) {
    return STAGE_PRESETS[0] // 默认首付款
  }

  if (!existingStages.includes('首付款') && !existingStages.includes('全款')) {
    return STAGE_PRESETS[0]
  }

  if (existingStages.includes('首付款') && !existingStages.includes('尾款')) {
    return STAGE_PRESETS[2] // 已有首付款，建议尾款
  }

  if (existingStages.includes('全款')) {
    return STAGE_PRESETS[6] // 已有全款，建议维护费
  }

  // 默认返回进度款
  return STAGE_PRESETS[1]
}
