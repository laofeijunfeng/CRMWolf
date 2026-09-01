import type { Component } from 'vue'
import {
  Bell,
  Building2,
  Cpu,
  Megaphone,
  Plug,
  Settings2,
  ShoppingCart,
  ShieldCheck,
  UsersRound,
  Workflow,
} from 'lucide-vue-next'

export type SettingsScope = 'personal' | 'team'
export type SettingsGroup = 'account' | 'business' | 'integration'

export interface SettingsNavigationItem {
  id: string
  label: string
  description: string
  path: string
  icon: Component
  group: SettingsGroup
  scope: SettingsScope
  requiredAnyPermissions: readonly string[]
  legacyComponentKey?: string
  requiresTeam?: boolean
}

export const SETTINGS_GROUP_LABELS: Record<SettingsGroup, string> = {
  account: '账户与成员',
  business: '流程与业务配置',
  integration: '智能与集成',
}

/**
 * 设置域唯一导航注册表。
 * 这里只描述路由、展示和访问契约，不放业务请求或页面状态。
 */
export const SETTINGS_NAVIGATION: readonly SettingsNavigationItem[] = [
  {
    id: 'account',
    label: '账户设置',
    description: '管理个人资料、密码和个人账号绑定。',
    path: '/settings/account',
    icon: Settings2,
    group: 'account',
    scope: 'personal',
    requiredAnyPermissions: [],
  },
  {
    id: 'team',
    label: '团队信息与安全',
    description: '维护当前团队基本信息、邀请设置和所有权关系。',
    path: '/settings/team',
    icon: Building2,
    group: 'account',
    scope: 'team',
    requiredAnyPermissions: ['team:settings:view', 'team:manage', 'role:manage'],
    requiresTeam: true,
  },
  {
    id: 'members',
    label: '团队成员',
    description: '管理成员、邀请和角色分配。',
    path: '/settings/members',
    icon: UsersRound,
    group: 'account',
    scope: 'team',
    requiredAnyPermissions: ['team:member:view', 'role:manage'],
    legacyComponentKey: 'members',
    requiresTeam: true,
  },
  {
    id: 'roles',
    label: '角色管理',
    description: '配置角色、权限集合和角色成员。',
    path: '/settings/roles',
    icon: ShieldCheck,
    group: 'account',
    scope: 'team',
    requiredAnyPermissions: ['role:view', 'role:manage'],
    legacyComponentKey: 'roles',
    requiresTeam: true,
  },
  {
    id: 'approval-flows',
    label: '审批流程管理',
    description: '配置审批流程、节点和启停状态。',
    path: '/settings/approval-flows',
    icon: Workflow,
    group: 'business',
    scope: 'team',
    requiredAnyPermissions: ['approval:flow:view', 'approval:flow:create', 'approval:flow:edit'],
    legacyComponentKey: 'approval-flows',
    requiresTeam: true,
  },
  {
    id: 'acquisition-sources',
    label: '获客来源',
    description: '维护线索与客户共用的获客来源。',
    path: '/settings/acquisition-sources',
    icon: Megaphone,
    group: 'business',
    scope: 'team',
    requiredAnyPermissions: ['acquisition_source:view'],
    legacyComponentKey: 'acquisition-sources',
    requiresTeam: true,
  },
  {
    id: 'procurement',
    label: '采购方式管理',
    description: '维护采购方式和阶段模板。',
    path: '/settings/procurement-methods',
    icon: ShoppingCart,
    group: 'business',
    scope: 'team',
    requiredAnyPermissions: ['procurement_method:view'],
    legacyComponentKey: 'procurement',
    requiresTeam: true,
  },
  {
    id: 'ai',
    label: 'AI 配置',
    description: '配置当前团队使用的大模型服务接口。',
    path: '/settings/ai',
    icon: Cpu,
    group: 'integration',
    scope: 'team',
    requiredAnyPermissions: ['ai:read', 'ai:manage', 'system:config'],
    legacyComponentKey: 'ai',
    requiresTeam: true,
  },
  {
    id: 'notifications',
    label: '通知配置',
    description: '配置审批流程相关的团队通知。',
    path: '/settings/notifications',
    icon: Bell,
    group: 'integration',
    scope: 'team',
    requiredAnyPermissions: ['notification:read', 'notification:manage'],
    legacyComponentKey: 'notifications',
    requiresTeam: true,
  },
  {
    id: 'integrations',
    label: '第三方集成',
    description: '配置当前团队的飞书应用和其他集成能力。',
    path: '/settings/integrations',
    icon: Plug,
    group: 'integration',
    scope: 'team',
    requiredAnyPermissions: ['integration:read', 'integration:manage', 'system:config'],
    legacyComponentKey: 'integrations',
    requiresTeam: true,
  },
]

export const getSettingsNavigationItem = (id: string): SettingsNavigationItem | undefined => {
  return SETTINGS_NAVIGATION.find(item => item.id === id)
}

export const getVisibleSettingsNavigation = (
  canAccess: (item: SettingsNavigationItem) => boolean,
): SettingsNavigationItem[] => SETTINGS_NAVIGATION.filter(canAccess)
