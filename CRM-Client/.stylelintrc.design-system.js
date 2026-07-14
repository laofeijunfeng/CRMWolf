/**
 * Stylelint 设计系统强制规则 - CRMWolf V2
 *
 * @规则来源: CRM-Docs/design-system/README.md（设计系统根入口）
 * @核心规则:
 *   1. 禁止硬编码颜色（必须使用 Design Tokens）
 *   2. 禁止旧圆角值（统一 6px）
 *   3. 禁止硬编码主色（必须使用 $wolf-primary-v2）
 */

export default {
  rules: {
    // ===== 禁止硬编码颜色 =====
    // 规则: 所有颜色必须使用 Design Tokens
    'declaration-property-value-disallowed-list': {
      // 禁止直接写 hex 颜色值
      'color': [
        '/#[0-9a-fA-F]{3,6}/',
        '/rgb\\(/',
        '/rgba\\(/',
      ],
      'background-color': [
        '/#[0-9a-fA-F]{3,6}/',
        '/rgb\\(/',
        '/rgba\\(/',
      ],
      'background': [
        '/#[0-9a-fA-F]{3,6}/',
      ],
      'border-color': [
        '/#[0-9a-fA-F]{3,6}/',
      ],
      'border-top-color': [
        '/#[0-9a-fA-F]{3,6}/',
      ],
      'border-right-color': [
        '/#[0-9a-fA-F]{3,6}/',
      ],
      'border-bottom-color': [
        '/#[0-9a-fA-F]{3,6}/',
      ],
      'border-left-color': [
        '/#[0-9a-fA-F]{3,6}/',
      ],

      // 禁止旧圆角值（统一 6px）
      'border-radius': [
        '/^4px$/',   // 禁止 4px
        '/^8px$/',   // 禁止 8px
        '/^12px$/',  // 禁止 12px
        '/^16px$/',  // 禁止 16px
      ],
      'border-top-left-radius': [
        '/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/',
      ],
      'border-top-right-radius': [
        '/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/',
      ],
      'border-bottom-left-radius': [
        '/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/',
      ],
      'border-bottom-right-radius': [
        '/^4px$/', '/^8px$/', '/^12px$/', '/^16px$/',
      ],

      // 禁止硬编码主色
      '/.*/': [
        '/#4A6FA5/',  // 禁止旧主色 V1
        '/#2563EB/',  // 禁止直接写新主色（必须用变量）
        '/#1E40AF/',  // 禁止直接写 hover 色
        '/#10B981/',  // 禁止直接写成功色
        '/#F59E0B/',  // 禁止直接写警告色
        '/#DC2626/',  // 禁止直接写危险色
      ],
    },

    // ===== 允许的 Design Tokens =====
    'declaration-property-value-allowed-list': {
      // 圆角必须使用变量
      'border-radius': [
        '$wolf-radius-v2',
        '$wolf-radius-sm-v2',
        '$wolf-radius-lg-v2',
        '$wolf-radius-full-v2',
        // 允许百分比和 inherit
        '/%/',
        'inherit',
        'initial',
      ],
    },

    // ===== SCSS 变量规则 =====
    'scss/dollar-variable-pattern': [
      '^wolf-([a-z]+)(-v2)?$',  // 必须以 wolf- 开头，可选 -v2 后缀
      {
        message: 'Design Tokens 必须以 $wolf- 开头',
      },
    ],
  },
}