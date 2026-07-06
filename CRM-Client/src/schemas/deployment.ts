/**
 * Zod Schema - DeploymentInfo Types
 *
 * @description 部署信息类型 Schema，映射后端 schemas/deployment.py
 */

import { z } from 'zod'

// ===== 部署信息基础类型 =====
export const DeploymentInfoSchema = z.object({
  id: z.number().int().positive(),
  customer_id: z.number().int().positive(),
  team_id: z.number().int().positive(),
  deployment_name: z.string().min(1, '部署名称不能为空').max(100, '部署名称长度不能超过100字符'),
  server_address: z.string()
    .min(1, '服务器地址不能为空')
    .max(500, '服务器地址长度不能超过500字符')
    .refine(
      (val) => val.startsWith('http://') || val.startsWith('https://'),
      '服务器地址必须以 http:// 或 https:// 开头'
    ),
  authorized_users: z.number().int().positive('授权人数必须大于0'),
  is_default: z.boolean(),
  created_time: z.string().datetime(),
  last_modified_time: z.string().datetime()
})

export type DeploymentInfo = z.infer<typeof DeploymentInfoSchema>

// ===== 部署信息创建请求 =====
export const DeploymentInfoCreateSchema = DeploymentInfoSchema.omit({
  id: true,
  team_id: true,
  created_time: true,
  last_modified_time: true
})

export type DeploymentInfoCreate = z.infer<typeof DeploymentInfoCreateSchema>

// ===== 部署信息更新请求 =====
export const DeploymentInfoUpdateSchema = DeploymentInfoCreateSchema.partial()

export type DeploymentInfoUpdate = z.infer<typeof DeploymentInfoUpdateSchema>