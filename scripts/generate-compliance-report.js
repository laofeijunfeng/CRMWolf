/**
 * 合规报告生成脚本
 *
 * @description 生成 TypeScript 违规统计报告
 */

const fs = require('fs')
const path = require('path')
const { execSync } = require('child_process')

const SRC_DIR = '/Users/eddie/Code/CRMWolf/CRM-Client/src'

/**
 * 统计违规数量
 */
function countViolations(pattern, directory) {
  try {
    const output = execSync(
      `grep -r "${pattern}" ${directory} --include="*.ts" --include="*.vue" 2>/dev/null | wc -l`,
      { encoding: 'utf-8' }
    )
    return parseInt(output.trim(), 10)
  } catch (e) {
    return 0
  }
}

/**
 * 统计各文件违规数量
 */
function countByFile(pattern, directory) {
  try {
    const output = execSync(
      `grep -r "${pattern}" ${directory} --include="*.ts" --include="*.vue" 2>/dev/null`,
      { encoding: 'utf-8' }
    )
    const lines = output.trim().split('\n').filter(l => l.length > 0)

    const fileCounts = {}
    for (const line of lines) {
      const match = line.match(/^(.+):/)
      if (match) {
        const filePath = match[1].replace(directory, '')
        fileCounts[filePath] = (fileCounts[filePath] || 0) + 1
      }
    }

    return fileCounts
  } catch (e) {
    return {}
  }
}

/**
 * 生成报告
 */
function generateReport() {
  const anyCount = countViolations(': any', SRC_DIR)
  const asAnyCount = countViolations('as any', SRC_DIR)
  const tsIgnoreCount = countViolations('@ts-ignore', SRC_DIR)
  const nonNullCount = countViolations('!', SRC_DIR) // 需进一步过滤

  console.log('# 合规日报\n')
  console.log(`**生成时间**: ${new Date().toISOString()}\n\n`)

  console.log('## TypeScript 违规统计\n')
  console.log('| 类型 | 数量 | 状态 |')
  console.log('|------|------|------|')
  console.log(`| \\`: any\\` | ${anyCount} | 存量跟踪 |`)
  console.log(`| \\`as any\\` | ${asAnyCount} | 存量跟踪 |`)
  console.log(`| \\`@ts-ignore\\` | ${tsIgnoreCount} | 零容忍 |`)
  console.log(`| \\`!\\` 非空断言 | ${nonNullCount} | 存量跟踪 |`)

  console.log('\n## 高优先级文件\n')
  console.log('### : any 违规 TOP 5\n')
  const anyByFile = countByFile(': any', SRC_DIR)
  const topAnyFiles = Object.entries(anyByFile)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  if (topAnyFiles.length > 0) {
    console.log('| 文件 | 数量 |')
    console.log('|------|------|')
    for (const [file, count] of topAnyFiles) {
      console.log(`| ${file} | ${count} |`)
    }
  } else {
    console.log('无违规文件')
  }

  console.log('\n### as any 违规 TOP 5\n')
  const asAnyByFile = countByFile('as any', SRC_DIR)
  const topAsAnyFiles = Object.entries(asAnyByFile)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  if (topAsAnyFiles.length > 0) {
    console.log('| 文件 | 数量 |')
    console.log('|------|------|')
    for (const [file, count] of topAsAnyFiles) {
      console.log(`| ${file} | ${count} |`)
    }
  } else {
    console.log('无违规文件')
  }

  console.log('\n## 清理进度\n')
  console.log('| 阶段 | 目标 | 状态 |')
  console.log('|------|------|------|')
  console.log('| Week 5-6 | stores/ + api/ | 待开始 |')
  console.log('| Week 7-8 | components/ | 待开始 |')
  console.log('| Week 9-12 | views/ | 待开始 |')

  console.log('\n---')
  console.log('*此报告由 CI 自动生成*')

  // 返回总违规数
  return anyCount + asAnyCount + tsIgnoreCount
}

// 执行并输出
const totalViolations = generateReport()

// 如果新增文件有违规，返回错误码
const newFiles = execSync('git diff HEAD~1 --name-only --diff-filter=A 2>/dev/null', { encoding: 'utf-8' })
  .trim()
  .split('\n')
  .filter(f => f.length > 0 && (f.endsWith('.ts') || f.endsWith('.vue')))

let newViolations = 0
for (const file of newFiles) {
  if (fs.existsSync(file)) {
    const content = fs.readFileSync(file, 'utf-8')
    if (content.includes(': any') || content.includes('as any') || content.includes('@ts-ignore')) {
      newViolations++
    }
  }
}

if (newViolations > 0) {
  console.log('\n❌ 新增文件包含 TypeScript 违规！')
  process.exit(1)
} else {
  console.log('\n✅ 新增文件无 TypeScript 违规')
  process.exit(0)
}