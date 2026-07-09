import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      // ===== Wolf Colors V2 =====
      colors: {
        wolf: {
          // Primary（现代蓝色）
          primary: {
            DEFAULT: '#2563EB',
            hover: '#1E40AF',
            active: '#1D4ED8',
            light: 'rgba(37, 99, 235, 0.1)',
          },
          secondary: '#3B82F6',
          accent: '#059669',

          // Backgrounds
          bg: {
            page: '#F8FAFC',
            card: '#FFFFFF',
            sidebar: '#FFFFFF',
            hover: '#EEF2FF',
            muted: '#F1F5FD',
            elevated: '#FFFFFF',
          },

          // Text
          text: {
            primary: '#0F172A',
            secondary: '#64748B',
            tertiary: '#94A3B8',
            placeholder: '#94A3B8',
            inverse: '#FFFFFF',
            link: '#2563EB',
            'link-hover': '#1E40AF',
          },

          // Borders
          border: {
            default: '#E4ECFC',
            hover: '#2563EB',
            light: '#F1F5FD',
            divider: '#E4ECFC',
          },

          // Status Colors（功能色）
          success: {
            DEFAULT: '#10B981',
            text: '#10B981',
            bg: 'rgba(16, 185, 129, 0.1)',
          },
          warning: {
            DEFAULT: '#F59E0B',
            text: '#F59E0B',
            bg: 'rgba(245, 158, 11, 0.1)',
          },
          danger: {
            DEFAULT: '#DC2626',
            text: '#DC2626',
            bg: 'rgba(220, 38, 38, 0.1)',
          },
        },
      },

      // ===== Radius（统一 6px）=====
      borderRadius: {
        'wolf': '6px',
        'wolf-sm': '4px',
        'wolf-lg': '8px',
        'wolf-full': '9999px',
      },

      // ===== Spacing（8dp grid）=====
      spacing: {
        'wolf-xs': '4px',
        'wolf-sm': '8px',
        'wolf-md': '12px',
        'wolf-lg': '16px',
        'wolf-xl': '24px',
        'wolf-2xl': '32px',
      },

      // ===== Shadows（中等强度）=====
      boxShadow: {
        'wolf-card': '0 1px 3px rgba(0, 0, 0, 0.1)',
        'wolf-hover': '0 2px 8px rgba(0, 0, 0, 0.15)',
        'wolf-dropdown': '0 -4px 12px rgba(0, 0, 0, 0.15)',
        'wolf-modal': '0 4px 16px rgba(0, 0, 0, 0.15)',
        'wolf-bottom': '0 -2px 8px rgba(0, 0, 0, 0.1)',
      },

      // ===== Typography =====
      fontFamily: {
        wolf: [
          '-apple-system',
          'BlinkMacSystemFont',
          'PingFang SC',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        display: [
          'IBM Plex Sans',
          '-apple-system',
          'BlinkMacSystemFont',
          'PingFang SC',
          'Segoe UI',
          'sans-serif',
        ],
        mono: [
          'IBM Plex Mono',
          'SF Mono',
          'Monaco',
          'Cascadia Code',
          'monospace',
        ],
      },
      fontSize: {
        'wolf-title': ['16px', { lineHeight: '1.2' }],
        'wolf-body': ['14px', { lineHeight: '1.5' }],
        'wolf-auxiliary': ['13px', { lineHeight: '1.5' }],
        'wolf-caption': ['12px', { lineHeight: '1.5' }],
      },
      fontWeight: {
        'wolf-normal': '400',
        'wolf-medium': '500',
        'wolf-semibold': '600',
      },

      // ===== Animation Duration =====
      transitionDuration: {
        wolf: '150ms',
        'wolf-hover': '200ms',
        'wolf-press': '150ms',
      },

      // ===== Focus Ring Width =====
      outlineWidth: {
        'wolf-focus': '2px',
        'wolf-focus-strong': '3px',
        'wolf-focus-subtle': '1px',
      },
      outlineOffset: {
        'wolf': '2px',
      },

      // ===== Touch Target Sizes =====
      minHeight: {
        'touch-target': '44px',
      },
      height: {
        'touch-target': '44px',
        'button-sm': '24px',
        'button-md': '32px',
        'button-lg': '44px',
        'input-desktop': '32px',
        'input-mobile': '44px',
      },
      minWidth: {
        'touch-target': '44px',
      },

      // ===== Breakpoints（Mobile-first）=====
      screens: {
        xs: '375px',
        sm: '768px',
        md: '1024px',
        lg: '1440px',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}

export default config