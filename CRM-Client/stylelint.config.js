/**
 * Stylelint 配置 - CRMWolf
 *
 * @description 强制使用 Design Tokens，禁止硬编码样式
 * @规则来源: CRM-Docs/design-system/README.md（设计系统根入口）
 */

export default {
  extends: ['stylelint-config-standard-scss'],
  plugins: ['stylelint-scss'],
  rules: {
    // ===== SCSS 特定规则 =====
    'scss/at-rule-no-unknown': true,
    'scss/no-duplicate-dollar-variables': true,
    'no-empty-source': true,
    'no-missing-end-of-source-newline': true,

    // ===== 设计系统强制规则 =====

    // 禁止硬编码颜色
    'declaration-property-value-disallowed-list': {
      'color': ['/#[0-9a-fA-F]{3,6}/', '/rgb\\(/', '/rgba\\(/'],
      'background-color': ['/#[0-9a-fA-F]{3,6}/', '/rgb\\(/', '/rgba\\(/'],
      'background': ['/#[0-9a-fA-F]{3,6}/'],
      'border-color': ['/#[0-9a-fA-F]{3,6}/'],
      'border-top-color': ['/#[0-9a-fA-F]{3,6}/'],
      'border-right-color': ['/#[0-9a-fA-F]{3,6}/'],
      'border-bottom-color': ['/#[0-9a-fA-F]{3,6}/'],
      'border-left-color': ['/#[0-9a-fA-F]{3,6}/'],

      // 禁止旧圆角值（统一 6px）
      'border-radius': ['/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/'],
      'border-top-left-radius': ['/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/'],
      'border-top-right-radius': ['/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/'],
      'border-bottom-left-radius': ['/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/'],
      'border-bottom-right-radius': ['/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/'],
    },

    // 允许的 Design Tokens（圆角）
    'declaration-property-value-allowed-list': {
      'border-radius': [
        '$wolf-radius-v2',
        '$wolf-radius-sm-v2',
        '$wolf-radius-lg-v2',
        '$wolf-radius-full-v2',
        '/%/',
        'inherit',
        'initial',
        '0',
      ],
    },

    // SCSS 变量命名规则
    'scss/dollar-variable-pattern': [
      '^wolf-([a-z]+)(-v2)?$',
      { message: 'Design Tokens 必须以 $wolf- 开头' },
    ],
  },
  ignoreFiles: [
    'node_modules/**',
    'dist/**',
    'coverage/**',
    '**/*.css',
    'src/styles/wolf-design.scss',
    'src/styles/_typography.scss',
    'src/styles/buttons.css',
    'src/styles/colors.css',
    'src/styles/spacing.css',
    'src/styles/typography.css',
    'src/styles/payment.scss',
    'src/styles/payment-sidebar.scss',
  ],
}