/**
 * 发票文件上传 API
 *
 * Task 5: 发票审批优化 - 前端文件上传组件
 * 对接后端 `app/api/invoice_approvals.py`:
 *   POST /v1/approvals/INVOICE/{invoice_id}/approve-with-file
 *   GET  /invoice-applications/{invoice_id}/file
 *
 * 设计要点：
 * - 复用 `@/utils/request` 实例（baseURL 由实例统一注入，禁止硬编码）
 * - TypeScript 严格模式：禁止 any / as any / 非空断言
 * - FormData 文件上传，Content-Type: multipart/form-data
 * - Zod Schema 校验响应（crmwolf/require-zod-schema）
 */

