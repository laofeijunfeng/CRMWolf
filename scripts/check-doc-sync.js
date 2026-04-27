/**
 * 文档同步检查脚本
 *
 * @description 检查代码变更是否同步更新了对应文档
 */

const fs = require('fs')
const path = require('path')

// 变更映射规则
const SYNC_RULES = [
  {
    codePattern: 'CRM-Client/src/api/*.ts',
    docPattern: 'CRM-Docs/05-API接口.md',
    message: 'API 文件变更但 API 文档未更新'
  },
  {
    codePattern: 'CRM-Client/src/schemas/*.ts',
    docPattern: 'CRM-Client/docs/TYPESCRIPT.md',
    message: 'Schema 文件变更但 TYPESCRIPT.md 未更新'
  },
  {
    codePattern: 'CRM-Client/src/stores/*.ts',
    docPattern: 'CRM-Client/docs/STATE-MANAGEMENT.md',
    message: 'Store 文件变更但 STATE-MANAGEMENT.md 未更新'
  },
  {
    codePattern: 'CRM-Client/src/components/*.vue',
    docPattern: 'CRM-Client/docs/COMPONENTS.md',
    message: '组件变更但 COMPONENTS.md 未更新'
  },
  {
    codePattern: 'CRM-Server/app/schemas/*.py',
    docPattern: 'CRM-Client/docs/TYPESCRIPT.md',
    message: '后端 Schema 变更但前端 TYPESCRIPT.md 未更新'
  },
  {
    codePattern: 'CRM-Server/app/api/*.py',
    docPattern: 'CRM-Docs/05-API接口.md',
    message: '后端 API 变更但 API 文档未更新'
  }
]

/**
 * 检查文件是否匹配模式
 */
function matchesPattern(filePath, pattern) {
  const baseDir = '/Users/eddie/Code/CRMWolf/'
  const relativePath = filePath.replace(baseDir, '')

  // 转换 glob 模式为正则
  const regexPattern = pattern
    .replace(/\*/g, '.*')
    .replace(/\//g, '\\/')

  return new RegExp(regexPattern).test(relativePath)
}

/**
 * 获取变更文件列表（从 git diff）
 */
function getChangedFiles() {
  try {
    // 模拟 git diff 输出
    const execSync = require('child_process').execSync
    const output = execSync('git diff HEAD~1 --name-only', { encoding: 'utf-8' })
    return output.trim().split('\n').filter(f => f.length > 0)
  } catch (e) {
    // 如果没有 git，返回空数组
    return []
  }
}

/**
 * 执行同步检查
 */
function checkDocSync() {
  const changedFiles = getChangedFiles()
  const warnings = []

  for (const rule of SYNC_RULES) {
    const codeChanged = changedFiles.some(f => matchesPattern(f, rule.codePattern))
    const docChanged = changedFiles.some(f => matchesPattern(f, rule.docPattern))

    if (codeChanged && !docChanged) {
      warnings.push({
        rule: rule.codePattern,
        message: rule.message
      })
    }
  }

  return warnings
}

/**
 * 生成报告
 */
function generateReport(warnings) {
  console.log('## 文档同步检查报告\n')

  if (warnings.length === 0) {
    console.log('✅ 所有代码变更已同步更新文档\n')
  } else {
    console.log('⚠️ 以下变更未同步更新文档：\n')
    for (const w of warnings) {
      console.log(`- ${w.rule}: ${w.message}`)
    }
  }

  console.log('\n---')
  console.log(`检查时间: ${new Date().toISOString()}`)
}

// 主执行流程
const warnings = checkDocSync()
generateReport(warnings)

// 返回状态码
process.exit(warnings.length > 0 ? 1 : 0)