/**
 * Glue SSE 事件契约类型定义
 *
 * Task 5.1: 对齐后端 GlueSSEStreamer（Phase 3.1）事件契约
 * 用于前端 AI Assistant SSE 流处理
 */

export type GlueSSEEvent =
  | { event: 'start'; data: { session_id: string } }
  | { event: 'intent'; data: IntentData }
  | { event: 'entity'; data: EntityData }
  | { event: 'preview'; data: PreviewData }
  | { event: 'execute'; data: ExecuteData }
  | { event: 'result'; data: ResultData }
  | { event: 'complete'; data: CompleteData }
  | { event: 'error'; data: ErrorData };

/** 意图识别阶段数据 */
export interface IntentData {
  intent_type: string;
  confidence: number;
  slots: Record<string, unknown>;
  auto_executed?: boolean;
}

/** 实体消解阶段数据 */
export interface EntityData {
  entity_type: string;
  status: 'resolved' | 'ambiguous' | 'not_found';
  resolved_id?: number;
  candidates?: EntityCandidate[];
  recovery?: RecoveryHint;
}

/** 预览阶段数据 */
export interface PreviewData {
  intent_type: string;
  risk_level: RiskLevel;
  requires_confirmation: boolean;
  /** outcome 分态：win=success-green / lose=neutral-grey / generic=danger-red */
  outcome_type: 'win' | 'lose' | 'generic';
  preview_snapshot?: PreviewSnapshot;
}

/** 执行阶段数据 */
export interface ExecuteData {
  success: boolean;
  message: string;
  action_id?: string;
}

export interface ResultData {
  event: 'result';
  success: boolean;
  message: string;
  content: string;
  answer: string;
  rounds: number;
  is_partial: boolean;
}

export interface CompleteData {
  answer: string;
  rounds: number;
  is_partial: boolean;
}

export interface ErrorData {
  message: string;
  recovery?: RecoveryHint;
}

/** 实体候选（歧义选择） */
export interface EntityCandidate {
  id: number;
  name: string;
  hint: string;
  matched_by: string;
}

/** 预览快照 */
export interface PreviewSnapshot {
  changes: { field: string; old: unknown; new: unknown }[];
  message: string;
}

/** 风险等级 */
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';

/** 错误恢复提示 */
export interface RecoveryHint {
  suggestions: string[];
  retryable: boolean;
}