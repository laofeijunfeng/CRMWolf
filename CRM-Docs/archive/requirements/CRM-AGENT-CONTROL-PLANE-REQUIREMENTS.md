---
status: completed
created: 2026-06-10
updated: 2026-06-10
related_plan: -
related_pr: -
---

# 需求文档：CRM 智能流程推进 Agent 控制系统 (Control Plane)

| 文档版本 | V 3.0 |
| :--- | :--- |
| **项目名称** | CRM 智能流程推进 Agent (Control Plane) |
| **当前状态** | 需求定义 |
| **关键词** | Control Plane, Workflow Engine, State Management, Guardrails |
| **更新日期** | 2026-06-10 |

---

## 一、需求背景 (Context & Problem Statement)

### 1.1 现状
基于 V2.0 的需求规划，项目已进入执行阶段。目前，ReAct 模式的 Agent 基础框架、四层架构设计（意图识别、工作流编排、执行引擎、可观测性）及核心业务原则已确立。团队正着手构建工作流引擎（Workflow Engine）与会话状态管理（Session State）模块。

### 1.2 核心挑战
随着代码实现的深入，我们需要解决从"架构设计"到"工程落地"之间的控制逻辑问题。目前的挑战不在于具体的业务流转，而在于**如何构建一个稳健的控制系统（Control Plane）**，确保 AI 的灵活性被限制在既定的工程化轨道内运行。

具体而言，我们需要解决以下三个核心问题：
1.  **流程控制权归属**：如何确保在 AI 意图识别（Layer 1）与工作流执行（Layer 2/3）之间，存在一个不可逾越的"硬边界"，防止 AI 越权操作。
2.  **状态一致性与生命周期**：如何管理跨多轮对话的 Session State，确保在网络波动、用户长时间离开或系统重启时，流程状态不丢失、不混乱。
3.  **异常流量治理**：当 AI 出现幻觉、连续推理错误或遭遇恶意输入时，系统如何通过熔断与降级机制自我保护，避免污染 CRM 核心数据。

### 1.3 机会
通过在 V2.0 的基础上定义明确的控制面需求，我们可以将系统的**确定性**提升至最高优先级。这不仅能够降低后续调试的复杂度，还能为未来的灰度发布和 A/B 测试提供标准化的基础设施支持。

---

## 二、核心原则 (Core Principles)

### 2.1 控制反转原则 (Inversion of Control for AI)
**AI 是插件，不是主程序。**

*   **Driver 模式**：系统必须由 Workflow Engine（代码）驱动，AI 仅作为意图识别的"插件"被调用。严禁 AI 自主决定调用工具的顺序或循环。
*   **单向数据流**：数据流必须严格遵循 `Input -> AI (Recognize) -> Engine (Decide) -> Executor (Act)`。AI 的输出必须经过 Engine 的校验才能到达 Executor。
*   **Fail-Safe 默认**：任何未预见的 AI 输出或解析失败，默认行为必须是"暂停并等待人工介入"，而非猜测或跳过。

### 2.2 状态外置与可恢复性原则 (Externalized State & Resumability)
**不依赖 AI 的记忆，不信任客户端的持久化。**

*   **Source of Truth**：Session State 必须存储在服务端（如 Redis），作为流程推进的唯一事实来源（Single Source of Truth）。
*   **幂等恢复**：系统设计必须支持从任意断点恢复。当用户重新打开页面或网络重连时，系统应能基于 Session State 重建当前步骤，而不是重新开始。
*   **TTL 与清理**：定义明确的 Session 生命周期（TTL）。对于已完成、已取消或超时（如超过 24 小时未操作）的会话，系统必须自动回收资源并记录归档。

### 2.3 防御性执行原则 (Defensive Execution)
**执行即风险，必须对每一步进行防御性编程。**

*   **Pre-flight 校验**：在执行任何 CRUD 操作前，Executor 必须再次校验业务不变式（Invariants），即使 Workflow Engine 已经校验过。这是最后一道防线。
*   **结构化异常处理**：针对 AI 侧的异常（如 Hallucination、Low Confidence）和系统侧的异常（如 DB Timeout、Lock Conflict），必须定义不同的处理策略（Retry vs. Fallback vs. Human-in-the-loop）。
*   **资源隔离**：Agent 的执行线程应与核心 CRM 业务线程池隔离，防止 Agent 的高频调用或死循环拖垮整个 CRM 系统。

### 2.4 可观测性即需求原则 (Observability as a Requirement)
**看不见的流程等于不存在的流程。**

*   **全链路 TraceId**：每一个用户请求必须生成唯一的 TraceId，串联起 Nginx -> App -> AI Service -> Workflow Engine -> Database 的完整路径。
*   **Decision Audit**：不仅仅是记录"谁改了数据"，更要记录"AI 为什么建议改数据"。必须留存 AI 的 Reasoning Process（Thought）和 Evidence。
*   **实时仪表盘**：系统需具备实时监控能力，重点关注"AI 置信度分布"、"Workflow 失败率"和"人工接管率"，以便快速发现模型漂移。

---

## 三、范围 (Scope)

### 3.1 功能范围 (In Scope)
*   **Workflow Engine 核心逻辑**：状态机的实现、步骤流转控制、条件分支判断。
*   **Session State 管理机制**：Redis 存储结构设计、读写接口、过期策略。
*   **Guardrails (护栏) 实现**：置信度拦截、必填字段校验、状态流转合法性检查。
*   **SSE 事件流控制**：后端向前端推送进度、等待确认、错误回滚的标准化协议。

### 3.2 非功能范围 (Out of Scope)
*   **不涉及具体业务字段**：如合同具体有哪些字段、商机金额的计算逻辑。
*   **不涉及 Prompt Engineering**：具体的 System Prompt 措辞优化、Few-shot 示例编写。
*   **不涉及前端 UI 实现**：具体的按钮样式、弹窗布局、颜色搭配。

---

## 四、成功指标 (Success Metrics)

1.  **控制面稳定性**：Workflow Engine 在 1000 次并发测试中，状态流转错误率为 0%。
2.  **恢复成功率**：模拟进程重启或网络闪断后，会话恢复成功率需达到 100%。
3.  **拦截有效率**：针对构造的恶意或模糊输入，Guardrails 的正确拦截率需达到 99% 以上。
4.  **资源隔离性**：Agent 模块在满载压力下，CRM 核心业务响应时间延迟增加不超过 5%。