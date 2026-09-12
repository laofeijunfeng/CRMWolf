<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { VueFlow, useVueFlow, type Connection, type NodeMouseEvent } from '@vue-flow/core'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import workflowApi, { type WorkflowDetail, type WorkflowDsl } from '@/api/workflow'
import { validateWorkflow, type WorkflowGraph, type WorkflowValidationIssue } from './workflowValidation'
import {
  insertNodeIntoGraph,
  type WorkflowEditorEdge,
  type WorkflowEditorNode,
  type WorkflowInsertContext,
} from './workflowGraphEditing'
import { WORKFLOW_NODE_REGISTRY, WORKFLOW_NODE_TYPES, type WorkflowNodeType } from './workflowNodeRegistry'
import WorkflowNode from './WorkflowNode.vue'
import WorkflowNodePalette from './WorkflowNodePalette.vue'

const WORKFLOW_FLOW_ID = 'workflow-editor-flow'

type WorkflowNodeData = WorkflowEditorNode['data']

function nodeData(config: Record<string, unknown>, hasError = false, errorMessage = ''): WorkflowNodeData {
  return { config, hasError, errorMessage }
}

const props = defineProps<{ workflowId: number | null }>()
const emit = defineEmits<{ saved: [workflow: WorkflowDetail]; cancelled: [] }>()
const nodes = ref<WorkflowEditorNode[]>([])
const edges = ref<WorkflowEditorEdge[]>([])
const workflowName = ref('')
const description = ref('')
const loadedLastModified = ref<string | null>(null)
const selectedNodeId = ref<string | null>(null)
const issues = ref<WorkflowValidationIssue[]>([])
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const nodeTypes = Object.fromEntries(WORKFLOW_NODE_TYPES.map(type => [type, WorkflowNode]))
const triggerUsed = computed(() => nodes.value.some(node => WORKFLOW_NODE_REGISTRY[node.type as WorkflowNodeType]?.isTrigger === true))
const selectedNode = computed(() => nodes.value.find(node => node.id === selectedNodeId.value) ?? null)
const selectedDefinition = computed(() => selectedNode.value === null ? undefined : WORKFLOW_NODE_REGISTRY[selectedNode.value.type as WorkflowNodeType])
const validationSummary = computed(() => issues.value.length === 0 ? '校验通过' : `有 ${issues.value.length} 个问题`)
const { screenToFlowCoordinate } = useVueFlow(WORKFLOW_FLOW_ID)

function freshId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function isKnownType(type: string): type is WorkflowNodeType {
  return type in WORKFLOW_NODE_REGISTRY
}

function graph(): WorkflowGraph {
  return {
    schema_version: 1,
    nodes: nodes.value.map(node => ({
      id: node.id,
      type: node.type,
      position: node.position,
      config: node.data.config,
    })),
    edges: edges.value,
  }
}

function applyIssues(nextIssues: WorkflowValidationIssue[]): void {
  issues.value = nextIssues
  const byNode = new Map<string, string>()
  for (const issue of nextIssues) {
    if (issue.nodeId !== undefined && !byNode.has(issue.nodeId)) {
      byNode.set(issue.nodeId, issue.message)
    }
  }
  nodes.value = nodes.value.map(node => ({
    ...node,
    data: nodeData(node.data.config, byNode.has(node.id), byNode.get(node.id) ?? ''),
  }))
}

function addNode(
  type: WorkflowNodeType,
  position = { x: 120, y: 120 },
  context: WorkflowInsertContext = { kind: 'root' },
): void {
  const definition = WORKFLOW_NODE_REGISTRY[type]
  if (definition.isTrigger && triggerUsed.value) return
  const nextNode: WorkflowEditorNode = { id: freshId('node'), type, position, data: nodeData(definition.defaults()) }
  const result = insertNodeIntoGraph(nodes.value, edges.value, nextNode, context)
  if (result.nodes === nodes.value) return
  nodes.value = result.nodes
  edges.value = result.edges
  selectedNodeId.value = nextNode.id
  applyIssues([])
}

