/**
 * 预览卡片字段配置
 *
 * 定义不同操作类型的字段映射和展示配置
 */

/** 字段类型 */
export type FieldType = 'text' | 'select' | 'date' | 'number' | 'entity'

/** 字段配置 */
export interface FieldConfig {
  /** 字段 key（对应 API 返回的字段名） */
  key: string
  /** 显示标签 */
  label: string
  /** 字段类型 */
  type: FieldType
  /** 占位符（用于空值显示） */
  placeholder?: string
  /** 选项映射（用于 select 类型） */
  options?: Record<string, string>
  /** 实体类型（用于 entity 类型，如 customer、opportunity） */
  entityType?: string
  /** 是否必填 */
  required?: boolean
}

/** 操作类型配置 */
export interface ActionConfig {
  /** 操作类型 */
  actionType: string
  /** 显示标题模板 */
  titleTemplate: string
  /** 风险等级 */
  riskLevel: 'low' | 'medium' | 'high'
  /** 字段配置列表 */
  fields: FieldConfig[]
}

/** 操作类型映射 */
export const ACTION_CONFIGS: Record<string, ActionConfig> = {
  // 创建客户
  create_customer: {
    actionType: 'create_customer',
    titleTemplate: '创建客户',
    riskLevel: 'low',
    fields: [
      { key: 'name', label: '客户名称', type: 'text', required: true },
      { key: 'phone', label: '联系电话', type: 'text' },
      { key: 'email', label: '邮箱', type: 'text' },
      { key: 'address', label: '地址', type: 'text' },
      { key: 'source', label: '客户来源', type: 'select', options: {
        website: '官网',
        referral: '推荐',
        event: '展会',
        cold_call: '电话开发',
        other: '其他'
      }}
    ]
  },

  // 创建跟进记录
  create_follow_up: {
    actionType: 'create_follow_up',
    titleTemplate: '创建跟进记录',
    riskLevel: 'low',
    fields: [
      { key: 'customer_name', label: '客户名称', type: 'entity', entityType: 'customer', required: true },
      { key: 'content', label: '跟进内容', type: 'text', required: true },
      { key: 'method', label: '跟进方式', type: 'select', options: {
        phone: '电话',
        email: '邮件',
        wechat: '微信',
        visit: '拜访',
        other: '其他'
      }},
      { key: 'next_follow_up_at', label: '下次跟进', type: 'date' }
    ]
  },

  // 商机赢单
  win_opportunity: {
    actionType: 'win_opportunity',
    titleTemplate: '商机赢单',
    riskLevel: 'medium',
    fields: [
      { key: 'opportunity_name', label: '商机名称', type: 'entity', entityType: 'opportunity', required: true },
      { key: 'amount', label: '成交金额', type: 'number', required: true },
      { key: 'contract_name', label: '合同名称', type: 'text' },
      { key: 'expected_close_date', label: '预计成交日期', type: 'date' }
    ]
  },

  // 更新客户状态
  update_customer_status: {
    actionType: 'update_customer_status',
    titleTemplate: '更新客户状态',
    riskLevel: 'medium',
    fields: [
      { key: 'customer_name', label: '客户名称', type: 'entity', entityType: 'customer', required: true },
      { key: 'status', label: '新状态', type: 'select', required: true, options: {
        active: '活跃',
        inactive: '不活跃',
        churned: '流失'
      }},
      { key: 'reason', label: '变更原因', type: 'text' }
    ]
  },

  // 删除操作（高风险）
  delete_customer: {
    actionType: 'delete_customer',
    titleTemplate: '删除客户',
    riskLevel: 'high',
    fields: [
      { key: 'customer_name', label: '客户名称', type: 'entity', entityType: 'customer', required: true },
      { key: 'reason', label: '删除原因', type: 'text', required: true }
    ]
  },

  // 查询操作
  query_customer: {
    actionType: 'query_customer',
    titleTemplate: '查询客户',
    riskLevel: 'low',
    fields: [
      { key: 'query', label: '查询条件', type: 'text' },
      { key: 'limit', label: '返回数量', type: 'number' }
    ]
  }
}

/** 获取操作配置 */
export function getActionConfig(actionType: string): ActionConfig | undefined {
  return ACTION_CONFIGS[actionType]
}

/** 格式化字段值 */
export function formatFieldValue(
  field: FieldConfig,
  value: unknown
): string {
  if (value === null || value === undefined || value === '') {
    return field.placeholder || '-'
  }

  // 选择类型：映射选项文本
  if (field.type === 'select' && field.options) {
    return field.options[String(value)] || String(value)
  }

  // 日期类型：格式化显示
  if (field.type === 'date') {
    const date = new Date(String(value))
    if (isNaN(date.getTime())) {
      return String(value)
    }
    return date.toLocaleDateString('zh-CN')
  }

  // 数字类型：格式化显示
  if (field.type === 'number') {
    const num = Number(value)
    if (isNaN(num)) {
      return String(value)
    }
    // 金额字段添加单位
    if (field.key.includes('amount') || field.key.includes('price')) {
      return `¥${num.toLocaleString('zh-CN')}`
    }
    return num.toLocaleString('zh-CN')
  }

  // 默认：字符串显示
  return String(value)
}