import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'CRMWolf 系统文档',
  description: 'CRMWolf 系统功能与模块说明',

  // 源文件目录（指向 CRM-Docs）
  srcDir: '../CRM-Docs',

  // 输出目录
  outDir: '.vitepress/dist',

  // 缓存目录
  cacheDir: '.vitepress/cache',

  themeConfig: {
    // 导航栏
    nav: [
      { text: '首页', link: '/' },
      { text: '系统说明', link: '/system/README' },
      { text: '模块功能', link: '/system/modules/README' },
      { text: '开发规范', link: '/standards/QUICK-START' }
    ],

    // 侧边栏
    sidebar: {
      '/system/': [
        {
          text: '系统说明',
          items: [
            { text: '系统总览', link: '/system/SYSTEM-DESCRIPTION' },
            { text: '系统架构', link: '/system/ARCHITECTURE' },
            { text: '术语表', link: '/system/GLOSSARY' },
            { text: '业务链路接口', link: '/system/BUSINESS-CHAIN-API' },
            { text: '日志规范', link: '/system/LOGGING-STANDARD' }
          ]
        },
        {
          text: '模块功能说明',
          collapsed: false,
          items: [
            { text: '导航入口', link: '/system/modules/README' },
            { text: '线索管理', link: '/system/modules/01-lead-management' },
            { text: '客户管理', link: '/system/modules/02-customer-management' },
            { text: '商机管理', link: '/system/modules/03-opportunity-management' },
            { text: '合同管理', link: '/system/modules/04-contract-management' },
            { text: '回款管理', link: '/system/modules/05-payment-management' },
            { text: '发票管理', link: '/system/modules/06-invoice-management' },
            { text: '财务管理', link: '/system/modules/07-finance-management' },
            { text: 'AI 功能', link: '/system/modules/ai-features' }
          ]
        },
        {
          text: '设计规范',
          collapsed: true,
          items: [
            { text: 'UI 设计规范', link: '/system/design/UI-DESIGN-SPEC' }
          ]
        }
      ],

      '/standards/': [
        {
          text: '开发规范',
          items: [
            { text: '快速上手', link: '/standards/QUICK-START' },
            { text: 'Git 提交规范', link: '/standards/GIT-STANDARD' },
            { text: '合规规范', link: '/standards/COMPLIANCE-STANDARD' },
            { text: '文档规范', link: '/standards/DOCS-STANDARD' },
            { text: 'AI OpenAPI 规范', link: '/standards/AI-API-STANDARD' }
          ]
        }
      ],

      '/best-practices/': [
        {
          text: '最佳实践',
          items: [
            { text: '导航入口', link: '/best-practices/README' }
          ]
        },
        {
          text: '后端',
          collapsed: true,
          items: [
            { text: 'CRUD 模式', link: '/best-practices/backend/crud-patterns' },
            { text: '团队隔离', link: '/best-practices/backend/team-isolation' },
            { text: 'API 设计', link: '/best-practices/backend/api-design' }
          ]
        },
        {
          text: '前端',
          collapsed: true,
          items: [
            { text: 'API 请求', link: '/best-practices/frontend/api-requests' },
            { text: '组件开发', link: '/best-practices/frontend/components' },
            { text: '状态管理', link: '/best-practices/frontend/state-management' }
          ]
        }
      ]
    },

    // 本地搜索
    search: {
      provider: 'local'
    },

    // 社交链接
    socialLinks: []
  },

  // Markdown 配置
  markdown: {
    lineNumbers: false
  }
})