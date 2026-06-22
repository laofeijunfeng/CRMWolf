<template>
  <!-- ========== Phase 3: InputBox 组件（IDLE 状态显示） ========== -->
  <div
    v-if="sidebarUIConfig.showInputBox"
    class="main-input-container"
  >
    <InputBox
      ref="inputBoxRef"
      :entity-name="entityName"
      :entity-type-text="getEntityTypeText(entityType)"
      :placeholder="dynamicPlaceholder"
      :is-loading="isLoading"
      :quick-commands="quickCommands"
      :hints="inputHints"
      @submit="handleInputBoxSubmit"
      @focus="handleInputFocus"
      @blur="handleInputBlur"
    />
  </div>

  <!-- ========== Sidebar (Drawer) - 非 IDLE 状态显示 ========== -->
  <el-drawer
    v-model="visible"
    v-if="sidebarUIConfig.showSidebar"
    direction="rtl"
    size="420px"
    :modal="false"
    :with-header="true"
    @close="handleClose"
  >
    <template #header>
      <div class="sidebar-header">
        <el-icon class="header-icon"><Cpu /></el-icon>
        <span class="sidebar-title">AI Assistant</span>
      </div>
    </template>

    <!-- Sidebar Content -->
    <div class="sidebar-content">
      <!-- 实体信息 -->
      <div class="sidebar-entity-info">
        <span class="entity-name">{{ entityName }}</span>
        <el-tag size="small" type="info">{{ getEntityTypeText(entityType) }}</el-tag>
      </div>

      <!-- 智能输入栏（按需求文档：应该在最上面） -->
      <div class="sidebar-input-section">
        <!-- 快捷指令提示 -->
        <div class="quick-commands" v-if="showQuickCommands">
          <el-button
            v-for="cmd in quickCommands"
            :key="cmd.command"
            size="small"
            text
            @click="insertCommand(cmd.command)"
          >
            <span class="cmd-text">{{ cmd.command }}</span>
            <span class="cmd-desc">{{ cmd.description }}</span>
          </el-button>
        </div>

        <el-input
          v-model="userInput"
          type="textarea"
          :rows="2"
          :placeholder="dynamicPlaceholder"
          :disabled="isLoading"
          @input="handleInputChange"
          @keydown="handleKeyDown"
        />

        <div class="input-actions-inline">
          <el-button type="primary" size="small" :loading="isLoading" @click="handleSend">
            <el-icon><Promotion /></el-icon>
            发送
          </el-button>
        </div>

        <!-- Inline Pill 确认区（按需求文档：在输入框下方） -->
        <div class="sidebar-pill-section" v-if="stage === 'sidebar-pill' && !workflowMiniMapData">
          <InlinePill
            :action-type="inlinePillData.actionType"
            :action-display-name="inlinePillData.actionDisplayName"
            :params="inlinePillData.params"
            :risk-level="inlinePillData.riskLevel"
            :summary-text="inlinePillData.summaryText"
            :detailed-params="inlinePillData.detailedParams"
            :recommendation="inlinePillData.recommendation"
            :undo-ttl="inlinePillData.undoTtl"
            @confirm="handleInlinePillConfirm"
            @cancel="handleInlinePillCancel"
            @select-alternative="handleSelectAlternative"
          />
        </div>
      </div>

      <!-- 执行摘要区：分组状态卡片（按需求文档：在输入框下面） -->
      <div class="sidebar-summary-section" v-if="statusCards.length > 0">
        <StatusCard
          v-for="(card, idx) in statusCards"
          :key="idx"
          :type="card.type"
          :title="card.title"
          :summary="card.summary"
          :timestamp="card.timestamp"
          :missing-fields="card.missingFields"
          :original-error="card.originalError"
          :show-detail="card.type === 'warning' || card.type === 'error'"
          :show-actions="card.type === 'success' || card.type === 'warning' || card.type === 'error'"
          @undo="handleUndoCard(idx)"
          @retry="handleRetryCard(card)"
          @ignore="handleIgnoreCard(idx)"
        />
      </div>

      <!-- 加载中状态 -->
      <div class="sidebar-loading-card" v-if="stage === 'sidebar-loading' && statusCards.length === 0">
        <StatusCard
          type="loading"
          title="正在处理"
          :summary="loadingMessage || '正在执行...'"
          :show-actions="false"
        />
      </div>

      <!-- AI 回复展示区 -->
      <div class="sidebar-reply-section" v-if="replyText && !workflowMissingFieldsForm">
        <div class="reply-bubble">
          <el-icon class="reply-icon"><Cpu /></el-icon>
          <div class="reply-text" v-html="renderMarkdown(replyText)"></div>
        </div>
      </div>

      <!-- 等待用户回复区（options 有值时显示按钮） -->
      <div class="sidebar-options-section" v-if="stage === 'sidebar-waiting' && workflowOptions.length > 0 && !workflowMissingFieldsForm">
        <div class="options-buttons">
          <el-button
            v-for="option in workflowOptions"
            :key="option"
            type="primary"
            size="small"
            plain
            @click="handleWorkflowChoice(option)"
          >
            {{ option }}
          </el-button>
        </div>
      </div>

      <!-- 缺失字段表单填充区（missing_fields 有值时显示表单） -->
      <div class="sidebar-missing-fields-section" v-if="workflowMissingFieldsForm">
        <!-- 显示 AI 的回复（Markdown 渲染） -->
        <div class="missing-fields-context" v-if="replyText">
          <div class="context-bubble">
            <el-icon class="context-icon"><Cpu /></el-icon>
            <div class="context-text" v-html="renderMarkdown(replyText)"></div>
          </div>
        </div>

        <div class="missing-fields-header">
          <el-icon><WarningFilled /></el-icon>
          <span>请补充以下信息</span>
        </div>
        <el-form
          ref="missingFieldsFormRef"
          :model="missingFieldsFormValues"
          label-position="top"
          class="missing-fields-form"
          :class="{ 'inline-form': workflowMissingFields.length <= 2 }"
        >
          <el-form-item
            v-for="field in workflowMissingFields"
            :key="field"
            :label="getFriendlyFieldLabel(field)"
            :prop="field"
            :rules="[{ required: true, message: `请填写${getFriendlyFieldLabel(field)}` }]"
          >
            <!-- 下拉选择字段 -->
            <el-select
              v-if="isSelectField(field)"
              v-model="missingFieldsFormValues[field]"
              :placeholder="getFriendlyFieldPlaceholder(field)"
              style="width: 100%"
            >
              <el-option
                v-for="option in getFieldOptions(field)"
                :key="option"
                :label="option"
                :value="option"
              />
            </el-select>
            <!-- 日期字段使用日期选择器 -->
            <el-date-picker
              v-else-if="isDateField(field)"
              v-model="missingFieldsFormValues[field]"
              type="date"
              :placeholder="getFriendlyFieldPlaceholder(field)"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
            <!-- 金额字段使用数字输入 -->
            <el-input-number
              v-else-if="isAmountField(field)"
              v-model="missingFieldsFormValues[field]"
              :placeholder="getFriendlyFieldPlaceholder(field)"
              :min="0"
              :precision="2"
              style="width: 100%"
            />
            <!-- 其他字段使用普通输入 -->
            <el-input
              v-else
              v-model="missingFieldsFormValues[field]"
              :placeholder="getFriendlyFieldPlaceholder(field)"
            />
          </el-form-item>
        </el-form>
        <div class="missing-fields-actions">
          <el-button type="primary" @click="handleMissingFieldsSubmit">
            提交并继续
          </el-button>
          <el-button @click="handleMissingFieldsCancel">
            取消
          </el-button>
        </div>
      </div>

      <!-- Workflow Mini-map 区（Inline Pill 嵌入在当前步骤中） -->
      <div class="sidebar-minimap-section" v-if="workflowMiniMapData">
        <WorkflowMiniMap
          :steps="workflowMiniMapDataWithInlinePill"
          :current-step="workflowMiniMapData.currentStep"
          @confirm="handleInlinePillConfirm"
          @cancel="handleInlinePillCancel"
          @select-alternative="handleSelectAlternative"
          @undo-last="handleUndoLastStep"
          @pause="handlePauseWorkflow"
        />
      </div>

      <!-- 结果状态 -->
      <div class="sidebar-result" v-if="stage === 'sidebar-result'">
        <div class="result-summary">
          <div class="result-header">
            <el-icon class="result-icon" :class="success ? 'success' : 'error'">
              <CircleCheckFilled v-if="success" />
              <CircleCloseFilled v-else />
            </el-icon>
            <span class="result-title">{{ success ? '操作已完成' : '操作失败' }}</span>
          </div>
          <div class="result-content" v-html="renderMarkdown(replyText)"></div>
          <div class="result-actions">
            <el-button type="primary" size="small" @click="resetDialog">
              <el-icon><Plus /></el-icon>
              继续操作
            </el-button>
          </div>
        </div>
      </div>

      <!-- 执行过程日志 -->
      <div class="sidebar-execution-log" v-if="executionLogSteps.length > 0">
        <AgentExecutionLog
          :steps="executionLogSteps"
          :expanded="logExpanded"
          @toggle-expand="toggleLogExpand"
        />
      </div>

      <!-- ========== Phase 2: ActionButtons 组件集成 ========== -->
      <ActionButtons
        v-if="sidebarUIConfig.showStopButton || sidebarUIConfig.showNewChatButton"
        :show-stop="sidebarUIConfig.showStopButton"
        :show-new-chat="sidebarUIConfig.showNewChatButton"
        :show-undo="undoToastData.visible"
        :undo-endpoint="undoToastData.undoEndpoint"
        :operation-id="undoToastData.operationId"
        @stop="handleStopOperation"
        @new-chat="handleNewChat"
        @undo-success="handleUndoSuccess"
        @undo-failed="handleUndoFailed"
      />
    </div>
  </el-drawer>

  <!-- Undo Snackbar -->
  <UndoToast
    v-if="undoToastData.visible"
    :operation-id="undoToastData.operationId"
    :undo-endpoint="undoToastData.undoEndpoint"
    :ttl="undoToastData.ttl"
    :message="undoToastData.message"
    @undo-success="handleUndoSuccess"
    @undo-failed="handleUndoFailed"
    @expired="hideUndoToast"
  />

  <!-- 原有 Modal 内容（兼容降级） -->
  <el-dialog
    v-model="legacyVisible"
    :title="dialogTitle"
    width="500px"
    :close-on-click-modal="false"
    @close="handleClose"
    v-if="useLegacyMode"
  >
    <div v-if="stage === 'clarify'" class="stage-clarify">
      <div class="ai-reply">
        <div class="reply-icon">🤖</div>
        <div class="reply-content">{{ replyText }}</div>
      </div>

      <el-input
        v-model="userInput"
        type="textarea"
        :rows="2"
        placeholder="补充信息..."
        :disabled="isLoading"
      />

      <div class="input-actions">
        <el-button @click="stage = 'input'">返回</el-button>
        <el-button type="primary" :loading="isLoading" @click="handleSend">继续</el-button>
      </div>
    </div>

    <!-- Stage 3: Preview -->
    <div v-if="stage === 'preview'" class="stage-preview">
      <div class="ai-reply">
        <div class="reply-icon">🤖</div>
        <div class="reply-content">{{ replyText }}</div>
      </div>

      <div class="action-preview">
        <div class="preview-header">即将执行的操作：</div>
        <div class="preview-item">
          <span class="preview-label">工具:</span>
          <span class="preview-value">{{ previewAction?.tool }}</span>
        </div>
        <div v-if="previewAction?.params" class="preview-params">
          <div class="preview-label">参数:</div>
          <pre class="params-json">{{ JSON.stringify(previewAction.params, null, 2) }}</pre>
        </div>
      </div>

      <div class="input-actions">
        <el-button @click="stage = 'input'">返回修改</el-button>
        <el-button type="primary" :loading="isExecuting" @click="handleExecute">确认执行</el-button>
      </div>
    </div>

    <!-- Stage 3.5: Preview with Form (missing params) -->
    <div v-if="stage === 'preview-form'" class="stage-preview-form">
      <!-- AI 思考过程展示（可折叠） -->
      <div v-if="contextSummary" class="context-summary-section">
        <div class="context-header" @click="showContextDetail = !showContextDetail">
          <el-icon><InfoFilled /></el-icon>
          <span>系统已汇总客户信息供 AI 分析</span>
          <el-icon :class="{ 'rotate': showContextDetail }"><ArrowDown /></el-icon>
        </div>

        <div v-if="showContextDetail" class="context-detail">
          <div class="detail-block">
            <div class="block-title">基本信息</div>
            <div class="block-content">
              <div v-for="(value, key) in contextSummary.basic_info" :key="key" class="info-item">
                <span class="info-label">{{ key }}:</span>
                <span class="info-value">{{ value }}</span>
              </div>
            </div>
          </div>

          <div v-if="contextSummary.related_entities?.length" class="detail-block">
            <div class="block-title">关联商机</div>
            <div class="block-content">
              <div v-for="entity in contextSummary.related_entities" :key="entity.id" class="entity-item">
                <span class="entity-name">{{ entity.name }}</span>
                <span class="entity-status">（{{ entity.status }}，{{ entity.amount }}元）</span>
              </div>
            </div>
          </div>

          <div v-if="contextSummary.recent_activities?.length" class="detail-block">
            <div class="block-title">最近跟进</div>
            <div class="block-content">
              <div v-for="activity in contextSummary.recent_activities" :key="activity.date" class="activity-item">
                <span class="activity-content">{{ activity.content }}</span>
                <span class="activity-method">（{{ activity.method }}）</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="ai-reply">
        <div class="reply-icon">🤖</div>
        <div class="reply-content">{{ replyText }}</div>
      </div>

      <div class="form-section">
        <DynamicParamForm
          :param-definitions="paramDefinitions"
          :initial-values="formInitialValues"
          :missing-params="missingParams.length > 0 ? missingParams : undefined"
          :loading="isExecuting"
          submit-text="确认执行"
          @submit="handleFormSubmit"
          @cancel="stage = 'input'"
        />
      </div>
    </div>

    <!-- Stage 3.5: Customer Follow-up Preview -->
    <div v-if="stage === 'preview-followup'" class="stage-preview-followup">
      <div v-if="thinkingContent" class="thinking-section">
        <div class="thinking-header">AI 思考过程</div>
        <div class="thinking-content">{{ thinkingContent }}</div>
      </div>

      <div class="followup-preview">
        <div class="preview-header">解析完成，即将创建跟进记录：</div>

        <div class="preview-item">
          <span class="preview-label">跟进内容：</span>
          <span class="preview-value">{{ customerFollowUpInfo?.content || '无' }}</span>
        </div>
        <div class="preview-item">
          <span class="preview-label">跟进方式：</span>
          <span class="preview-value">{{ customerFollowUpInfo?.method || '其他' }}</span>
        </div>
        <div v-if="customerFollowUpInfo?.next_action" class="preview-item">
          <span class="preview-label">下一步动作：</span>
          <span class="preview-value">{{ customerFollowUpInfo?.next_action }}</span>
        </div>
        <div v-if="customerFollowUpInfo?.next_follow_time" class="preview-item">
          <span class="preview-label">下次跟进时间：</span>
          <span class="preview-value">{{ customerFollowUpInfo?.next_follow_time }}</span>
        </div>
      </div>

      <div class="input-actions">
        <el-button @click="stage = 'input'">返回修改</el-button>
        <el-button type="primary" :loading="isExecuting" @click="handleExecute">确认创建</el-button>
      </div>
    </div>

    <!-- Stage 5: Multi Tool Preview (依次确认) -->
    <div v-if="stage === 'preview-multi'" class="stage-preview-multi">
      <!-- ReAct 进度展示 -->
      <ReactProgress
        v-if="reactMode"
        :current-round="reactRound"
        :max-rounds="maxRounds"
        :previous-results="previousResults"
        :is-loading="false"
      />

      <div class="ai-reply">
        <div class="reply-icon">🤖</div>
        <div class="reply-content">{{ replyText }}</div>
      </div>

      <!-- 工具进度 -->
      <div class="tool-progress">
        <span class="progress-label">{{ multiToolProgress }}</span>
        <el-progress
          :percentage="(currentToolIndex + 1) / toolCallQueue.length * 100"
          :show-text="false"
        />
      </div>

      <!-- 当前工具预览 -->
      <div class="action-preview">
        <div class="preview-header">
          {{ getToolDisplayName(currentToolCall?.tool || '') }}
        </div>
        <div v-if="currentToolCall?.params" class="preview-params">
          <div class="preview-label">参数:</div>
          <pre class="params-json">{{ JSON.stringify(currentToolCall.params, null, 2) }}</pre>
        </div>
      </div>

      <!-- 已执行结果 -->
      <div v-if="executedResults.length > 0" class="executed-results">
        <div class="results-header">已完成的操作：</div>
        <div
          v-for="result in executedResults"
          :key="result.tool"
          class="result-item"
        >
          <span class="result-tool">{{ getToolDisplayName(result.tool) }}</span>
          <el-tag :type="result.success ? 'success' : 'info'" size="small">
            {{ result.success ? '成功' : '跳过' }}
          </el-tag>
        </div>
      </div>

      <div class="input-actions">
        <el-button @click="handleCancelAllTools">取消后续</el-button>
        <el-button @click="handleSkipCurrentTool">跳过此操作</el-button>
        <el-button type="primary" :loading="isExecuting" @click="handleConfirmCurrentTool">
          确认执行
        </el-button>
      </div>
    </div>

    <!-- Stage 5.5: Multi Tool Form (表单填充) -->
    <div v-if="stage === 'preview-multi-form'" class="stage-preview-multi-form">
      <!-- ReAct 进度展示 -->
      <ReactProgress
        v-if="reactMode"
        :current-round="reactRound"
        :max-rounds="maxRounds"
        :previous-results="previousResults"
        :is-loading="false"
      />

      <div class="ai-reply">
        <div class="reply-icon">🤖</div>
        <div class="reply-content">{{ replyText }}</div>
      </div>

      <!-- 工具进度 -->
      <div class="tool-progress">
        <span class="progress-label">{{ multiToolProgress }}</span>
        <el-progress
          :percentage="(currentToolIndex + 1) / toolCallQueue.length * 100"
          :show-text="false"
        />
      </div>

      <div class="form-section">
        <DynamicParamForm
          :param-definitions="paramDefinitions"
          :initial-values="previewAction?.params"
          :missing-params="missingParams.length > 0 ? missingParams : undefined"
          :loading="isExecuting"
          submit-text="确认执行"
          @submit="handleMultiFormSubmit"
          @cancel="handleSkipCurrentTool"
        />
      </div>
    </div>

    <!-- Stage 6: React Progress (多轮进度展示) -->
    <div v-if="stage === 'react-progress'" class="stage-react-progress">
      <ReactProgress
        :current-round="reactRound"
        :max-rounds="maxRounds"
        :previous-results="previousResults"
        :current-round-results="executedResults"
        :is-loading="isLoading"
      />

      <div v-if="isLoading" class="loading-indicator">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>{{ replyText }}</span>
      </div>
    </div>

    <!-- Stage: Workflow Waiting (等待用户选择) -->
    <div v-if="stage === 'workflow-waiting'" class="stage-workflow-waiting">
      <div class="workflow-question">
        <el-icon><InfoFilled /></el-icon>
        <span>{{ workflowQuestion }}</span>
      </div>

      <div class="workflow-options">
        <el-button
          v-for="option in workflowOptions"
          :key="option"
          type="primary"
          plain
          @click="handleWorkflowChoice(option)"
        >
          {{ option }}
        </el-button>
      </div>
    </div>

    <!-- Stage 7: Result -->
    <div v-if="stage === 'result'" class="stage-result">
      <el-result
        :icon="success ? 'success' : 'error'"
        :title="success ? '操作成功' : '操作失败'"
        :sub-title="resultMessage"
      >
        <template #extra>
          <el-button type="primary" @click="handleClose">关闭</el-button>
          <el-button v-if="success" @click="resetDialog">继续操作</el-button>
        </template>
      </el-result>
    </div>

    <!-- Stage 8: Pending Confirmation (Phase F 显式确认) -->
    <div v-if="stage === 'pending-confirmation'" class="stage-pending-confirmation">
      <ConfirmationCard
        :title="getToolDisplayName(confirmationData.toolName)"
        :risk-level="confirmationData.riskLevel"
        :entity-info="confirmationData.display?.entity_info"
        :params="confirmationData.params"
        :allow-edit="confirmationData.allowEdit"
        :evidence-chain="confirmationData.display?.evidence_chain"
        :undo-ttl="confirmationData.undoConfig?.ttl"
        :is-loading="isLoading"
        @cancel="handleConfirmationCancel"
        @confirm="handleConfirmationConfirm"
      />
    </div>

    <!-- Stage 9: Loading (执行中) -->
    <div v-if="stage === 'loading'" class="stage-loading">
      <div class="loading-indicator">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在执行...</span>
      </div>
    </div>
  </el-dialog>

  <!-- Undo Toast (Phase F 撤销提示) -->
  <UndoToast
    v-if="undoToastData.visible"
    :operation-id="undoToastData.operationId"
    :undo-endpoint="undoToastData.undoEndpoint"
    :ttl="undoToastData.ttl"
    :message="undoToastData.message"
    @undo-success="handleUndoSuccess"
    @undo-failed="handleUndoFailed"
    @expired="hideUndoToast"
  />

  <!-- Entity Select Dialog (实体歧义选择) -->
  <EntitySelectDialog
    v-model:visible="disambiguationVisible"
    :entity-type="disambiguationEntityType"
    :candidates="disambiguationCandidates"
    :message="disambiguationMessage"
    @select="handleEntitySelect"
    @cancel="handleEntitySelectCancel"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Loading,
  InfoFilled,
  ArrowDown,
  CircleCheckFilled,
  Cpu,
  Promotion,
  Plus,
  RefreshLeft,
  WarningFilled,
  CircleCloseFilled,
  Clock
} from '@element-plus/icons-vue'
import {
  aiAssistantApi,
  type AIAssistantSSEEvent,
  type ToolCall,
  type EntityCandidate,
  type ExecutedResult,
  type ParamDefinition,
  type ContextSummary
} from '@/api/aiAssistant'
import { customerAiApi, type CustomerAIParseSSEEvent, type CustomerAIFollowUpInfo } from '@/api/customerAI'
import { continueWorkflowSSE } from '@/api/workflow'
import { useUserStore } from '@/stores/user'
import { useSidebarState } from '@/composables/useSidebarState'
import { SidebarState } from '@/types/sidebar'
import DynamicParamForm from '@/components/DynamicParamForm.vue'
import ReactProgress from '@/components/ReactProgress.vue'
import EntitySelectDialog from '@/components/EntitySelectDialog.vue'
import ConfirmationCard from '@/components/ConfirmationCard.vue'
import UndoToast from '@/components/UndoToast.vue'
import InlinePill from '@/components/InlinePill.vue'
import WorkflowMiniMap from '@/components/WorkflowMiniMap.vue'
import StatusCard from '@/components/StatusCard.vue'
import ActionButtons from '@/components/sidebar/ActionButtons.vue'
import InputBox from '@/components/sidebar/InputBox.vue'
import AgentExecutionLog from '@/components/AgentExecutionLog.vue'
import { useAgentExecutionLog } from '@/composables/useAgentExecutionLog'
import { transformToolResult } from '@/utils/errorTransformer'