function addNodeWithAutomaticContext(type: WorkflowNodeType, position: { x: number; y: number }): void {
  const terminalNodes = nodes.value.filter(node => !edges.value.some(edge => edge.source === node.id))
  const soleTerminal = terminalNodes.length === 1 ? terminalNodes[0] : undefined
  const context: WorkflowInsertContext = soleTerminal !== undefined && !WORKFLOW_NODE_REGISTRY[type].isTrigger
    ? { kind: 'after-node', sourceNodeId: soleTerminal.id }
    : { kind: 'root' }
  addNode(type, position, context)
}

function addNodeFromPalette(type: WorkflowNodeType): void {
  addNodeWithAutomaticContext(type, { x: 120, y: 120 })
}
function selectNodeById(nodeId: string): void {
  selectedNodeId.value = nodeId
}

function selectNode(event: NodeMouseEvent): void {
  selectNodeById(event.node.id)
}

function updateSelectedConfig(patch: Record<string, unknown>): void {
  if (selectedNodeId.value === null) return
  nodes.value = nodes.value.map(node => node.id === selectedNodeId.value
    ? { ...node, data: nodeData({ ...node.data.config, ...patch }, node.data.hasError, node.data.errorMessage) }
    : node)
  applyIssues(validateWorkflow(graph(), workflowName.value))
}

function removeNode(nodeId: string): void {
  nodes.value = nodes.value.filter(node => node.id !== nodeId)
  edges.value = edges.value.filter(edge => edge.source !== nodeId && edge.target !== nodeId)
  if (selectedNodeId.value === nodeId) selectedNodeId.value = null
}

function onConnect(connection: Connection): void {
  if (connection.source === null || connection.target === null || connection.source === connection.target) return
  const target = nodes.value.find(node => node.id === connection.target)
  if (target === undefined || WORKFLOW_NODE_REGISTRY[target.type as WorkflowNodeType]?.isTrigger === true) return
  edges.value = [...edges.value, { id: freshId('edge'), source: connection.source, target: connection.target }]
  applyIssues(validateWorkflow(graph(), workflowName.value))
}

function onDrop(event: DragEvent): void {
  event.preventDefault()
  const type = event.dataTransfer?.getData('application/workflow-node') ?? ''
  if (isKnownType(type)) {
    addNodeWithAutomaticContext(type, screenToFlowCoordinate({ x: event.clientX, y: event.clientY }))
  }
}

function onDragOver(event: DragEvent): void {
  event.preventDefault()
}

function hydrate(detail: WorkflowDetail): void {
  workflowName.value = detail.name
  description.value = detail.description ?? ''
  loadedLastModified.value = detail.last_modified_time
  nodes.value = detail.dsl.nodes.map(node => ({
    id: node.id,
    type: node.type,
    position: { ...node.position },
    data: nodeData({ ...node.config }),
  }))
  edges.value = detail.dsl.edges.map(edge => ({ id: edge.id, source: edge.source, target: edge.target }))
  applyIssues([])
}

async function load(): Promise<void> {
  if (props.workflowId === null) return
  loading.value = true
  try {
    hydrate(await workflowApi.get(props.workflowId))
  } catch {
    errorMessage.value = '无法加载工作流，请稍后重试。'
  } finally {
    loading.value = false
  }
}

async function reload(): Promise<void> {
  errorMessage.value = ''
  await load()
}

function responseOf(error: unknown): unknown {
  if (typeof error !== 'object' || error === null) return undefined
  return Reflect.get(error, 'response')
}

function statusOf(error: unknown): number | undefined {
  const response = responseOf(error)
  const status = typeof response === 'object' && response !== null ? Reflect.get(response, 'status') : undefined
  return typeof status === 'number' ? status : undefined
}

function validationIssuesOf(error: unknown): WorkflowValidationIssue[] {
  const response = responseOf(error)
  const data = typeof response === 'object' && response !== null ? Reflect.get(response, 'data') : undefined
  const detail = typeof data === 'object' && data !== null ? Reflect.get(data, 'detail') : undefined
  const errors = typeof detail === 'object' && detail !== null ? Reflect.get(detail, 'errors') : undefined
  if (!Array.isArray(errors)) return []
  return errors
    .filter((message): message is string => typeof message === 'string')
    .map(message => {
      const nodeId = /^节点\s+(\S+)\s+/.exec(message)?.[1]
      return nodeId === undefined ? { message } : { nodeId, message }
    })
}

