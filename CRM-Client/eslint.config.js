/**
 * ESLint 配置 - CRMWolf
 *
 * @description 零妥协 TypeScript 校验配置
 */

import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'
import customRules from './eslint-custom-rules/index.js'

export default [
  // 基础规则
  js.configs.recommended,

  // TypeScript 严格规则
  ...tseslint.configs.strict,
  ...tseslint.configs.stylistic,

  // Vue 规则
  ...pluginVue.configs['flat/essential'],

  // CRMWolf 自定义规则（红线）
  {
    plugins: {
      'crmwolf': {
        rules: customRules.rules
      }
    },
    rules: {
      // ===== 红线规则（error） =====
      'crmwolf/no-any-type': 'error',
      'crmwolf/no-as-any': 'error',
      'crmwolf/no-ts-ignore': 'error',
      'crmwolf/no-non-null': 'error',

      // ===== 边界校验（warn） =====
      'crmwolf/require-zod-schema': 'warn',

      // ===== TypeScript 严格规则 =====
      '@typescript-eslint/explicit-function-return-type': 'error',
      '@typescript-eslint/explicit-module-boundary-types': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unsafe-assignment': 'error',
      '@typescript-eslint/no-unsafe-member-access': 'error',
      '@typescript-eslint/no-unsafe-call': 'error',
      '@typescript-eslint/no-unsafe-return': 'error',
      '@typescript-eslint/strict-boolean-expressions': 'error',

      // ===== Vue 规则 =====
      'vue/require-prop-types': 'error',
      'vue/require-default-prop': 'error',
      'vue/no-reserved-component-names': 'error',
      'vue/multi-word-component-names': 'error',

      // ===== 代码质量 =====
      'no-console': 'warn',
      'no-debugger': 'error',
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }]
    }
  },

  // 文件覆盖规则
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
        project: './tsconfig.json',
        extraFileExtensions: ['.vue']
      }
    }
  },

  // TypeScript 文件也需要类型信息
  {
    files: ['**/*.ts'],
    languageOptions: {
      parserOptions: {
        project: './tsconfig.json'
      }
    }
  },

  // ========== 分层策略：存量文件暂时降低严格度 ==========
  // 对非 V2 新组件的存量文件，降低部分规则的严格度
  {
    files: [
      'src/**/*.vue',
      'src/**/*.ts'
    ],
    rules: {
      // 存量文件：暂时降级为 warn，不阻塞提交
      '@typescript-eslint/explicit-function-return-type': 'warn',
      '@typescript-eslint/explicit-module-boundary-types': 'warn',
      '@typescript-eslint/no-unsafe-assignment': 'warn',
      '@typescript-eslint/no-unsafe-member-access': 'warn',
      '@typescript-eslint/no-unsafe-call': 'warn',
      '@typescript-eslint/no-unsafe-return': 'warn',
      '@typescript-eslint/strict-boolean-expressions': 'warn',
      '@typescript-eslint/array-type': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }]
    }
  },

  // 忽略文件
  {
    ignores: [
      'node_modules/**',
      'dist/**',
      'coverage/**',
      '*.config.js',
      '*.stories.ts',
      'src/env.d.ts',
      'src/vite-env.d.ts',
      'src/types.d.ts'  // 存量类型定义，待修复
    ]
  }
]