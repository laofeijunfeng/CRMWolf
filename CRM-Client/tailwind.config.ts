import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: ['class', 'class'],
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  // Safelist: 确保 cn() 函数中的 wolf-* 类都被生成
  safelist: [
    // Colors
    'bg-wolf-bg-card',
    'bg-wolf-bg-page',
    'bg-wolf-bg-hover',
    'bg-wolf-bg-muted',
    'text-wolf-text-primary',
    'text-wolf-text-secondary',
    'text-wolf-text-tertiary',
    'text-wolf-text-inverse',
    'text-wolf-primary',
    'border-wolf-border-default',
    'border-wolf-border-hover',
    // Radius
    'rounded-wolf',
    'rounded-wolf-sm',
    'rounded-wolf-lg',
    'rounded-wolf-full',
    // Shadows
    'shadow-wolf-card',
    'shadow-wolf-hover',
    // Spacing
    'px-wolf-lg',
    'px-wolf-sm',
    'px-wolf-xs',
    'py-wolf-sm',
    'p-wolf-xs',
    'p-wolf-sm',
    // Typography
    'text-wolf-body',
    'text-wolf-title',
    'text-wolf-caption',
    'font-wolf-medium',
    'font-wolf-semibold',
    // Transitions
    'transition-all',
    'duration-150',
    // Heights
    'h-wolf-context-tabs',
  ],
  theme: {
    extend: {
      colors: {
        // shadcn-vue 必需的语义颜色（必须定义 background 以支持 bg-background）
        background: '#FFFFFF',
        foreground: '#0F172A',
        card: {
          DEFAULT: '#FFFFFF',
          foreground: '#0F172A'
        },
        popover: {
          DEFAULT: '#FFFFFF',
          foreground: '#0F172A'
        },
        primary: {
          DEFAULT: '#2563EB',
          foreground: '#FFFFFF'
        },
        secondary: {
          DEFAULT: '#EEF2FF',
          foreground: '#0F172A'
        },
        muted: {
          DEFAULT: '#F1F5FD',
          foreground: '#64748B'
        },
        accent: {
          DEFAULT: '#EEF2FF',
          foreground: '#0F172A'
        },
        destructive: {
          DEFAULT: '#DC2626',
          foreground: '#F8FAFC'
        },
        border: '#E4ECFC',
        input: '#E4ECFC',
        ring: '#2563EB',
        // CRMWolf 设计系统颜色
        wolf: {
          primary: {
            DEFAULT: '#2563EB',
            hover: '#1E40AF',
            active: '#1D4ED8',
            light: 'rgba(37, 99, 235, 0.1)'
          },
          secondary: '#3B82F6',
          accent: '#059669',
          bg: {
            page: '#F8FAFC',
            card: '#FFFFFF',
            sidebar: '#FFFFFF',
            hover: '#EEF2FF',
            muted: '#F1F5FD',
            elevated: '#FFFFFF'
          },
          text: {
            primary: '#0F172A',
            secondary: '#64748B',
            tertiary: '#94A3B8',
            placeholder: '#94A3B8',
            inverse: '#FFFFFF',
            link: '#2563EB',
            'link-hover': '#1E40AF'
          },
          border: {
            'default': '#E4ECFC',
            hover: '#2563EB',
            light: '#F1F5FD',
            divider: '#E4ECFC'
          },
          success: {
            DEFAULT: '#10B981',
            text: '#10B981',
            bg: 'rgba(16, 185, 129, 0.1)',
            border: '#10B981'
          },
          warning: {
            DEFAULT: '#F59E0B',
            text: '#F59E0B',
            bg: 'rgba(245, 158, 11, 0.1)',
            border: '#F59E0B'
          },
          danger: {
            DEFAULT: '#DC2626',
            text: '#DC2626',
            bg: 'rgba(220, 38, 38, 0.1)',
            border: '#DC2626'
          },
          info: {
            DEFAULT: '#2563EB',
            text: '#2563EB',
            bg: 'rgba(37, 99, 235, 0.1)',
            border: '#2563EB'
          }
        }
      },
      borderRadius: {
        wolf: '6px',
        'wolf-sm': '4px',
        'wolf-lg': '8px',
        'wolf-full': '9999px'
      },
      spacing: {
        'wolf-xs': '4px',
        'wolf-sm': '8px',
        'wolf-md': '12px',
        'wolf-lg': '16px',
        'wolf-xl': '24px',
        'wolf-2xl': '32px',
        'wolf-8': '32px'
      },
      width: {
        'wolf-icon-xs': '16px',
        'wolf-icon-sm': '20px',
        'wolf-icon-md': '24px',
        'wolf-icon-lg': '32px'
      },
      boxShadow: {
        'wolf-card': '0 1px 3px rgba(0, 0, 0, 0.1)',
        'wolf-hover': '0 2px 8px rgba(0, 0, 0, 0.15)',
        'wolf-dropdown': '0 -4px 12px rgba(0, 0, 0, 0.15)',
        'wolf-modal': '0 4px 16px rgba(0, 0, 0, 0.15)',
        'wolf-bottom': '0 -2px 8px rgba(0, 0, 0, 0.1)'
      },
      fontFamily: {
        wolf: [
          '-apple-system',
          'BlinkMacSystemFont',
          'PingFang SC',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif'
        ],
        display: [
          'IBM Plex Sans',
          '-apple-system',
          'BlinkMacSystemFont',
          'PingFang SC',
          'Segoe UI',
          'sans-serif'
        ],
        mono: [
          'IBM Plex Mono',
          'SF Mono',
          'Monaco',
          'Cascadia Code',
          'monospace'
        ]
      },
      fontSize: {
        'wolf-title': [
          '16px',
          {
            lineHeight: '1.2'
          }
        ],
        'wolf-body': [
          '14px',
          {
            lineHeight: '1.5'
          }
        ],
        'wolf-auxiliary': [
          '13px',
          {
            lineHeight: '1.5'
          }
        ],
        'wolf-caption': [
          '12px',
          {
            lineHeight: '1.5'
          }
        ]
      },
      fontWeight: {
        'wolf-normal': '400',
        'wolf-medium': '500',
        'wolf-semibold': '600'
      },
      transitionDuration: {
        wolf: '150ms',
        'wolf-fast': '150ms',
        'wolf-hover': '200ms',
        'wolf-press': '150ms'
      },
      outlineWidth: {
        'wolf-focus': '2px',
        'wolf-focus-strong': '3px',
        'wolf-focus-subtle': '1px'
      },
      outlineOffset: {
        wolf: '2px'
      },
      minHeight: {
        'touch-target': '44px'
      },
      height: {
        'touch-target': '44px',
        'button-sm': '24px',
        'button-md': '32px',
        'button-lg': '44px',
        'input-desktop': '32px',
        'input-mobile': '44px',
        'wolf-icon-xs': '16px',
        'wolf-icon-sm': '20px',
        'wolf-icon-md': '24px',
        'wolf-icon-lg': '32px',
        'wolf-context-tabs': '48px'
      },
      minWidth: {
        'touch-target': '44px'
      },
      screens: {
        xs: '375px',
        sm: '768px',
        md: '1024px',
        lg: '1440px'
      },
      keyframes: {
        'accordion-down': {
          from: {
            height: '0'
          },
          to: {
            height: 'var(--reka-accordion-content-height)'
          }
        },
        'accordion-up': {
          from: {
            height: 'var(--reka-accordion-content-height)'
          },
          to: {
            height: '0'
          }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out'
      }
    }
  },
  plugins: [
    require('tailwindcss-animate'),
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}

export default config