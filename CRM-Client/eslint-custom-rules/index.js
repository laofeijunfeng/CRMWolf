/**
 * ESLint 自定义规则 - CRMWolf
 *
 * @description TypeScript 四禁令校验规则
 */

const noAnyType = {
  meta: {
    type: 'problem',
    docs: {
      description: '禁止使用 : any 类型注解',
      category: 'TypeScript Zero Compromise',
      recommended: 'error'
    },
    messages: {
      unexpectedAny: '使用 : any 类型注解违反 TypeScript 零妥协规范。请查阅 TYPESCRIPT.md 使用 Approved Types。'
    }
  },
  create(context) {
    return {
      TSAnyKeyword(node) {
        context.report({
          node,
          messageId: 'unexpectedAny'
        })
      }
    }
  }
}

const noAsAny = {
  meta: {
    type: 'problem',
    docs: {
      description: '禁止使用 as any 类型转换',
      category: 'TypeScript Zero Compromise',
      recommended: 'error'
    },
    messages: {
      unexpectedAsAny: '使用 as any 类型转换违反 TypeScript 零妥协规范。请使用 TYPESCRIPT.md Approved Types + Zod 校验。'
    }
  },
  create(context) {
    return {
      TSAsExpression(node) {
        if (node.typeAnnotation?.type === 'TSAnyKeyword') {
          context.report({
            node,
            messageId: 'unexpectedAsAny'
          })
        }
      }
    }
  }
}

const noTsIgnore = {
  meta: {
    type: 'problem',
    docs: {
      description: '禁止使用 @ts-ignore 注释',
      category: 'TypeScript Zero Compromise',
      recommended: 'error'
    },
    messages: {
      unexpectedTsIgnore: '使用 @ts-ignore 隐藏错误违反 TypeScript 零妥协规范。请修复错误源而非隐藏错误。'
    }
  },
  create(context) {
    return {
      Program(node) {
        const sourceCode = context.sourceCode
        const comments = sourceCode.getAllComments()

        for (const comment of comments) {
          if (comment.value.includes('@ts-ignore') || comment.value.includes('@ts-nocheck')) {
            context.report({
              loc: comment.loc,
              messageId: 'unexpectedTsIgnore'
            })
          }
        }
      }
    }
  }
}

const noNonNullAssertion = {
  meta: {
    type: 'problem',
    docs: {
      description: '禁止使用 ! 非空断言',
      category: 'TypeScript Zero Compromise',
      recommended: 'error'
    },
    messages: {
      unexpectedNonNull: '使用 ! 非空断言违反 TypeScript 零妥协规范。请使用条件判断或 Optional chaining。'
    }
  },
  create(context) {
    return {
      TSNonNullExpression(node) {
        context.report({
          node,
          messageId: 'unexpectedNonNull'
        })
      }
    }
  }
}

const requireZodSchema = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'API 响应必须使用 Zod Schema 校验',
      category: 'Boundary Validation',
      recommended: 'warn'
    },
    messages: {
      missingZodValidation: 'API 响应未使用 Zod Schema 校验。请从 schemas/ 导入并使用 .parse() 方法。'
    }
  },
  create(context) {
    return {
      CallExpression(node) {
        // 检测 await request.get/post 但未使用 Zod parse
        if (
          node.callee?.object?.name === 'request' &&
          ['get', 'post', 'put', 'delete'].includes(node.callee?.property?.name)
        ) {
          const parent = node.parent
          if (parent?.type !== 'CallExpression' || parent.callee?.property?.name !== 'parse') {
            // 仅警告，不阻止
            context.report({
              node,
              messageId: 'missingZodValidation'
            })
          }
        }
      }
    }
  }
}

export default {
  rules: {
    'no-any-type': noAnyType,
    'no-as-any': noAsAny,
    'no-ts-ignore': noTsIgnore,
    'no-non-null': noNonNullAssertion,
    'require-zod-schema': requireZodSchema
  }
}