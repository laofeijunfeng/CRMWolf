/**
 * 资源快捷入口配置
 *
 * 定义各资源类型的 API、显示字段、快捷操作等配置
 */

export type ResourceType = 'lead' | 'customer' | 'opportunity' | 'contract'

export interface QuickAction {
  type: string
  label: string
  icon: string
  template: string
}

export interface ResourceConfig {
  type: ResourceType
  label: string
  menuIcon: string
  searchPlaceholder: string
  nameField: string
  idField: string
  statusFilter: number | number[] | null
  quickActions: QuickAction[]
  // API 参数映射
  apiParams: {
    owner_id: string
    status?: string
    keyword?: string
  }
}

export const resourceConfigs: Record<ResourceType, ResourceConfig> = {
  lead: {
    type: 'lead',
    label: '我的线索',
    menuIcon: 'User',
    searchPlaceholder: '搜索线索名称或联系人',
    nameField: 'lead_name',
    idField: 'id',
    // 只显示 NEW(0) 和 FOLLOWING(1) 状态的线索
    statusFilter: null, // API 会自动处理
    quickActions: [
      {
        type: 'follow_up',
        label: '跟进线索',
        icon: 'ChatDotRound',
        template: '帮我把【{name}（ID：{id}）】添加一条跟进记录，跟进方式【电话/微信/邮件/面谈】，跟进内容【请填写跟进内容】，下次跟进时间【请填写日期，格式：YYYY-MM-DD】，下一步动作【请填写下一步计划】'
      },
      {
        type: 'convert',
        label: '转化客户',
        icon: 'Switch',
        template: '帮我把【{name}（ID：{id}）】转化为客户，客户名称【请填写客户全称】'
      },
      {
        type: 'invalid',
        label: '标记无效',
        icon: 'Close',
        template: '帮我把【{name}（ID：{id}）】标记为无效线索'
      }
    ],
    apiParams: {
      owner_id: 'owner_id'
    }
  },

  customer: {
    type: 'customer',
    label: '我的客户',
    menuIcon: 'OfficeBuilding',
    searchPlaceholder: '搜索客户名称',
    nameField: 'account_name',
    idField: 'id',
    statusFilter: null,
    quickActions: [
      {
        type: 'follow_up',
        label: '跟进客户',
        icon: 'ChatDotRound',
        template: '帮我把【{name}（ID：{id}）】添加一条跟进记录，跟进方式【电话/微信/邮件/面谈】，跟进内容【请填写跟进内容】，下次跟进时间【请填写日期，格式：YYYY-MM-DD】，下一步动作【请填写下一步计划】'
      },
      {
        type: 'create_opportunity',
        label: '创建商机',
        icon: 'Briefcase',
        template: '帮我为【{name}（ID：{id}）】创建商机，商机名称【请填写商机名称】，预计金额【请填写金额，格式：数字】'
      },
      {
        type: 'add_contact',
        label: '添加联系人',
        icon: 'UserFilled',
        template: '帮我为【{name}（ID：{id}）】添加联系人，姓名【请填写姓名】，手机号【请填写手机号】'
      },
      {
        type: 'view_detail',
        label: '查看详情',
        icon: 'View',
        template: '帮我看下【{name}（ID：{id}）】的详细信息'
      }
    ],
    apiParams: {
      owner_id: 'owner_id'
    }
  },

  opportunity: {
    type: 'opportunity',
    label: '我的商机',
    menuIcon: 'Briefcase',
    searchPlaceholder: '搜索商机名称或客户名称',
    nameField: 'opportunity_name',
    idField: 'id',
    // 只显示跟进中的商机（status=0）
    statusFilter: 0,
    quickActions: [
      {
        type: 'advance',
        label: '推进阶段',
        icon: 'ArrowRight',
        template: '帮我把【{name}（ID：{id}）】推进到下一阶段'
      },
      {
        type: 'win',
        label: '标记赢单',
        icon: 'TrophyBase',
        template: '帮我把【{name}（ID：{id}）】标记为赢单，实际成交金额【请填写金额，格式：数字】，实际成交日期【请填写日期，格式：YYYY-MM-DD】'
      },
      {
        type: 'contract',
        label: '创建合同',
        icon: 'Document',
        template: '帮我给【{name}（ID：{id}）】创建合同，合同名称【请填写合同全称】，签约日期【请填写日期，格式：YYYY-MM-DD】，签约联系人【请填写联系人姓名】'
      }
    ],
    apiParams: {
      owner_id: 'owner_id',
      status: 'status'
    }
  },

  contract: {
    type: 'contract',
    label: '我的合同',
    menuIcon: 'Document',
    searchPlaceholder: '搜索合同名称或合同编号',
    nameField: 'contract_name',
    idField: 'id',
    statusFilter: null,
    quickActions: [
      {
        type: 'submit_review',
        label: '提交审批',
        icon: 'Upload',
        template: '帮我把【{name}（ID：{id}）】提交审批'
      },
      {
        type: 'update_status',
        label: '更新状态',
        icon: 'Refresh',
        template: '帮我把【{name}（ID：{id}）】的状态更新为【已签署/已生效】'
      },
      {
        type: 'view_detail',
        label: '查看详情',
        icon: 'View',
        template: '帮我看下【{name}（ID：{id}）】的详细信息'
      }
    ],
    apiParams: {
      owner_id: 'owner_id'
    }
  }
}

// 菜单项列表（按顺序）
export const menuItems: { type: ResourceType; label: string; icon: string }[] = [
  { type: 'lead', label: '我的线索', icon: 'User' },
  { type: 'customer', label: '我的客户', icon: 'OfficeBuilding' },
  { type: 'opportunity', label: '我的商机', icon: 'Briefcase' },
  { type: 'contract', label: '我的合同', icon: 'Document' }
]

// 生成指令模板的辅助函数
export function generateTemplate(
  config: ResourceConfig,
  actionType: string,
  resourceName: string,
  resourceId: number
): string {
  const action = config.quickActions.find(a => a.type === actionType)
  if (!action) return ''

  return action.template.replace('{name}', resourceName).replace('{id}', String(resourceId))
}