// ========== Phase 1: 状态驱动 UI - 引入 SidebarState ==========
const sidebarStateManager = useSidebarState()

/**
 * Stage 到 SidebarState 的映射
 *
 * 将现有的微观 stage 状态映射到宏观 SidebarState
 */
function stageToSidebarState(stageValue: Stage): SidebarState {
  switch (stageValue) {
    case 'input':
    case 'sidebar-input':
      return SidebarState.IDLE
    case 'clarify':
    case 'sidebar-waiting':
      return SidebarState.COLLECTING
    case 'preview':
    case 'preview-form':
    case 'preview-followup':
    case 'sidebar-pill':
      return SidebarState.PREVIEW
    case 'disambiguation':
      return SidebarState.RESOLVING_AMBIGUITY
    case 'react-progress':
    case 'preview-multi':
    case 'preview-multi-form':
    case 'pending-confirmation':
    case 'loading':
    case 'sidebar-loading':
      return SidebarState.EXECUTING
    case 'result':
    case 'sidebar-result':
      return SidebarState.COMPLETED
    default:
      return SidebarState.IDLE
  }
}

// Stage 类型定义（支持多工具依次确认、ReAct 循环、实体歧义、显式确认、Sidebar）
type Stage =
  | 'input'
  | 'clarify'
  | 'preview'
  | 'preview-form'
  | 'preview-followup'
  | 'preview-multi'         // 多工具依次确认
  | 'preview-multi-form'    // 多工具表单填充
  | 'disambiguation'        // 实体歧义选择
  | 'react-progress'        // ReAct 多轮进度展示
  | 'workflow-waiting'      // Workflow 等待用户回复
  | 'pending-confirmation'  // Phase F: 显式确认阶段
  | 'loading'               // Phase F: 执行中阶段
  | 'result'
  | 'sidebar-input'         // Phase G: Sidebar 输入态
  | 'sidebar-pill'          // Phase G: Inline Pill 确认态
  | 'sidebar-loading'       // Phase G: Sidebar 执行中
  | 'sidebar-result'        // Phase G: Sidebar 结果态
  | 'sidebar-waiting'       // Phase G: Sidebar 等待用户回复（新增）