async function save(): Promise<void> {
  if (saving.value) return
  const nextIssues = validateWorkflow(graph(), workflowName.value)
  applyIssues(nextIssues)
  errorMessage.value = ''
  if (nextIssues.length > 0) return
  saving.value = true
  const dsl = graph() as WorkflowDsl
  try {
    const result = props.workflowId === null
      ? await workflowApi.create({ name: workflowName.value.trim(), description: description.value.trim() || null, dsl })
      : await workflowApi.update(props.workflowId, {
          name: workflowName.value.trim(),
          description: description.value.trim() || null,
          dsl,
          expected_last_modified_time: loadedLastModified.value ?? '',
        })
    emit('saved', result)
  } catch (error: unknown) {
    const status = statusOf(error)
    if (status === 422) {
      const backendIssues = validationIssuesOf(error)
      applyIssues(backendIssues)
      errorMessage.value = backendIssues.length > 0
        ? `工作流校验失败：${backendIssues.length} 个问题，请检查配置。`
        : '工作流校验失败，请检查配置。'
    } else {
      errorMessage.value = status === 409 ? '工作流已被修改，请刷新后重试' : '保存工作流失败，请稍后重试。'
    }
  } finally {
    saving.value = false
  }
}

function cancel(): void {
  emit('cancelled')
}

watch(() => props.workflowId, () => { void load() })
onMounted(() => { void load() })

defineExpose({ addNode, save, onConnect, removeNode, updateSelectedConfig, nodes, edges, reload })
</script>

<template>
  <div class="workflow-editor flex h-full min-h-[560px] flex-col" data-testid="workflow-editor">
    <header class="flex items-center gap-3 border-b p-3">
      <Input v-model="workflowName" data-testid="workflow-name" placeholder="工作流名称" />
      <span data-testid="validation-summary">{{ validationSummary }}</span>
      <span v-if="errorMessage" role="alert">{{ errorMessage }}</span>
      <div class="ml-auto flex gap-2">
        <Button
          v-if="errorMessage.includes('已被修改')"
          type="button"
          data-testid="reload-workflow"
          variant="outline"
          :disabled="loading"
          @click="reload"
        >
          重新加载
        </Button>
        <Button type="button" variant="outline" @click="cancel">取消</Button>
        <Button type="button" data-testid="save-workflow" :disabled="saving" @click="save">保存</Button>
      </div>
    </header>
    <div class="grid min-h-0 flex-1 grid-cols-[220px_1fr_320px]">
      <WorkflowNodePalette :trigger-used="triggerUsed" @add="addNodeFromPalette" />
      <div class="min-h-0" @drop="onDrop" @dragover="onDragOver">
        <VueFlow
          :id="WORKFLOW_FLOW_ID"
          v-model:nodes="nodes"
          v-model:edges="edges"
          :node-types="nodeTypes"
          @connect="onConnect"
          @node-click="selectNode"
        >
          <Background />
          <Controls />
        </VueFlow>
        <div class="sr-only">
          <div v-for="node in nodes" :key="node.id" :data-testid="`workflow-node-${node.type}`" @click="selectNodeById(node.id)">
            {{ WORKFLOW_NODE_REGISTRY[node.type as WorkflowNodeType]?.summary(node.data.config) }}
          </div>
        </div>
      </div>
      <aside class="border-l p-4" data-testid="workflow-config-panel">
        <template v-if="selectedNode && selectedDefinition">
          <component :is="selectedDefinition.component" :config="selectedNode.data.config" @update:config="updateSelectedConfig" />
          <Button type="button" variant="destructive" @click="removeNode(selectedNode.id)">删除节点</Button>
        </template>
        <p v-else>选择节点以配置</p>
      </aside>
    </div>
    <ul v-if="issues.length" data-testid="workflow-issues">
      <li v-for="issue in issues" :key="`${issue.nodeId ?? 'workflow'}-${issue.message}`">{{ issue.message }}</li>
    </ul>
  </div>
</template>