interface Props {
  modelValue: boolean
  entityType: 'lead' | 'customer' | 'opportunity' | 'contract'
  entityId: number
  entityName: string
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'refresh'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const userStore = useUserStore()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const dialogTitle = computed(() => `✨ AI 操作 - ${getEntityTypeText(props.entityType)}`)

const stage = ref<Stage>('input')

// ========== Phase 1: 状态驱动 UI 计算 ==========
// 计算 SidebarState（基于当前 stage）
const currentSidebarState = computed<SidebarState>(() => {
  return stageToSidebarState(stage.value)
})

// 获取当前状态的 UI 配置
const sidebarUIConfig = computed(() => {
  return sidebarStateManager.uiConfig.value
})

// 监听 stage 变化，同步 SidebarState
watch(stage, (newStage) => {
  const newState = stageToSidebarState(newStage)
  if (sidebarStateManager.state.value !== newState) {
    // 更新状态（不记录历史，避免重复记录）
    sidebarStateManager.transitionTo(newState, 'ai_execution_done')
  }
})

const userInput = ref('')
const isLoading = ref(false)
const isExecuting = ref(false)
const replyText = ref('')
const previewAction = ref<{ tool: string; params: Record<string, unknown> } | null>(null)
const success = ref(false)
const resultMessage = ref('')
const sessionId = ref('')
const lastParsedEvent = ref<AIAssistantSSEEvent | null>(null)

// Customer follow-up specific state
const customerFollowUpInfo = ref<CustomerAIFollowUpInfo | null>(null)
const thinkingContent = ref('')

// Dynamic form state
const paramDefinitions = ref<Record<string, ParamDefinition>>({})
const missingParams = ref<string[]>([])

// ========== 上下文汇总展示状态 ==========
const contextSummary = ref<ContextSummary | null>(null)
const enhancedContentPreview = ref('')
const showContextDetail = ref(false)  // 是否展开上下文详情

// ========== ReAct 循环相关状态 ==========
const reactMode = ref(false)                       // 是否 ReAct 模式
const reactRound = ref(1)                          // 当前轮数
const maxRounds = ref(5)                           // 最大轮数
const toolCallQueue = ref<ToolCall[]>([])          // 待确认工具队列
const currentToolIndex = ref(0)                    // 当前处理工具索引
const executedResults = ref<ExecutedResult[]>([])  // 本轮已执行结果
const previousResults = ref<ExecutedResult[]>([])  // 前几轮执行结果

// ========== 实体歧义相关状态 ==========
const disambiguationVisible = ref(false)           // 实体选择弹窗可见性
const disambiguationEntityType = ref<'opportunity' | 'contact' | 'contract'>('opportunity')
const disambiguationCandidates = ref<EntityCandidate[]>([])
const disambiguationMessage = ref('')
const pendingToolCall = ref<ToolCall | null>(null) // 待选择后执行的工具

// ========== Workflow 相关状态 ==========
const workflowSessionId = ref('')                  // Workflow session ID

// ========== Phase F: 显式确认状态变量 ==========

interface ConfirmationData {
  stepId: string
  toolName: string
  riskLevel: 'low' | 'medium' | 'high'
  params: Record<string, any>
  display: Record<string, any>
  undoConfig: Record<string, any>
  allowEdit: boolean
}

interface UndoToastData {
  operationId: number
  undoEndpoint: string
  ttl: number
  message: string
  visible: boolean
}

const confirmationData = ref<ConfirmationData>({
  stepId: '',
  toolName: '',
  riskLevel: 'medium',
  params: {},
  display: {},
  undoConfig: {},
  allowEdit: false
})

const undoToastData = ref<UndoToastData>({
  operationId: 0,
  undoEndpoint: '',
  ttl: 10,
  message: '',
  visible: false
})

// ========== Phase H: 状态卡片 + 智能输入栏 ==========

interface StatusCardData {
  type: 'success' | 'warning' | 'error' | 'loading'
  title: string
  summary: string
  timestamp?: string
  missingFields?: string[]
  originalError?: string
  toolName?: string
  undoEndpoint?: string
}

const statusCards = ref<StatusCardData[]>([])
const showQuickCommands = ref(false)

// 快捷指令列表
const quickCommands = [
  { command: '/赢单', description: '标记商机赢单' },
  { command: '/跟进', description: '跟进客户' },
  { command: '/查合同', description: '查询合同' },
  { command: '/创建商机', description: '创建新商机' }
]

// ========== Phase 3: InputBox 相关状态 ==========
const inputBoxRef = ref<InstanceType<typeof InputBox> | null>(null)

// 动态提示列表（根据实体类型）
const inputHints = computed(() => {
  if (props.entityType === 'customer') {
    return [
      { command: '跟进客户，微信沟通产品需求', description: '跟进记录' },
      { command: '创建商机，产品CRM系统，预计50万', description: '创建商机' },
      { command: '查询这个客户的合同信息', description: '查询合同' }
    ]
  } else if (props.entityType === 'opportunity') {
    return [
      { command: '标记商机赢单，成交金额50万', description: '商机赢单' },
      { command: '推进到下一阶段', description: '阶段推进' },
      { command: '创建合同，签约金额50万', description: '创建合同' }
    ]
  } else if (props.entityType === 'contract') {
    return [
      { command: '登记回款，金额10万', description: '登记回款' },
      { command: '申请开票', description: '申请开票' },
      { command: '提交审批', description: '提交审批' }
    ]
  }
  return [
    { command: '创建客户张三，电话13812345678', description: '创建客户' },
    { command: '跟进客户，微信沟通产品需求', description: '跟进记录' },
    { command: '标记商机赢单，成交金额50万', description: '商机赢单' }
  ]
})

// 动态 Placeholder
const dynamicPlaceholder = computed(() => {
  const entityText = getEntityTypeText(props.entityType)
  if (props.entityType === 'customer') {
    return `例如：微信跟进客户、标记赢单、创建商机...`
  } else if (props.entityType === 'opportunity') {
    return `例如：推进阶段、标记赢单、创建合同...`
  } else if (props.entityType === 'contract') {
    return `例如：修改金额、提交审批、登记回款...`
  }
  return `描述你想对这个${entityText}做的操作...`
})

// ========== Phase G: Sidebar 状态变量 ==========

interface InlinePillData {
  actionType: string
  actionDisplayName: string
  params: Record<string, any>
  riskLevel: 'low' | 'medium' | 'high'
  summaryText: string
  detailedParams: Record<string, any>
  recommendation?: any
  undoTtl: number
}

interface WorkflowMiniMapData {
  steps: any[]
  currentStep: number
}

const inlinePillData = ref<InlinePillData>({
  actionType: '',
  actionDisplayName: '',
  params: {},
  riskLevel: 'medium',
  summaryText: '',
  detailedParams: {},
  undoTtl: 10
})

const workflowMiniMapData = ref<WorkflowMiniMapData | null>(null)
const loadingMessage = ref('')
const useLegacyMode = ref(false)  // 是否使用旧的 Modal 模式（降级）
const legacyVisible = ref(false)  // 旧 Modal 的可见性
const workflowStepId = ref('')                     // 当前等待的步骤 ID
const workflowQuestion = ref('')                   // 等待用户的问题
const workflowOptions = ref<string[]>([])          // 用户选择的选项
const workflowTraceId = ref('')                    // Trace ID
const workflowMissingFields = ref<string[]>([])    // 缺失的字段列表
const workflowMissingFieldsForm = ref(false)       // 是否显示缺失字段表单
const missingFieldsFormValues = ref<Record<string, string>>({}) // 缺失字段表单值
const missingFieldsFormRef = ref()                 // 缺失字段表单 ref
const workflowFieldOptions = ref<Record<string, any>>({}) // 字段选项配置（下拉选项等）

// ========== Agent Execution Log ==========
const { steps: executionLogSteps, handleSSEEvent: handleExecutionLogEvent } = useAgentExecutionLog()
const logExpanded = ref(false)

const toggleLogExpand = () => {
  logExpanded.value = !logExpanded.value
}

// ========== 计算属性 ==========
const formInitialValues = computed(() => previewAction.value?.params)

// 将 Inline Pill 数据嵌入到 Workflow Mini-map 的当前步骤中
const workflowMiniMapDataWithInlinePill = computed(() => {
  if (!workflowMiniMapData.value) return null

  const steps = workflowMiniMapData.value.steps.map(step => {
    // 如果是当前运行步骤且 stage 是 sidebar-pill，嵌入 Inline Pill 数据
    if (step.status === 'running' && stage.value === 'sidebar-pill') {
      return {
        ...step,
        inlinePill: inlinePillData.value
      }
    }
    return step
  })

  return {
    ...workflowMiniMapData.value,
    steps
  }
})

// 当前工具（多工具依次确认时使用）
const currentToolCall = computed(() => {
  if (toolCallQueue.value.length === 0) return null
  return toolCallQueue.value[currentToolIndex.value]
})

// 是否还有后续工具
const hasMoreTools = computed(() => {
  return currentToolIndex.value < toolCallQueue.value.length - 1
})

// 多工具进度描述
const multiToolProgress = computed(() => {
  if (toolCallQueue.value.length === 0) return ''
  return `操作 ${currentToolIndex.value + 1}/${toolCallQueue.value.length}`
})

watch(visible, (val) => {
  if (val) {
    resetDialog()
    sessionId.value = `mw_${Date.now()}_${props.entityId}`
  }
})

function getEntityTypeText(type: string): string {
  const map: Record<string, string> = {
    lead: '线索',
    customer: '客户',
    opportunity: '商机',
    contract: '合同'
  }
  return map[type] || type
}

function buildContextMessage(content: string): string {
  // Build message with entity context
  const contextPrefix = `[当前操作对象：${getEntityTypeText(props.entityType)} "${props.entityName}"（ID: ${props.entityId}）]\n`
  return contextPrefix + content
}

async function handleSend() {
  console.log('[MagicWand] handleSend called, userInput:', userInput.value, 'stage:', stage.value)
  if (!userInput.value.trim()) {
    ElMessage.warning('请输入操作描述')
    return
  }

  // 如果是 sidebar-waiting 状态，发送用户回复继续 workflow
  if (stage.value === 'sidebar-waiting' && workflowSessionId.value) {
    await handleWorkflowChoice(userInput.value)
    return
  }

  isLoading.value = true
  replyText.value = ''
  thinkingContent.value = ''

  const token = userStore.token || localStorage.getItem('token') || ''
  console.log('[MagicWand] token:', token ? 'exists' : 'empty')

  // 构建 entity_context（JSON 格式）
  const entity_context = {
    entity_type: props.entityType,
    entity_id: props.entityId,
    entity_name: props.entityName
  }
  console.log('[MagicWand] entity_context:', entity_context)

  try {
    console.log('[MagicWand] Starting SSE request...')
    await aiAssistantApi.chatSSE(
      {
        content: userInput.value,
        entity_context: entity_context  // 传递 JSON 格式
      },
      (event: AIAssistantSSEEvent) => {
        console.log('[MagicWand] SSE event received:', event)
        handleSSEEvent(event)
      },
      token
    )
    console.log('[MagicWand] SSE request completed')
  } catch (error: unknown) {
    const err = error as Error
    console.error('[MagicWand] SSE error:', err)
    ElMessage.error(err.message || '请求失败')
    stage.value = 'input'
  } finally {
    isLoading.value = false
  }
}

// ========== Phase 3: InputBox 事件处理 ==========

/**
 * InputBox 提交事件
 */
async function handleInputBoxSubmit(value: string) {
  console.log('[MagicWand] handleInputBoxSubmit:', value)
  if (!value.trim()) {
    ElMessage.warning('请输入操作描述')
    return
  }

  // 更新 userInput（用于后续流程）
  userInput.value = value

  // 触发发送流程
  isLoading.value = true
  replyText.value = ''
  thinkingContent.value = ''

  const token = userStore.token || localStorage.getItem('token') || ''

  const entity_context = {
    entity_type: props.entityType,
    entity_id: props.entityId,
    entity_name: props.entityName
  }

  try {
    await aiAssistantApi.chatSSE(
      {
        content: value,
        entity_context: entity_context
      },
      (event: AIAssistantSSEEvent) => {
        handleSSEEvent(event)
      },
      token
    )
  } catch (error: unknown) {
    const err = error as Error
    console.error('[MagicWand] SSE error:', err)
    ElMessage.error(err.message || '请求失败')
    stage.value = 'input'
  } finally {
    isLoading.value = false
  }
}

/**
 * InputBox 聚焦事件
 */
function handleInputFocus() {
  console.log('[MagicWand] InputBox focused')
}

/**
 * InputBox 失焦事件
 */
function handleInputBlur() {
  console.log('[MagicWand] InputBox blurred')
}

// @ts-expect-error - 保留原有 customer follow-up 逻辑，后续可能启用
async function handleCustomerFollowUp(token: string) {
  try {
    await customerAiApi.parseSSE(
      {
        content: userInput.value,
        customer_id: props.entityId,
        customer_name: props.entityName
      },
      (event: CustomerAIParseSSEEvent) => {
        switch (event.event) {
          case 'status':
            replyText.value = event.message || ''
            break
          case 'content':
            thinkingContent.value += event.content || ''
            break
          case 'parsed':
            if (event.follow_up_info) {
              customerFollowUpInfo.value = event.follow_up_info
              stage.value = 'preview-followup'
            } else {
              success.value = false
              resultMessage.value = '未能解析出跟进信息'
              stage.value = 'result'
            }
            break
          case 'error':
            success.value = false
            resultMessage.value = event.message || '解析失败'
            stage.value = 'result'
            break
        }
      },
      token
    )
  } catch (error: unknown) {
    const err = error as Error
    ElMessage.error(err.message || '请求失败')
    stage.value = 'input'
  } finally {
    isLoading.value = false
  }
}

function handleSSEEvent(event: AIAssistantSSEEvent) {
  // 调用 Agent Execution Log 的事件处理
  handleExecutionLogEvent(event)

  switch (event.event) {
    case 'react_start':
      // ReAct 循环开始
      console.log('[MagicWand] react_start:', event)
      reactMode.value = true
      maxRounds.value = event.max_rounds || 10
      sessionId.value = event.session_id || ''
      reactRound.value = 1
      previousResults.value = []
      executedResults.value = []
      stage.value = 'sidebar-loading'
      break

    case 'round_start':
      // 新轮次开始
      console.log('[MagicWand] round_start:', event)
      reactRound.value = event.round || reactRound.value + 1
      // 将上一轮的结果移到 previousResults
      if (executedResults.value.length > 0) {
        previousResults.value = [...previousResults.value, ...executedResults.value]
        executedResults.value = []
      }
      break

    case 'react_complete':
      // ReAct 循环完成
      console.log('[MagicWand] react_complete:', event)
      // 等待后续的 result 事件来决定最终状态
      break

    case 'tool_call':
      // 工具调用
      console.log('[MagicWand] tool_call:', event)
      // 可用于实时显示当前正在执行的工具
      replyText.value = `正在执行: ${getToolDisplayName(event.tool || '')}`
      break

    case 'tool_result':
      // 工具执行结果 - 关键：填充进度显示数据 + 状态卡片
      console.log('[MagicWand] tool_result:', event)
      if (event.tool && event.result) {
        // 填充 executedResults（用于进度显示）
        executedResults.value.push({
          tool: event.tool,
          success: event.result.success !== false,
          message: event.result.message || (event.result.success ? '成功' : '失败')
        })

        // 填充 statusCards（用于分组状态卡片）
        const cardData = transformToolResult({
          tool: event.tool,
          success: event.result.success !== false,
          message: event.result.message
        })
        statusCards.value.push({
          type: cardData.type,
          title: cardData.title,
          summary: cardData.summary,
          timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          missingFields: cardData.missingFields,
          originalError: event.result.message?.includes('validation error') ? event.result.message : undefined,
          toolName: event.tool
        })
      }
      break

    case 'status':
      replyText.value = event.message || ''
      break

    case 'content':
      replyText.value += event.content || ''
      break

    case 'context_summary':
      // 上下文汇总展示（系统给 AI 的信息）
      console.log('[MagicWand] context_summary:', event)
      if (event.summary) {
        contextSummary.value = event.summary
        enhancedContentPreview.value = event.enhanced_content_preview || ''
      }
      break

    case 'parsed':
      lastParsedEvent.value = event
      if (event.tool) {
        // Has matched tool
        previewAction.value = {
          tool: event.tool,
          params: event.params || {}
        }
        replyText.value = event.reply_text || ''

        // 接收参数定义
        if (event.param_definitions && Object.keys(event.param_definitions).length > 0) {
          paramDefinitions.value = event.param_definitions
          missingParams.value = event.missing_params || []
          // 有参数定义时，始终进入表单填充阶段让用户确认/修改
          stage.value = 'preview-form'
        } else {
          // 无参数定义时，直接预览
          stage.value = 'preview'
        }
      } else if (event.reply_text) {
        // Need clarification
        replyText.value = event.reply_text
        stage.value = 'clarify'
      }
      break

    case 'parsed_multi':
      // 多工具依次确认（ReAct 模式）
      handleParsedMulti(event)
      break

    case 'disambiguation_required':
      // 实体歧义选择
      handleDisambiguation(event)
      break

    case 'awaiting_confirmation':
      // ReAct 等待确认（前端已处理 parsed_multi，此事件可忽略或作为同步标记）
      console.log('[MagicWand] awaiting_confirmation:', event)
      break

    case 'pending_confirmation':
      // 显式确认事件（Phase F 新增）
      handlePendingConfirmation(event)
      break

    case 'undo_available':
      // 撤销可用事件（Phase F 新增）
      handleUndoAvailable(event)
      break

    case 'undo_expired':
      // 撤销窗口过期
      hideUndoToast()
      break

    case 'round_completed':
      // 单轮执行完成，准备进入下一轮
      handleRoundCompleted(event)
      break

    case 'max_rounds_reached':
      // 达到最大轮数
      success.value = true
      resultMessage.value = event.message || `已完成 ${reactRound.value} 轮处理（达到最大轮数限制）`
      stage.value = 'result'
      emit('refresh')
      break

    case 'result':
      // 先停止 loading 状态
      isLoading.value = false
      loadingMessage.value = ''

      // 检查消息是否包含成功信息 + 下一步问题
      const resultMsg = event.message || ''
      const hasSuccessInfo = resultMsg.includes('已完成') || resultMsg.includes('成功') || resultMsg.includes('创建成功')
      const hasQuestion = resultMsg.includes('请问') ||
                          resultMsg.includes('是否') ||
                          resultMsg.includes('需要') ||
                          resultMsg.includes('?') ||
                          resultMsg.includes('？')

      // 尝试从消息中提取缺失字段（支持多种格式）
      const extractedMissingFields: string[] = []

      // 格式1: - **字段名** 或 * **字段名**
      const pattern1 = /[-*]\s*\*\*([^*]+)\*\*/g
      let match1
      while ((match1 = pattern1.exec(resultMsg)) !== null) {
        extractedMissingFields.push(match1[1].replace(/：$/, '').trim())
      }

      // 格式2: 字段名：xxx？ （如 "预计金额：xxx？"）
      if (extractedMissingFields.length === 0) {
        const pattern2 = /([^\n：]+)：[^？]*[？?]/g
        let match2
        while ((match2 = pattern2.exec(resultMsg)) !== null) {
          const field = match2[1].trim()
          // 排除一些非字段名的文本
          if (field.length < 20 && !field.includes('请问') && !field.includes('如果')) {
            extractedMissingFields.push(field)
          }
        }
      }

      // 注意：不再硬编码采购方式选项！
      // 后端会从数据库查询并通过 field_options 传递
      // 这里只提供字段类型提示（不包含具体选项）

      if (hasSuccessInfo && hasQuestion) {
        // 成功完成 + 有下一步问题：显示完整结果，允许用户继续操作
        console.log('[MagicWand] result with success + question')
        success.value = true
        replyText.value = resultMsg  // 显示完整内容（包含表格等）
        stage.value = 'sidebar-result'
        emit('refresh')
      } else if (hasQuestion && extractedMissingFields.length > 0) {
        // 有提问需要用户补充信息，显示表单
        console.log('[MagicWand] result with question + missing fields, showing form')
        replyText.value = resultMsg
        workflowMissingFields.value = extractedMissingFields
        workflowMissingFieldsForm.value = true
        extractedMissingFields.forEach(field => {
          const fieldConfig = workflowFieldOptions.value[field]
          if (fieldConfig?.type === 'select' && fieldConfig.options?.length > 0) {
            // 下拉选择：默认选中第一个或指定的默认值
            missingFieldsFormValues.value[field] = fieldConfig.default || fieldConfig.options[0]
          } else {
            // 其他字段：空值
            missingFieldsFormValues.value[field] = ''
          }
        })
        stage.value = 'sidebar-waiting'
      } else if (hasQuestion) {
        // 有提问需要用户回复，保持在对话状态
        console.log('[MagicWand] result with question, staying in input state')
        replyText.value = resultMsg
        workflowMissingFields.value = []
        workflowMissingFieldsForm.value = false
        stage.value = 'sidebar-waiting'
      } else if (event.message) {
        // 真正的流程结束
        success.value = true
        replyText.value = event.message
        stage.value = 'result'
        emit('refresh')
      } else if (event.success === false) {
        success.value = false
        replyText.value = event.message || event.reply_text || '操作失败'
        stage.value = 'result'
      } else {
        // 有 message 或 data 就视为成功
        success.value = true
        replyText.value = event.message || '操作已完成'
        stage.value = 'result'
        emit('refresh')
      }
      break

    case 'error':
      success.value = false
      resultMessage.value = event.message || '发生错误'
      stage.value = 'result'
      break

    // ========== Workflow 事件处理 ==========

    case 'workflow_start':
      console.log('[MagicWand] workflow_start:', event)
      // Workflow 开始，更新状态显示
      if (event.data) {
        replyText.value = `启动流程: ${event.data.workflow_name || ''}`
      }
      break

    case 'step_start':
      console.log('[MagicWand] step_start:', event)
      // 步骤开始，更新状态显示
      if (event.data) {
        replyText.value = `正在执行: ${event.data.description || event.data.step_id}`
      }
      break

    case 'step_result':
      console.log('[MagicWand] step_result:', event)
      // 步骤结果
      if (event.data) {
        if (event.data.success) {
          replyText.value = event.data.message || '步骤执行成功'
        } else {
          replyText.value = `错误: ${event.data.error || '步骤执行失败'}`
        }
      }
      break

    case 'decision_made':
      console.log('[MagicWand] decision_made:', event)
      // 决策结果
      break

    case 'waiting_for_user':
      // 关键：Workflow 等待用户回复
      console.log('[MagicWand] waiting_for_user:', event)
      handleWorkflowWaiting(event)
      break

    case 'workflow_complete':
      console.log('[MagicWand] workflow_complete:', event)
      // Workflow 完成
      success.value = true
      resultMessage.value = event.data?.message || '流程执行完成'
      stage.value = 'result'
      emit('refresh')
      break

    case 'workflow_error':
      console.log('[MagicWand] workflow_error:', event)
      // Workflow 错误
      success.value = false
      resultMessage.value = event.data?.message || '流程执行失败'
      stage.value = 'result'
      break

    // ========== 异常处理事件 ==========

    case 'exception_handled':
      console.log('[MagicWand] exception_handled:', event)
      // 异常被 Guardrails 拦截处理
      if (event.data) {
        const exceptionType = event.data.exception_type
        const strategy = event.data.strategy
        const error = event.data.error

        // 根据异常类型和策略决定处理方式
        if (strategy === 'human_loop') {
          // 需要人工介入，等待 guardrail_human_loop 事件
          replyText.value = `操作遇到异常：${error}`
        } else if (strategy === 'block') {
          // 阻断操作
          success.value = false
          resultMessage.value = `操作被拦截：${error}`
          stage.value = 'result'
        }
      }
      break

    case 'guardrail_human_loop':
      console.log('[MagicWand] guardrail_human_loop:', event)
      // Guardrails 触发人工介入流程
      if (event.data) {
        const reason = event.data.reason || '未知错误'
        const stepId = event.data.step_id || ''

        // 显示异常处理界面，让用户选择：重试/跳过/取消
        workflowSessionId.value = event.session_id || workflowSessionId.value
        workflowQuestion.value = `操作遇到异常需要人工处理：\n${reason}`
        workflowOptions.value = ['重试', '跳过', '取消']
        workflowStepId.value = stepId

        replyText.value = workflowQuestion.value
        stage.value = 'sidebar-waiting'
        isLoading.value = false
      }
      break

    case 'step_precondition_failed':
      console.log('[MagicWand] step_precondition_failed:', event)
      // 步骤前置条件失败
      if (event.data) {
        console.warn(`[MagicWand] 前置条件失败: ${event.data.message}`)
      }
      break
  }
}

// ========== Workflow 处理函数 ==========

/**
 * 处理 Workflow waiting_for_user 事件
 */
function handleWorkflowWaiting(event: AIAssistantSSEEvent) {
  console.log('[MagicWand] handleWorkflowWaiting:', event)

  // 保存 workflow 状态
  const data = event.data as {
    session_id?: string
    step_id?: string
    question?: string
    options?: string[]
    trace_id?: string
    missing_fields?: string[]
    field_options?: Record<string, any>
  } || {}

  workflowSessionId.value = data.session_id || event.session_id || ''
  workflowStepId.value = data.step_id || ''
  workflowQuestion.value = data.question || event.question || ''
  workflowOptions.value = data.options || event.options || []
  workflowTraceId.value = data.trace_id || event.trace_id || ''
  workflowMissingFields.value = data.missing_fields || event.missing_fields || []
  workflowFieldOptions.value = data.field_options || event.field_options || {}

  // 设置 AI 回复文本
  replyText.value = workflowQuestion.value

  // 判断是显示表单还是按钮选项
  if (workflowMissingFields.value.length > 0) {
    // 有缺失字段，显示表单填充
    workflowMissingFieldsForm.value = true
    // 初始化表单值（设置默认值）
    workflowMissingFields.value.forEach(field => {
      const fieldConfig = workflowFieldOptions.value[field]
      if (fieldConfig?.type === 'select' && fieldConfig.options?.length > 0) {
        // 下拉选择：默认选中第一个或指定的默认值
        missingFieldsFormValues.value[field] = fieldConfig.default || fieldConfig.options[0]
      } else {
        // 其他字段：空值
        missingFieldsFormValues.value[field] = ''
      }
    })
    stage.value = 'sidebar-waiting'
  } else if (workflowOptions.value.length > 0) {
    // 有选项按钮，显示按钮
    workflowMissingFieldsForm.value = false
    stage.value = 'sidebar-waiting'
  } else {
    // 没有选项也没有缺失字段，只显示输入框让用户自由输入
    workflowMissingFieldsForm.value = false
    if (!useLegacyMode.value) {
      stage.value = 'sidebar-waiting'
    } else {
      stage.value = 'workflow-waiting'
    }
  }
  isLoading.value = false
}

/**
 * 处理缺失字段表单提交
 */
async function handleMissingFieldsSubmit() {
  console.log('[MagicWand] handleMissingFieldsSubmit:', missingFieldsFormValues.value)

  // 表单验证
  try {
    await missingFieldsFormRef.value?.validate()
  } catch {
    ElMessage.warning('请填写所有必填字段')
    return
  }

  // 立即清空表单状态，防止重复提交
  workflowMissingFieldsForm.value = false
  const fieldsCopy = [...workflowMissingFields.value]
  const valuesCopy = { ...missingFieldsFormValues.value }
  workflowMissingFields.value = []
  missingFieldsFormValues.value = {}

  // 构建用户回复
  const responseParts: string[] = []
  fieldsCopy.forEach(field => {
    const value = valuesCopy[field]
    if (value) {
      responseParts.push(`${getFriendlyFieldLabel(field)}: ${value}`)
    }
  })
  const userResponse = responseParts.join('\n')

  // 设置 loading 状态
  isLoading.value = true
  stage.value = 'sidebar-loading'
  loadingMessage.value = '正在处理...'
  replyText.value = ''

  // 发送回复并继续 workflow
  try {
    await continueWorkflowSSE(
      {
        session_id: workflowSessionId.value,
        user_response: userResponse
      },
      (event) => {
        handleSSEEvent(event as AIAssistantSSEEvent)
      },
      userStore.token
    )
  } catch (error: unknown) {
    const err = error as Error
    console.error('[MagicWand] Workflow continue error:', err)
    ElMessage.error(err.message || '继续流程失败')
    stage.value = 'sidebar-input'
  } finally {
    isLoading.value = false
  }
}

/**
 * 取消缺失字段表单
 */
function handleMissingFieldsCancel() {
  console.log('[MagicWand] handleMissingFieldsCancel')

  workflowMissingFieldsForm.value = false
  workflowMissingFields.value = []
  missingFieldsFormValues.value = {}
  stage.value = 'sidebar-input'
  replyText.value = ''
}

/**
 * 用户选择 Workflow 选项（或通过输入框回复）
 */
async function handleWorkflowChoice(option: string) {
  console.log('[MagicWand] handleWorkflowChoice:', option, workflowSessionId.value)

  if (!workflowSessionId.value) {
    ElMessage.error('会话已过期')
    stage.value = 'sidebar-input'
    return
  }

  isLoading.value = true
  stage.value = 'sidebar-loading'
  replyText.value = ''
  userInput.value = ''  // 清空输入框

  try {
    const token = userStore.token
    await continueWorkflowSSE(
      {
        session_id: workflowSessionId.value,
        user_response: option
      },
      (event) => {
        console.log('[MagicWand] Workflow continue SSE event:', event)
        // WorkflowEvent 和 AIAssistantSSEEvent 结构相似，可以复用 handleSSEEvent
        handleSSEEvent(event as AIAssistantSSEEvent)
      },
      token
    )
  } catch (error: unknown) {
    const err = error as Error
    console.error('[MagicWand] Workflow continue error:', err)
    ElMessage.error(err.message || '继续流程失败')
    stage.value = 'sidebar-input'
  } finally {
    isLoading.value = false
  }
}

// ========== 多工具处理函数 ==========

/**
 * 处理 parsed_multi 事件（多工具依次确认）
 */
function handleParsedMulti(event: AIAssistantSSEEvent) {
  console.log('[MagicWand] handleParsedMulti:', event)

  // 设置 ReAct 模式
  reactMode.value = true
  reactRound.value = event.round || 1
  previousResults.value = event.previous_results || []

  // 初始化工具队列
  toolCallQueue.value = event.tool_calls || []
  currentToolIndex.value = 0
  executedResults.value = []

  replyText.value = event.reply_text || ''

  // 判断是否需要表单填充
  const firstCall = toolCallQueue.value[0]
  if (firstCall?.param_definitions && Object.keys(firstCall.param_definitions).length > 0) {
    // 有参数定义，进入表单填充阶段
    paramDefinitions.value = firstCall.param_definitions
    missingParams.value = firstCall.missing_params || []
    previewAction.value = {
      tool: firstCall.tool,
      params: firstCall.params
    }
    stage.value = 'preview-multi-form'
  } else {
    // 无参数定义，直接预览确认
    previewAction.value = {
      tool: firstCall?.tool || '',
      params: firstCall?.params || {}
    }
    stage.value = 'preview-multi'
  }
}

/**
 * 处理实体歧义事件
 */
function handleDisambiguation(event: AIAssistantSSEEvent) {
  console.log('[MagicWand] handleDisambiguation:', event)

  // 设置 ReAct 模式（保持之前的轮数）
  reactMode.value = true
  reactRound.value = event.round || reactRound.value
  previousResults.value = event.previous_results || []

  // 设置歧义数据
  disambiguationEntityType.value = event.entity_type || 'opportunity'
  disambiguationCandidates.value = event.candidates || []
  disambiguationMessage.value = event.message || '请选择要操作的实体'

  // 保存待执行的工具
  pendingToolCall.value = {
    tool: event.tool || '',
    params: event.params || {},
    reply_text: ''
  }

  // 显示选择弹窗
  disambiguationVisible.value = true
  stage.value = 'disambiguation'
}

// ========== Phase F: 显式确认处理函数 ==========

/**
 * 处理 pending_confirmation 事件
 */
function handlePendingConfirmation(event: AIAssistantSSEEvent) {
  console.log('[MagicWand] handlePendingConfirmation:', event)

  // 判断是否使用 Sidebar 模式
  const useSidebar = !useLegacyMode.value && (event.inline_pill || event.workflow_mini_map)

  if (useSidebar) {
    // Sidebar 模式：使用 inline_pill 数据
    if (event.inline_pill) {
      inlinePillData.value = {
        actionType: event.inline_pill.action_type || event.tool_name,
        actionDisplayName: event.inline_pill.action_display_name || getToolDisplayName(event.tool_name),
        params: event.inline_pill.params || event.params || {},
        riskLevel: event.inline_pill.risk_level || event.risk_level || 'medium',
        summaryText: event.inline_pill.summary_text || buildSummaryText(event.tool_name, event.params),
        detailedParams: event.inline_pill.detailed_params || event.params || {},
        recommendation: event.inline_pill.recommendation,
        undoTtl: event.inline_pill.undo_ttl || event.undo_config?.ttl || 10
      }
    }

    // Workflow Mini-map 数据
    if (event.workflow_mini_map) {
      workflowMiniMapData.value = {
        steps: event.workflow_mini_map.steps || [],
        currentStep: event.workflow_mini_map.current_step || 0
      }
    }

    // 进入 Sidebar 确认阶段
    stage.value = 'sidebar-pill'
    workflowSessionId.value = event.session_id || workflowSessionId.value
  } else {
    // 兼容模式：使用原有的 confirmationData
    confirmationData.value = {
      stepId: event.step_id,
      toolName: event.tool_name,
      riskLevel: event.risk_level || 'medium',
      params: event.params || {},
      display: event.display || {},
      undoConfig: event.undo_config || {},
      allowEdit: event.confirmation_config?.allow_param_edit ?? false
    }

    // 进入确认阶段
    stage.value = 'pending-confirmation'
  }
}

/**
 * 构建摘要文本（用于 inline_pill）
 */
function buildSummaryText(toolName: string, params: Record<string, any>): string {
  if (toolName === 'follow_up_customer' || toolName === 'follow_up_lead') {
    const content = params.content || ''
    return content.length > 30 ? content.substring(0, 30) + '...' : content
  }
  if (toolName === 'win_opportunity') {
    const name = params.opportunity_name || '未知商机'
    const amount = params.actual_amount || '未知金额'
    return `${name} (${amount}万)`
  }
  if (toolName === 'create_contract') {
    const name = params.customer_name || '未知客户'
    const amount = params.contract_amount || '未知金额'
    return `${name} (${amount}万)`
  }
  return JSON.stringify(params).substring(0, 50)
}

/**
 * 处理 undo_available 事件
 */
function handleUndoAvailable(event: AIAssistantSSEEvent) {
  console.log('[MagicWand] handleUndoAvailable:', event)

  // 显示撤销 Toast
  undoToastData.value = {
    operationId: event.operation_id,
    undoEndpoint: event.undo_endpoint,
    ttl: event.undo_ttl || 10,
    message: '操作已执行',
    visible: true
  }
}

/**
 * 隐藏撤销 Toast
 */
function hideUndoToast() {
  undoToastData.value.visible = false
}

/**
 * 确认执行（pending_confirmation 阶段）
 */
async function handleConfirmationConfirm(updatedParams?: Record<string, any>) {
  console.log('[MagicWand] handleConfirmationConfirm:', updatedParams)

  isLoading.value = true
  stage.value = 'loading'

  try {
    // 发送确认请求
    await workflowApi.continueWorkflow(sessionId.value, {
      action: 'confirm',
      step_id: confirmationData.value.stepId,
      params: updatedParams || confirmationData.value.params
    })

    // 等待后续事件（step_result / undo_available）
  } catch (error: unknown) {
    const err = error as Error
    console.error('[MagicWand] Confirmation confirm error:', err)
    ElMessage.error(err.message || '确认执行失败')
    stage.value = 'pending-confirmation'
  } finally {
    isLoading.value = false
  }
}

/**
 * 取消执行（pending_confirmation 阶段）
 */
async function handleConfirmationCancel() {
  console.log('[MagicWand] handleConfirmationCancel')

  isLoading.value = true

  try {
    await workflowApi.continueWorkflow(sessionId.value, {
      action: 'cancel',
      step_id: confirmationData.value.stepId
    })

    // 返回输入阶段
    stage.value = 'input'
  } catch (error: unknown) {
    const err = error as Error
    console.error('[MagicWand] Confirmation cancel error:', err)
    ElMessage.error(err.message || '取消失败')
  } finally {
    isLoading.value = false
  }
}

/**
 * 撤销成功回调
 */
function handleUndoSuccess() {
  console.log('[MagicWand] Undo success')
  hideUndoToast()
  ElMessage.success('操作已撤销')
  emit('refresh')
}

/**
 * 撤销失败回调
 */
function handleUndoFailed(reason: string) {
  console.log('[MagicWand] Undo failed:', reason)
  ElMessage.error(reason || '撤销失败')
}

// ========== Phase G: Sidebar 处理函数 ==========

/**
 * 处理 Inline Pill 确认
 */
async function handleInlinePillConfirm(updatedParams?: Record<string, any>) {
  console.log('[MagicWand] handleInlinePillConfirm:', updatedParams)

  isLoading.value = true
  stage.value = 'sidebar-loading'
  loadingMessage.value = '正在执行...'

  try {
    // 发送确认请求
    if (workflowSessionId.value) {
      await continueWorkflowSSE(
        {
          session_id: workflowSessionId.value,
          user_response: 'confirm',
          params: updatedParams || inlinePillData.value.params
        },
        (event) => {
          handleSSEEvent(event as AIAssistantSSEEvent)
        },
        userStore.token
      )
    }
  } catch (error: unknown) {
    const err = error as Error
    console.error('[MagicWand] Inline Pill confirm error:', err)
    ElMessage.error(err.message || '执行失败')
    stage.value = 'sidebar-pill'
  } finally {
    isLoading.value = false
  }
}

/**
 * 处理 Inline Pill 取消
 */
async function handleInlinePillCancel() {
  console.log('[MagicWand] handleInlinePillCancel')

  isLoading.value = true

  try {
    if (workflowSessionId.value) {
      await continueWorkflowSSE(
        {
          session_id: workflowSessionId.value,
          user_response: 'cancel'
        },
        (event) => {
          handleSSEEvent(event as AIAssistantSSEEvent)
        },
        userStore.token
      )
    }

    // 返回输入阶段
    stage.value = 'sidebar-input'
  } catch (error: unknown) {
    const err = error as Error
    console.error('[MagicWand] Inline Pill cancel error:', err)
    ElMessage.error(err.message || '取消失败')
  } finally {
    isLoading.value = false
  }
}

/**
 * 处理选择推荐项的替代选项
 */
async function handleSelectAlternative(id: number) {
  console.log('[MagicWand] handleSelectAlternative:', id)

  // 更新 inlinePillData 中的推荐选项
  if (inlinePillData.value.recommendation?.alternatives) {
    const selected = inlinePillData.value.recommendation.alternatives.find(a => a.id === id)
    if (selected) {
      inlinePillData.value.recommendation = {
        option: selected,
        reason: '用户手动选择',
        alternatives: inlinePillData.value.recommendation.alternatives.filter(a => a.id !== id)
      }
    }
  }
}

/**
 * 处理撤销上一步（Mini-map）
 */
async function handleUndoLastStep() {
  console.log('[MagicWand] handleUndoLastStep')

  try {
    if (workflowSessionId.value) {
      const response = await fetch(`/workflow/undo/workflow/${workflowSessionId.value}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })

      const result = await response.json()

      if (result.success) {
        ElMessage.success(`已撤销 ${result.undone_count} 个操作`)
        emit('refresh')

        // 重新获取 Workflow 状态
        // TODO: 调用 API 获取最新状态
      } else {
        ElMessage.error(result.reason || '撤销失败')
      }
    }
  } catch (error) {
    console.error('[MagicWand] Undo last step error:', error)
    ElMessage.error('撤销失败')
  }
}

/**
 * 处理暂停流程
 */
async function handlePauseWorkflow() {
  console.log('[MagicWand] handlePauseWorkflow')

  ElMessage.info('流程已暂停，可随时继续')
  stage.value = 'sidebar-input'
}

/**
 * 处理单轮完成事件
 */
function handleRoundCompleted(event: AIAssistantSSEEvent) {
  console.log('[MagicWand] handleRoundCompleted:', event)

  // 记录本轮执行结果
  if (event.results) {
    executedResults.value = event.results
  }

  // 进入进度展示阶段，等待下一轮
  stage.value = 'react-progress'
}

/**
 * 用户选择实体后的回调
 */
async function handleEntitySelect(candidate: EntityCandidate) {
  console.log('[MagicWand] handleEntitySelect:', candidate)

  disambiguationVisible.value = false

  if (!pendingToolCall.value) return

  // 将选择的实体 ID 注入参数
  const entityType = disambiguationEntityType.value
  const updatedParams = { ...pendingToolCall.value.params }

  // 根据实体类型设置参数
  if (entityType === 'opportunity') {
    updatedParams['opportunity_id'] = candidate.id
    updatedParams['opportunity_name'] = candidate.name
  } else if (entityType === 'contact') {
    updatedParams['contact_id'] = candidate.id
    updatedParams['contact_name'] = candidate.name
  } else if (entityType === 'contract') {
    updatedParams['contract_id'] = candidate.id
    updatedParams['contract_name'] = candidate.name
  }

  // 继续执行工具
  isExecuting.value = true

  try {
    await executeSingleToolWithParams(pendingToolCall.value.tool, updatedParams)
  } finally {
    isExecuting.value = false
  }
}

/**
 * 用户取消实体选择
 */
function handleEntitySelectCancel() {
  disambiguationVisible.value = false
  stage.value = 'input'
}

// ========== 依次确认处理函数 ==========

/**
 * 获取工具显示名称
 */
function getToolDisplayName(toolName: string): string {
  const toolNames: Record<string, string> = {
    follow_up_customer: '创建跟进记录',
    win_opportunity: '标记商机赢单',
    lose_opportunity: '标记商机输单',
    create_opportunity: '创建商机',
    update_opportunity_stage: '推进商机阶段',
    create_contract: '创建合同',
    query_contracts: '查询合同',
    get_contract_detail: '获取合同详情',
    update_contract_status: '更新合同状态',
    create_payment_plan: '创建回款计划',
    create_payment_record: '登记回款',
    query_payment_records: '查询回款记录',
    confirm_payment: '确认回款',
    create_invoice_application: '申请开票',
    query_invoice_applications: '查询开票申请',
    get_invoice_application_detail: '获取开票申请详情'
  }
  return toolNames[toolName] || toolName
}

/**
 * 确认当前工具（多工具依次确认）
 */
async function handleConfirmCurrentTool() {
  if (!currentToolCall.value) return

  isExecuting.value = true

  try {
    await executeSingleTool(
      currentToolCall.value.tool,
      currentToolCall.value.params
    )

    // 显示成功提示
    ElMessage.success(`${getToolDisplayName(currentToolCall.value.tool)} 执行成功`)

    // 处理下一个工具或进入下一轮
    moveToNextToolOrRound()
  } catch (error: unknown) {
    const err = error as Error
    // 记录失败结果
    executedResults.value.push({
      tool: currentToolCall.value.tool,
      success: false,
      message: err.message
    })

    ElMessage.error(`${getToolDisplayName(currentToolCall.value.tool)} 执行失败：${err.message}`)

    // 继续处理下一个工具（不中断）
    moveToNextToolOrRound()
  } finally {
    isExecuting.value = false
  }
}

/**
 * 确认当前工具表单提交（多工具表单填充后）
 */
async function handleMultiFormSubmit(values: Record<string, unknown>) {
  if (!currentToolCall.value) return

  isExecuting.value = true

  // 合并表单值与现有参数
  const mergedParams = {
    ...currentToolCall.value.params,
    ...values
  }

  try {
    await executeSingleTool(
      currentToolCall.value.tool,
      mergedParams
    )

    ElMessage.success(`${getToolDisplayName(currentToolCall.value.tool)} 执行成功`)
    moveToNextToolOrRound()
  } catch (error: unknown) {
    const err = error as Error
    executedResults.value.push({
      tool: currentToolCall.value.tool,
      success: false,
      message: err.message
    })
    ElMessage.error(`${getToolDisplayName(currentToolCall.value.tool)} 执行失败：${err.message}`)
    moveToNextToolOrRound()
  } finally {
    isExecuting.value = false
  }
}

/**
 * 跳过当前工具
 */
function handleSkipCurrentTool() {
  if (!currentToolCall.value) return

  // 记录跳过
  executedResults.value.push({
    tool: currentToolCall.value.tool,
    success: false,
    message: '用户跳过'
  })

  ElMessage.info(`已跳过 ${getToolDisplayName(currentToolCall.value.tool)}`)
  moveToNextToolOrRound()
}

/**
 * 取消后续所有工具
 */
function handleCancelAllTools() {
  stage.value = 'result'
  success.value = executedResults.value.some(r => r.success)

  const successCount = executedResults.value.filter(r => r.success).length
  const skipCount = executedResults.value.filter(r => !r.success).length

  resultMessage.value = `已完成 ${successCount} 个操作，跳过 ${skipCount} 个操作`
}

/**
 * 移动到下一个工具或进入下一轮
 */
function moveToNextToolOrRound() {
  if (hasMoreTools.value) {
    // 进入下一个工具
    currentToolIndex.value++

    const nextCall = toolCallQueue.value[currentToolIndex.value]
    if (nextCall?.param_definitions && Object.keys(nextCall.param_definitions).length > 0) {
      // 有参数定义，进入表单填充阶段
      paramDefinitions.value = nextCall.param_definitions
      missingParams.value = nextCall.missing_params || []
      previewAction.value = {
        tool: nextCall.tool,
        params: nextCall.params
      }
      stage.value = 'preview-multi-form'
    } else {
      // 无参数定义，直接预览确认
      previewAction.value = {
        tool: nextCall?.tool || '',
        params: nextCall?.params || {}
      }
      stage.value = 'preview-multi'
    }
  } else {
    // 本轮所有工具完成
    if (reactMode.value) {
      // ReAct 模式，进入下一轮
      stage.value = 'react-progress'
      continueReactRound()
    } else {
      // 非 ReAct 模式，显示最终结果
      showFinalResult()
    }
  }
}

/**
 * 执行单个工具
 */
async function executeSingleTool(toolName: string, params: Record<string, unknown>) {
  const token = userStore.token || localStorage.getItem('token') || ''

  return new Promise<void>((resolve, reject) => {
    aiAssistantApi.chatSSE(
      {
        content: '确认执行',
        tool: toolName,
        params
      },
      (event: AIAssistantSSEEvent) => {
        if (event.event === 'result') {
          // 记录执行结果
          executedResults.value.push({
            tool: toolName,
            success: event.success !== false,
            message: event.message || '执行成功'
          })
          resolve()
        } else if (event.event === 'error') {
          reject(new Error(event.message || '执行失败'))
        }
      },
      token
    )
  })
}

/**
 * 执行单个工具（带参数）
 */
async function executeSingleToolWithParams(toolName: string, params: Record<string, unknown>) {
  await executeSingleTool(toolName, params)
  moveToNextToolOrRound()
}

/**
 * 继续 ReAct 循环下一轮
 */
async function continueReactRound() {
  if (reactRound.value >= maxRounds.value) {
    // 达到最大轮数，显示完成
    stage.value = 'result'
    success.value = true
    resultMessage.value = `已完成 ${reactRound.value} 轮处理（达到最大轮数限制）`
    emit('refresh')
    return
  }

  isLoading.value = true
  replyText.value = 'AI 继续分析下一步操作...'

  const token = userStore.token || localStorage.getItem('token') || ''

  try {
    await aiAssistantApi.continueReactSSE(
      {
        round: reactRound.value,
        original_content: userInput.value,
        executed_results: executedResults.value
      },
      (event: AIAssistantSSEEvent) => {
        handleSSEEvent(event)
      },
      token
    )
  } catch (error: unknown) {
    const err = error as Error
    ElMessage.error(`继续处理失败：${err.message}`)
    showFinalResult()
  } finally {
    isLoading.value = false
  }
}

/**
 * 显示最终结果
 */
function showFinalResult() {
  stage.value = 'result'
  success.value = executedResults.value.some(r => r.success)

  const successCount = executedResults.value.filter(r => r.success).length
  const totalCount = executedResults.value.length

  if (successCount === totalCount) {
    resultMessage.value = `全部 ${successCount} 个操作执行成功`
  } else {
    resultMessage.value = `已完成 ${successCount}/${totalCount} 个操作`
  }

  emit('refresh')
}

async function handleExecute() {
  // Customer follow-up confirmation
  if (stage.value === 'preview-followup' && customerFollowUpInfo.value) {
    await handleCustomerFollowUpCreate()
    return
  }

  // Generic skill/action confirmation
  if (!previewAction.value) {
    ElMessage.warning('没有可执行的操作')
    return
  }

  isExecuting.value = true

  const token = userStore.token || localStorage.getItem('token') || ''

  try {
    await aiAssistantApi.chatSSE(
      {
        content: '确认执行',
        tool: previewAction.value.tool,
        params: previewAction.value.params
      },
      (event: AIAssistantSSEEvent) => {
        if (event.event === 'result' || event.event === 'error') {
          handleSSEEvent(event)
        }
      },
      token
    )
  } catch (error: unknown) {
    const err = error as Error
    ElMessage.error(err.message || '执行失败')
    success.value = false
    resultMessage.value = err.message || '执行失败'
    stage.value = 'result'
  } finally {
    isExecuting.value = false
  }
}

async function handleCustomerFollowUpCreate() {
  isExecuting.value = true

  try {
    await customerAiApi.create({
      customer_id: props.entityId,
      customer_name: props.entityName,
      content: customerFollowUpInfo.value?.content || userInput.value,
      method: customerFollowUpInfo.value?.method ?? undefined,
      next_action: customerFollowUpInfo.value?.next_action ?? undefined,
      next_follow_time: customerFollowUpInfo.value?.next_follow_time ?? undefined
    })

    success.value = true
    resultMessage.value = '跟进记录已创建'
    stage.value = 'result'
    emit('refresh')
  } catch (error: unknown) {
    const err = error as Error
    ElMessage.error(err.message || '创建失败')
    success.value = false
    resultMessage.value = err.message || '创建失败'
    stage.value = 'result'
  } finally {
    isExecuting.value = false
  }
}

async function handleFormSubmit(values: Record<string, unknown>) {
  if (!previewAction.value) {
    ElMessage.warning('没有可执行的操作')
    return
  }

  isExecuting.value = true

  // Merge form values with existing params
  const mergedParams = {
    ...previewAction.value.params,
    ...values
  }

  const token = userStore.token || localStorage.getItem('token') || ''

  try {
    await aiAssistantApi.chatSSE(
      {
        content: '确认执行',
        tool: previewAction.value.tool,
        params: mergedParams
      },
      (event: AIAssistantSSEEvent) => {
        if (event.event === 'result' || event.event === 'error') {
          handleSSEEvent(event)
        }
      },
      token
    )
  } catch (error: unknown) {
    const err = error as Error
    ElMessage.error(err.message || '执行失败')
    success.value = false
    resultMessage.value = err.message || '执行失败'
    stage.value = 'result'
  } finally {
    isExecuting.value = false
  }
}

function resetDialog() {
  // Sidebar 模式下使用 sidebar-input，否则使用 input
  stage.value = useLegacyMode.value ? 'input' : 'sidebar-input'
  userInput.value = ''
  replyText.value = ''
  previewAction.value = null
  success.value = false
  resultMessage.value = ''
  isLoading.value = false
  isExecuting.value = false
  customerFollowUpInfo.value = null
  thinkingContent.value = ''
  paramDefinitions.value = {}
  missingParams.value = []

  // ReAct 状态重置
  reactMode.value = false
  reactRound.value = 1
  toolCallQueue.value = []
  currentToolIndex.value = 0
  executedResults.value = []
  previousResults.value = []

  // 实体歧义状态重置
  disambiguationVisible.value = false
  disambiguationCandidates.value = []
  disambiguationMessage.value = ''
  pendingToolCall.value = null

  // 上下文汇总状态重置
  contextSummary.value = null
  enhancedContentPreview.value = ''
  showContextDetail.value = false

  // Workflow 状态重置
  workflowSessionId.value = ''
  workflowQuestion.value = ''
  workflowOptions.value = []
  workflowMissingFields.value = []
  workflowMissingFieldsForm.value = false
  workflowFieldOptions.value = {}
  missingFieldsFormValues.value = {}

  // 状态卡片重置
  statusCards.value = []
  showQuickCommands.value = false
}

function handleClose() {
  emit('update:modelValue', false)
}

// ========== Phase 1: 状态驱动操作按钮方法 ==========

/**
 * 停止当前操作（EXECUTING 状态）
 */
function handleStopOperation() {
  console.log('[MagicWand] handleStopOperation')
  // 中断当前操作
  isLoading.value = false
  isExecuting.value = false
  // 重置状态到 IDLE
  sidebarStateManager.userStop()
  stage.value = 'sidebar-input'
  replyText.value = ''
  ElMessage.info('操作已停止')
}

/**
 * 新对话（COMPLETED 状态）
 */
function handleNewChat() {
  console.log('[MagicWand] handleNewChat')
  // 清空对话，返回 IDLE
  sidebarStateManager.userNewChat()
  resetDialog()
  ElMessage.info('开始新对话')
}

// ========== Phase H: 智能输入栏方法 ==========

/**
 * 插入快捷指令
 */
function insertCommand(command: string) {
  userInput.value = command + ' '
  showQuickCommands.value = false
}

/**
 * 输入变化时检测快捷指令
 */
function handleInputChange(value: string) {
  // 输入 / 时显示快捷指令
  if (value.endsWith('/') || value === '/') {
    showQuickCommands.value = true
  } else {
    showQuickCommands.value = false
  }
}

/**
 * 键盘事件处理
 */
function handleKeyDown(event: KeyboardEvent) {
  // ESC 关闭快捷指令菜单
  if (event.key === 'Escape' && showQuickCommands.value) {
    showQuickCommands.value = false
    event.preventDefault()
  }
}

/**
 * 撤销状态卡片对应的操作
 */
function handleUndoCard(index: number) {
  const card = statusCards.value[index]
  if (card && card.undoEndpoint) {
    // TODO: 实现撤销逻辑
    ElMessage.info('撤销功能开发中')
  } else {
    ElMessage.info('暂无可撤销的操作')
  }
}

/**
 * 重试失败的操作（补充信息）
 */
function handleRetryCard(card: StatusCardData) {
  // 将缺失字段信息转换为用户提示
  if (card.missingFields && card.missingFields.length > 0) {
    userInput.value = `请补充：${card.missingFields.join('、')}`
    stage.value = 'sidebar-input'
  } else {
    ElMessage.info('请重新描述操作')
  }
}

/**
 * 忽略失败的卡片
 */
function handleIgnoreCard(index: number) {
  statusCards.value.splice(index, 1)
  ElMessage.info('已忽略此错误')
}

/**
 * 字段名映射表：英文名 -> 中文友好标签
 */
const FIELD_LABEL_MAP: Record<string, string> = {
  product_name: '产品名称',
  expected_amount: '预计金额（万元）',
  expected_closing_date: '预期成交日期',
  total_amount: '预计总金额（万元）',
  procurement_method_name: '采购方式',
  purchase_type: '采购类型',
  product: '产品名称',
  amount: '预计金额（万元）',
  actual_amount: '实际成交金额（万元）',
  actual_closing_date: '实际成交日期',
  opportunity_name: '商机名称',
  customer_name: '客户名称',
  contract_amount: '合同金额（万元）',
  signed_date: '签约日期',
  contact_name: '联系人姓名',
  contact_phone: '联系电话',
  lead_name: '线索名称',
  source: '来源',
  city: '城市',
  user_count: '采购人数',
  subscription_years: '订阅年限',
  license_type: '授权模式',
  // 中文字段名直接映射
  '预计金额': '预计金额（万元）',
  '预计总金额': '预计金额（万元）',
  '预期成交日期': '预期成交日期',
  '产品名称': '产品名称',
  '商机名称': '商机名称',
  '采购人数': '采购人数',
  '订阅年限': '订阅年限',
  '采购方式': '采购方式',
  '采购类型': '采购类型'
}

/**
 * 字段名映射表：英文名 -> placeholder 提示
 */
const FIELD_PLACEHOLDER_MAP: Record<string, string> = {
  product_name: '请输入产品名称，如：CRM系统',
  expected_amount: '请输入预计金额（万元），如：50',
  expected_closing_date: '请选择预期成交日期',
  total_amount: '请输入预计总金额（万元），如：50',
  procurement_method_name: '请选择采购方式',
  purchase_type: '请选择采购类型',
  product: '请输入产品名称',
  amount: '请输入预计金额（万元）',
  actual_amount: '请输入实际成交金额（万元）',
  actual_closing_date: '请选择实际成交日期',
  opportunity_name: '请输入商机名称',
  customer_name: '请输入客户名称',
  contract_amount: '请输入合同金额（万元）',
  signed_date: '请选择签约日期',
  contact_name: '请输入联系人姓名',
  contact_phone: '请输入联系电话（11位手机号）',
  lead_name: '请输入线索名称',
  source: '请选择来源',
  city: '请输入城市',
  user_count: '请输入采购人数，如：50',
  subscription_years: '请输入订阅年限，如：1',
  license_type: '请选择授权模式（订阅制/买断制）',
  // 中文字段名
  '预计金额': '请输入预计金额（万元），如：50',
  '预计总金额': '请输入预计金额（万元），如：50',
  '预期成交日期': '请选择预期成交日期',
  '产品名称': '请输入产品名称',
  '商机名称': '请输入商机名称',
  '采购人数': '请输入采购人数',
  '订阅年限': '请输入订阅年限',
  '采购方式': '请选择采购方式',
  '采购类型': '请选择采购类型'
}

/**
 * 获取字段友好标签
 */
function getFriendlyFieldLabel(field: string): string {
  return FIELD_LABEL_MAP[field] || field
}

/**
 * 获取字段 placeholder 提示
 */
function getFriendlyFieldPlaceholder(field: string): string {
  return FIELD_PLACEHOLDER_MAP[field] || `请输入${getFriendlyFieldLabel(field)}`
}

/**
 * 判断是否是日期字段
 */
function isDateField(field: string): boolean {
  const dateFields = [
    'expected_closing_date',
    'actual_closing_date',
    'signed_date',
    'next_follow_time',
    'expected_close_date',
    '预期成交日期',
    '成交日期',
    '签约日期',
    '下次跟进时间'
  ]
  return dateFields.includes(field) || field.includes('date') || field.includes('日期')
}

/**
 * 判断是否是金额字段
 */
function isAmountField(field: string): boolean {
  const amountFields = [
    'total_amount',
    'expected_amount',
    'actual_amount',
    'contract_amount',
    'amount',
    '预计金额',
    '预计总金额',
    '实际成交金额',
    '合同金额'
  ]
  return amountFields.includes(field) || field.includes('amount') || field.includes('金额')
}

/**
 * 判断是否是下拉选择字段
 */
function isSelectField(field: string): boolean {
  const fieldConfig = workflowFieldOptions.value[field]
  return fieldConfig?.type === 'select' && fieldConfig?.options?.length > 0
}

/**
 * 获取下拉字段的选项列表
 */
function getFieldOptions(field: string): string[] {
  const fieldConfig = workflowFieldOptions.value[field]
  return fieldConfig?.options || []
}

/**
 * 简单的 Markdown 渲染函数
 */
function renderMarkdown(text: string): string {
  if (!text) return ''

  // 处理表格（Markdown table syntax）
  // 表格格式: | 列1 | 列2 | ... |\n|---|---|...|\n| 数据1 | 数据2 | ... |
  const tableRegex = /\|(.+)\|\n\|[-\s|]+\|\n((\|.+\|\n)+)/g
  text = text.replace(tableRegex, (match) => {
    const lines = match.trim().split('\n')
    if (lines.length < 2) return match

    // 解析表头
    const headerLine = lines[0]
    const headers = headerLine.split('|').filter(h => h.trim()).map(h => h.trim())

    // 解析数据行（跳过分隔行）
    const dataLines = lines.slice(2)
    const rows = dataLines.map(line => {
      const cells = line.split('|').filter(c => c.trim()).map(c => c.trim())
      return `<tr>${cells.map(c => `<td>${c}</td>`).join('')}</tr>`
    }).join('')

    // 构建表格 HTML
    const headerHtml = headers.map(h => `<th>${h}</th>`).join('')
    return `<table class="md-table"><thead><tr>${headerHtml}</tr></thead><tbody>${rows}</tbody></table>`
  })

  // 处理加粗 **text**
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')

  // 处理列表项 - text 或 * text
  text = text.replace(/^[•\-\*]\s(.+)/gm, '<li>$1</li>')

  // 如果有列表项，包裹在 <ul> 中
  if (text.includes('<li>')) {
    text = text.replace(/(<li>.*<\/li>\n?)+/g, '<ul class="md-list">$&</ul>')
  }

  // 处理换行（排除表格内的换行）
  text = text.replace(/\n(?![^\n]*\|)/g, '<br>')

  return text
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

// ========== Phase 3: 主输入框容器样式 ==========

.main-input-container {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  padding: $wolf-space-lg $wolf-space-8;  // 24px 32px
  background: $wolf-bg-page;
  border-top: 1px solid $wolf-border-divider;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

// 响应式适配
@media (max-width: 768px) {
  .main-input-container {
    padding: $wolf-space-md;
  }
}

// ========== 原有样式 ==========

.stage-input,
.stage-clarify,
.stage-preview,
.stage-preview-multi,
.stage-preview-multi-form,
.stage-react-progress,
.stage-workflow-waiting,
.stage-result {
  padding: $wolf-space-sm 0;
}

.stage-workflow-waiting {
  .workflow-question {
    display: flex;
    align-items: flex-start;
    gap: $wolf-space-sm;
    padding: $wolf-space-md;
    background: $wolf-bg-hover;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;
    font-size: $wolf-font-size-body;
    color: $wolf-text-primary;
    line-height: 1.5;

    .el-icon {
      font-size: 20px;
      color: $wolf-primary;
    }
  }

  .workflow-options {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-sm;

    .el-button {
      width: 100%;
      justify-content: center;
    }
  }
}

.stage-preview-form {
  padding: $wolf-space-sm 0;

  .ai-reply {
    display: flex;
    gap: $wolf-space-sm;
    padding: $wolf-space-md;
    background: $wolf-bg-hover;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;
  }

  .reply-icon {
    font-size: 20px;
  }

  .reply-content {
    flex: 1;
    font-size: $wolf-font-size-body;
    color: $wolf-text-primary;
    line-height: 1.5;
  }

  .form-section {
    margin-top: $wolf-space-md;
  }
}

.entity-info {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-md;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-md;
  margin-bottom: $wolf-space-md;
}

.entity-avatar {
  width: 40px;
  height: 40px;
  border-radius: $wolf-radius-full;
  background: $wolf-primary-light;
  color: $wolf-primary;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: $wolf-font-weight-semibold;
}

.entity-meta {
  flex: 1;
}

.entity-name {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.entity-type {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.input-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-bottom: $wolf-space-sm;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-xs;
  margin-top: $wolf-space-md;
}

.ai-reply {
  display: flex;
  gap: $wolf-space-sm;
  padding: $wolf-space-md;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-md;
  margin-bottom: $wolf-space-md;
}

.reply-icon {
  font-size: 20px;
}

.reply-content {
  flex: 1;
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  line-height: 1.5;
}

.action-preview {
  padding: $wolf-space-md;
  background: $wolf-warning-bg;
  border-radius: $wolf-radius-md;
  margin-bottom: $wolf-space-md;
}

.preview-header {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-warning-text;
  margin-bottom: $wolf-space-sm;
}

.preview-item {
  display: flex;
  gap: $wolf-space-sm;
  margin-bottom: $wolf-space-xs;
}

.preview-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  min-width: 60px;
}

.preview-value {
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  font-weight: $wolf-font-weight-medium;
}

.preview-params {
  margin-top: $wolf-space-sm;
}

.params-json {
  font-size: $wolf-font-size-caption;
  background: $wolf-bg-card;
  padding: $wolf-space-sm;
  border-radius: $wolf-radius-sm;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
}

.stage-preview-followup {
  padding: $wolf-space-sm 0;

  .thinking-section {
    margin-bottom: $wolf-space-md;

    .thinking-header {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      margin-bottom: $wolf-space-sm;
    }

    .thinking-content {
      padding: $wolf-space-md;
      background: $wolf-bg-hover;
      border-radius: $wolf-radius-sm;
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      white-space: pre-wrap;
      max-height: 150px;
      overflow-y: auto;
    }
  }

  .followup-preview {
    padding: $wolf-space-md;
    background: $wolf-success-bg;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;

    .preview-header {
      font-size: $wolf-font-size-body;
      font-weight: $wolf-font-weight-semibold;
      color: $wolf-success-text;
      margin-bottom: $wolf-space-sm;
    }

    .preview-item {
      display: flex;
      gap: $wolf-space-sm;
      margin-bottom: $wolf-space-xs;

      .preview-label {
        font-size: $wolf-font-size-caption;
        color: $wolf-text-tertiary;
        min-width: 80px;
      }

      .preview-value {
        font-size: $wolf-font-size-body;
        color: $wolf-text-primary;
        font-weight: $wolf-font-weight-medium;
      }
    }
  }
}

// ========== 多工具依次确认样式 ==========

.stage-preview-multi,
.stage-preview-multi-form {
  .tool-progress {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    margin-bottom: $wolf-space-md;

    .progress-label {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      min-width: 60px;
    }

    .el-progress {
      flex: 1;
    }
  }

  .executed-results {
    padding: $wolf-space-md;
    background: $wolf-bg-hover;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;

    .results-header {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      margin-bottom: $wolf-space-sm;
    }

    .result-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: $wolf-space-xs 0;

      .result-tool {
        font-size: $wolf-font-size-caption;
        color: $wolf-text-primary;
      }
    }
  }

  .action-preview {
    .preview-header {
      color: $wolf-primary;
    }
  }
}

// ========== ReAct 进度样式 ==========

.stage-react-progress {
  .loading-indicator {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    justify-content: center;
    padding: $wolf-space-lg;

    .el-icon {
      font-size: 20px;
      color: $wolf-primary;
    }

    span {
      font-size: $wolf-font-size-body;
      color: $wolf-text-tertiary;
    }
  }
}

// ========== 上下文汇总展示样式 ==========

.context-summary-section {
  margin-bottom: $wolf-space-md;
  border: 1px solid $wolf-border-color;
  border-radius: $wolf-radius-md;

  .context-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-sm $wolf-space-md;
    background: $wolf-primary-light;
    cursor: pointer;
    transition: background 0.2s;

    &:hover {
      background: rgba($wolf-primary, 0.15);
    }

    .el-icon {
      font-size: 14px;
      color: $wolf-primary;
    }

    span {
      font-size: $wolf-font-size-caption;
      color: $wolf-primary;
      flex: 1;
    }

    .rotate {
      transform: rotate(180deg);
    }
  }

  .context-detail {
    padding: $wolf-space-md;
    background: $wolf-bg-card;

    .detail-block {
      margin-bottom: $wolf-space-sm;

      &:last-child {
        margin-bottom: 0;
      }

      .block-title {
        font-size: $wolf-font-size-caption;
        color: $wolf-text-secondary;
        font-weight: $wolf-font-weight-medium;
        margin-bottom: $wolf-space-xs;
      }

      .block-content {
        .info-item,
        .entity-item,
        .activity-item {
          display: flex;
          gap: $wolf-space-xs;
          padding: $wolf-space-xs 0;
          font-size: $wolf-font-size-caption;

          .info-label,
          .entity-name,
          .activity-content {
            color: $wolf-text-primary;
          }

          .info-value,
          .entity-status,
          .activity-method {
            color: $wolf-text-tertiary;
          }
        }
      }
    }
  }

  // ==================== Phase G: Sidebar 样式（系统规范优化版）====================

  // Drawer 容器样式覆盖
  :deep(.el-drawer) {
    background: $wolf-bg-page;
    border-left: 1px solid $wolf-border-divider;
  }

  :deep(.el-drawer__header) {
    padding: $wolf-space-md $wolf-space-lg;
    margin-bottom: 0;
    border-bottom: 1px solid $wolf-border-divider;
    background: $wolf-bg-card;
  }

  :deep(.el-drawer__body) {
    padding: 0;
    background: $wolf-bg-page;
    overflow-y: auto;
  }

  // Sidebar Header
  .sidebar-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    height: 48px;

    .header-icon {
      font-size: 18px;
      color: $wolf-primary;
    }

    .sidebar-title {
      font-size: $wolf-font-size-title;
      font-weight: $wolf-font-weight-semibold;
      color: $wolf-text-primary;
    }
  }

  // Sidebar Content
  .sidebar-content {
    padding: $wolf-space-md;
    display: flex;
    flex-direction: column;
    gap: $wolf-card-gap;  // 卡片间距统一 16px
  }

  // 实体信息卡片（单行）
  .sidebar-entity-info {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-sm $wolf-space-md;
    background: $wolf-bg-card;
    border-radius: $wolf-radius-lg;  // 12px 圆角
    border: 1px solid $wolf-border-light;
    box-shadow: $wolf-shadow-card;  // 轻阴影

    .entity-name {
      flex: 1;
      font-size: $wolf-font-size-body;
      font-weight: $wolf-font-weight-medium;
      color: $wolf-text-primary;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .el-tag {
      margin-left: $wolf-space-xs;
    }
  }

  // 执行摘要区：分组状态卡片
  .sidebar-summary-section {
    display: flex;
    flex-direction: column;
    gap: $wolf-card-gap;  // 16px 间距
  }

  // 执行过程日志
  .sidebar-execution-log {
    margin-top: $wolf-space-md;
    padding: $wolf-space-sm;
  }

  // 加载状态卡片
  .sidebar-loading-card {
    padding: $wolf-space-xs 0;
  }

  // ReAct 进度展示区
  .sidebar-progress-section {
    padding: $wolf-space-sm $wolf-space-md;
    background: $wolf-bg-card;
    border-radius: $wolf-radius-md;
    border: 1px solid $wolf-border-light;

    .progress-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: $wolf-space-sm;

      .progress-title {
        font-size: $wolf-font-size-caption;
        font-weight: $wolf-font-weight-medium;
        color: $wolf-text-secondary;
      }

      .progress-round {
        font-size: $wolf-font-size-caption;
        color: $wolf-primary;
      }
    }

    .progress-steps {
      .progress-step {
        display: flex;
        align-items: center;
        gap: $wolf-space-sm;
        padding: $wolf-space-xs 0;

        .step-icon {
          font-size: 14px;
        }

        .step-content {
          display: flex;
          flex-direction: column;
          gap: 2px;

          .step-name {
            font-size: $wolf-font-size-caption;
            color: $wolf-text-primary;
          }

          .step-status {
            font-size: $wolf-font-size-auxiliary;
            color: $wolf-text-tertiary;
          }
        }

        &.completed {
          .step-icon {
            color: $wolf-success;
          }

          .step-status {
            color: $wolf-success;
          }
        }

        &.current {
          .step-icon {
            color: $wolf-primary;
          }

          .step-name {
            color: $wolf-primary;
            font-weight: $wolf-font-weight-medium;
          }
        }
      }
    }
  }

  // 输入区
  .sidebar-input-section {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-sm;  // 关联元素间距（规范：textarea 与 button 属于关联元素）

    .input-tip {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
    }

    // 快捷指令提示
    .quick-commands {
      display: flex;
      flex-wrap: wrap;
      gap: $wolf-space-xs;
      margin-bottom: $wolf-space-sm;
      padding: $wolf-space-sm;
      background: $wolf-bg-hover;
      border-radius: $wolf-radius-md;  // 8px 圆角

      .el-button {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 4px 8px;
        font-size: $wolf-font-size-caption;

        .cmd-text {
          color: $wolf-primary;
          font-weight: $wolf-font-weight-medium;
        }

        .cmd-desc {
          color: $wolf-text-tertiary;
        }
      }
    }

    .el-input {
      :deep(.el-textarea__inner) {
        background: $wolf-input-bg;  // 使用输入框规范背景
        border: none;  // 无边框（系统规范）
        border-radius: $wolf-radius-md;
        padding: $wolf-space-sm $wolf-space-md;
        font-size: $wolf-font-size-body;
        color: $wolf-text-secondary;
        resize: none;
        min-height: 64px;

        &:hover {
          background: $wolf-input-bg-hover;
        }

        &:focus {
          background: $wolf-input-bg-active;
        }

        &::placeholder {
          color: $wolf-text-placeholder;
        }
      }
    }

    .input-actions-inline {
      display: flex;
      justify-content: flex-end;
      gap: $wolf-space-sm;

      .el-button {
        display: flex;
        align-items: center;
        gap: 4px;
      }
    }
  }

  // Inline Pill 区域
  .sidebar-pill-section {
    padding: $wolf-space-xs 0;
  }

  // Workflow Mini-map 区域
  .sidebar-minimap-section {
    padding: $wolf-space-xs 0;
  }

  // AI 回复展示区
  .sidebar-reply-section {
    .reply-bubble {
      display: flex;
      align-items: flex-start;
      gap: $wolf-space-sm;
      padding: $wolf-space-md;
      background: $wolf-bg-card;
      border-radius: $wolf-radius-lg;  // 12px 圆角
      border: 1px solid $wolf-border-light;
      box-shadow: $wolf-shadow-card;  // 轻阴影

      .reply-icon {
        font-size: 16px;  // 缩小图标
        color: $wolf-primary;
      }

      .reply-text {
        flex: 1;
        font-size: $wolf-font-size-body;
        color: $wolf-text-primary;
        line-height: $wolf-line-height-body;

        // Markdown 渲染样式
        strong {
          font-weight: $wolf-font-weight-semibold;
          color: $wolf-primary;
        }

        .md-list {
          margin: 8px 0;
          padding-left: 20px;
          list-style-type: disc;

          li {
            margin: 4px 0;
            color: $wolf-text-primary;
          }
        }

        // Markdown 表格样式
        .md-table {
          width: 100%;
          margin: 12px 0;
          border-collapse: collapse;
          border: 1px solid $wolf-border-color;
          border-radius: $wolf-radius-sm;

          th {
            padding: 8px 12px;
            background: $wolf-bg-hover;
            font-size: $wolf-font-size-caption;
            font-weight: $wolf-font-weight-medium;
            color: $wolf-text-secondary;
            text-align: left;
            border-bottom: 1px solid $wolf-border-color;
          }

          td {
            padding: 8px 12px;
            font-size: $wolf-font-size-caption;
            color: $wolf-text-primary;
            border-bottom: 1px solid $wolf-border-light;
          }

          tr:last-child td {
            border-bottom: none;
          }
        }
      }
    }
  }

  // 等待用户回复区（按钮选项）
  .sidebar-options-section {
    .options-buttons {
      display: flex;
      flex-wrap: wrap;
      gap: $wolf-space-sm;
      padding: $wolf-space-xs 0;

      .el-button {
        flex: 1;
        min-width: 80px;
      }
    }
  }

  // 缺失字段表单填充区
  .sidebar-missing-fields-section {
    padding: $wolf-space-md;
    background: $wolf-bg-card;  // 白色背景（更清爽）
    border-radius: $wolf-radius-lg;  // 12px 圆角
    border: 1px solid $wolf-border-default;
    box-shadow: $wolf-shadow-card;

    // 上下文显示区（显示 AI 的回复，支持 Markdown）
    .missing-fields-context {
      margin-bottom: $wolf-space-md;

      .context-bubble {
        display: flex;
        align-items: flex-start;
        gap: $wolf-space-sm;
        padding: $wolf-space-sm $wolf-space-md;
        background: $wolf-bg-hover;
        border-radius: $wolf-radius-md;

        .context-icon {
          font-size: 16px;
          color: $wolf-primary;
        }

        .context-text {
          flex: 1;
          font-size: $wolf-font-size-body;
          color: $wolf-text-primary;
          line-height: $wolf-line-height-body;

          // Markdown 渲染样式
          strong {
            font-weight: $wolf-font-weight-semibold;
            color: $wolf-primary;
          }

          .md-list {
            margin: 8px 0;
            padding-left: 20px;
            list-style-type: disc;

            li {
              margin: 4px 0;
              color: $wolf-text-primary;
            }
          }

          // Markdown 表格样式
          .md-table {
            width: 100%;
            margin: 12px 0;
            border-collapse: collapse;
            border: 1px solid $wolf-border-color;
            border-radius: $wolf-radius-sm;

            th {
              padding: 8px 12px;
              background: $wolf-bg-hover;
              font-size: $wolf-font-size-caption;
              font-weight: $wolf-font-weight-medium;
              color: $wolf-text-secondary;
              text-align: left;
              border-bottom: 1px solid $wolf-border-color;
            }

            td {
              padding: 8px 12px;
              font-size: $wolf-font-size-caption;
              color: $wolf-text-primary;
              border-bottom: 1px solid $wolf-border-light;
            }

            tr:last-child td {
              border-bottom: none;
            }
          }
        }
      }
    }

    .missing-fields-header {
      display: flex;
      align-items: center;
      gap: $wolf-space-sm;
      margin-bottom: $wolf-space-md;
      font-size: $wolf-font-size-body;
      font-weight: $wolf-font-weight-medium;
      color: $wolf-warning-text;

      .el-icon {
        font-size: 18px;
      }
    }

    .missing-fields-form {
      margin-bottom: $wolf-space-md;

      // 默认样式
      :deep(.el-form-item) {
        margin-bottom: $wolf-form-item-gap;  // 16px

        .el-form-item__label {
          font-size: $wolf-font-size-caption;
          color: $wolf-text-secondary;
          font-weight: $wolf-font-weight-medium;
          padding-bottom: $wolf-space-xs;
        }

        // 输入框样式（系统规范）
        .el-input__wrapper,
        .el-input-number__wrapper {
          background: $wolf-input-bg;
          border: none;
          border-radius: $wolf-input-radius;
          height: $wolf-input-height;
          box-shadow: none;

          &:hover {
            background: $wolf-input-bg-hover;
          }

          &:focus {
            background: $wolf-input-bg-active;
          }
        }

        // 下拉选择框样式
        .el-select__wrapper {
          background: $wolf-input-bg;
          border: none;
          border-radius: $wolf-select-radius;
          height: $wolf-select-height;
          box-shadow: none;

          &:hover {
            background: $wolf-input-bg-hover;
          }
        }
      }

      // 日期选择器样式
      :deep(.el-date-editor) {
        width: 100%;
        height: $wolf-input-height;
      }

      // 数字输入样式
      :deep(.el-input-number) {
        width: 100%;
        height: $wolf-input-height;
      }

      // 并排显示样式（两个字段时并排，三个或更多时换行）
      &.inline-form {
        display: flex;
        flex-wrap: wrap;
        gap: $wolf-space-md;

        :deep(.el-form-item) {
          flex: 1;
          min-width: 140px;
          margin-bottom: 0;
          margin-right: $wolf-space-md;

          &:last-child {
            margin-right: 0;
          }
        }
      }
    }

    .missing-fields-actions {
      display: flex;
      justify-content: flex-end;
      gap: $wolf-space-sm;
    }
  }

  // 加载状态
  .sidebar-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-lg;
    font-size: $wolf-font-size-auxiliary;
    color: $wolf-text-tertiary;

    .el-icon {
      font-size: 16px;
      color: $wolf-primary;
    }
  }

  // 结果状态（精简版）
  .sidebar-result {
    padding: $wolf-space-md;
    background: $wolf-bg-card;
    border-radius: $wolf-radius-lg;
    box-shadow: $wolf-shadow-card;

    .result-summary {
      .result-header {
        display: flex;
        align-items: center;
        gap: $wolf-space-sm;
        margin-bottom: $wolf-space-sm;

        .result-icon {
          font-size: 18px;

          &.success {
            color: $wolf-success;
          }

          &.error {
            color: $wolf-danger;
          }
        }

        .result-title {
          font-size: $wolf-font-size-body;
          font-weight: $wolf-font-weight-medium;
          color: $wolf-text-primary;
        }
      }

      .result-content {
        font-size: $wolf-font-size-body;
        color: $wolf-text-primary;
        line-height: 1.6;

        // Markdown 样式
        strong {
          font-weight: $wolf-font-weight-semibold;
          color: $wolf-primary;
        }

        .md-list {
          margin: 8px 0;
          padding-left: 20px;
          list-style-type: disc;

          li {
            margin: 4px 0;
            color: $wolf-text-primary;
          }
        }

        // Markdown 表格样式
        .md-table {
          width: 100%;
          margin: 12px 0;
          border-collapse: collapse;
          border: 1px solid $wolf-border-color;
          border-radius: $wolf-radius-sm;

          th {
            padding: 8px 12px;
            background: $wolf-bg-hover;
            font-size: $wolf-font-size-caption;
            font-weight: $wolf-font-weight-medium;
            color: $wolf-text-secondary;
            text-align: left;
            border-bottom: 1px solid $wolf-border-color;
          }

          td {
            padding: 8px 12px;
            font-size: $wolf-font-size-caption;
            color: $wolf-text-primary;
            border-bottom: 1px solid $wolf-border-light;
          }

          tr:last-child td {
            border-bottom: none;
          }
        }
      }

      .result-actions {
        margin-top: $wolf-space-md;
        padding-top: $wolf-space-md;
        border-top: 1px solid $wolf-border-light;
      }
    }
  }

  // 滚动条样式
  :deep(.el-drawer__body)::-webkit-scrollbar {
    width: 6px;
  }

  :deep(.el-drawer__body)::-webkit-scrollbar-track {
    background: $wolf-bg-elevated;
  }

  :deep(.el-drawer__body)::-webkit-scrollbar-thumb {
    background: $wolf-border-default;
    border-radius: $wolf-radius-sm;

    &:hover {
      background: $wolf-border-hover;
    }
  }

  // ========== Phase 4: Sidebar 响应式样式 ==========

  // 中屏（768px-1199px）：Sidebar 稍窄
  :deep(.el-drawer) {
    @media (max-width: 1199px) and (min-width: 768px) {
      width: 360px !important;
    }
  }

  // 小屏（<768px）：Sidebar 全宽，从底部弹出
  :deep(.el-drawer) {
    @media (max-width: 767px) {
      width: 100% !important;
      max-height: 70vh;
      border-radius: $wolf-radius-xl $wolf-radius-xl 0 0;
      border-left: none;
      border-top: 1px solid $wolf-border-divider;
    }
  }

  :deep(.el-drawer__header) {
    @media (max-width: 767px) {
      padding: $wolf-space-sm $wolf-space-md;
      border-radius: $wolf-radius-xl $wolf-radius-xl 0 0;
    }
  }

  :deep(.el-drawer__body) {
    @media (max-width: 767px) {
      max-height: calc(70vh - 48px);
      overflow-y: auto;
    }
  }

  .sidebar-content {
    @media (max-width: 767px) {
      padding: $wolf-space-sm;
      gap: $wolf-space-sm; // 小屏间距减小（8px）
    }
  }

  .sidebar-entity-info {
    @media (max-width: 767px) {
      padding: $wolf-space-xs $wolf-space-sm;
      border-radius: $wolf-radius-md;
    }
  }

  .sidebar-input-section {
    @media (max-width: 767px) {
      .el-input {
        :deep(.el-textarea__inner) {
          min-height: 48px;
          font-size: $wolf-font-size-caption;
        }
      }

      .input-actions-inline {
        .el-button {
          padding: $wolf-space-xs $wolf-space-sm;
        }
      }
    }
  }

  .sidebar-reply-section {
    @media (max-width: 767px) {
      .reply-bubble {
        padding: $wolf-space-sm;
        border-radius: $wolf-radius-md;

        .reply-text {
          font-size: $wolf-font-size-caption;
        }
      }
    }
  }

  .sidebar-missing-fields-section {
    @media (max-width: 767px) {
      padding: $wolf-space-sm;
      border-radius: $wolf-radius-md;

      .missing-fields-form {
        :deep(.el-form-item) {
          margin-bottom: $wolf-space-sm;
        }
      }
    }
  }

  .sidebar-result {
    @media (max-width: 767px) {
      padding: $wolf-space-sm;
      border-radius: $wolf-radius-md;

      .result-summary {
        .result-header {
          .result-title {
            font-size: $wolf-font-size-caption;
          }
        }

        .result-content {
          font-size: $wolf-font-size-caption;
        }
      }
    }
  }
}

// ========== Phase 4: 主输入框容器响应式 ==========

@media (max-width: 767px) {
  .main-input-container {
    padding: $wolf-space-md;
  }
}

@media (min-width: 1200px) {
  .main-input-container {
    padding: $wolf-space-lg $wolf-space-8;  // 24px 32px（使用已定义变量）
  }
}
</style>