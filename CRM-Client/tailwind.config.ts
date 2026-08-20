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
    // Status colors (for ApprovalStatusBadge)
    'text-wolf-success-text',
    'bg-wolf-success-bg',
    'text-wolf-warning-text',
    'bg-wolf-warning-bg',
    'text-wolf-danger-text',
    'bg-wolf-danger-bg',
    // Radius
    'rounded-wolf',
    'rounded-wolf-sm',
    'rounded-wolf-md',
    'rounded-wolf-lg',
    'rounded-wolf-xl',
    'rounded-wolf-surface',
    'rounded-wolf-overlay',
    'rounded-wolf-sheet',
    'rounded-wolf-popover',
    'rounded-wolf-full',
    // Shadows
    'shadow-wolf-card',
    'shadow-wolf-hover',
    'shadow-wolf-overlay',
    'shadow-wolf-modal',
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
			background: 'hsl(var(--background) / <alpha-value>)',
			foreground: 'hsl(var(--foreground) / <alpha-value>)',
			card: {
				DEFAULT: 'hsl(var(--card) / <alpha-value>)',
				foreground: 'hsl(var(--card-foreground) / <alpha-value>)'
			},
			popover: {
				DEFAULT: 'hsl(var(--popover) / <alpha-value>)',
				foreground: 'hsl(var(--popover-foreground) / <alpha-value>)'
			},
			primary: {
				DEFAULT: 'hsl(var(--primary) / <alpha-value>)',
				foreground: 'hsl(var(--primary-foreground) / <alpha-value>)'
			},
			secondary: {
				DEFAULT: 'hsl(var(--secondary) / <alpha-value>)',
				foreground: 'hsl(var(--secondary-foreground) / <alpha-value>)'
			},
			muted: {
				DEFAULT: 'hsl(var(--muted) / <alpha-value>)',
				foreground: 'hsl(var(--muted-foreground) / <alpha-value>)'
			},
			accent: {
				DEFAULT: 'hsl(var(--accent) / <alpha-value>)',
				foreground: 'hsl(var(--accent-foreground) / <alpha-value>)'
			},
			destructive: {
				DEFAULT: 'hsl(var(--destructive) / <alpha-value>)',
				foreground: 'hsl(var(--destructive-foreground) / <alpha-value>)'
			},
			border: 'hsl(var(--border) / <alpha-value>)',
			input: 'hsl(var(--input) / <alpha-value>)',
			ring: 'hsl(var(--ring) / <alpha-value>)',
			wolf: {
				primary: {
					DEFAULT: 'hsl(var(--primary) / <alpha-value>)',
					hover: 'hsl(var(--primary-hover) / <alpha-value>)',
					active: 'hsl(var(--primary-active) / <alpha-value>)',
					light: 'hsl(var(--primary) / 0.1)'
				},
				secondary: 'hsl(var(--info) / <alpha-value>)',
				accent: 'hsl(var(--success) / <alpha-value>)',
				bg: {
					page: 'hsl(var(--background) / <alpha-value>)',
					card: 'hsl(var(--card) / <alpha-value>)',
					sidebar: 'hsl(var(--sidebar-background) / <alpha-value>)',
					hover: 'hsl(var(--accent) / <alpha-value>)',
					muted: 'hsl(var(--muted) / <alpha-value>)',
					elevated: 'hsl(var(--popover) / <alpha-value>)'
				},
				text: {
					primary: 'hsl(var(--foreground) / <alpha-value>)',
					secondary: 'hsl(var(--muted-foreground) / <alpha-value>)',
					tertiary: 'hsl(var(--muted-foreground) / <alpha-value>)',
					placeholder: 'hsl(var(--muted-foreground) / <alpha-value>)',
					inverse: 'hsl(var(--primary-foreground) / <alpha-value>)',
					link: 'hsl(var(--primary) / <alpha-value>)',
					'link-hover': 'hsl(var(--primary-hover) / <alpha-value>)'
				},
				border: {
					'default': 'hsl(var(--border) / <alpha-value>)',
					hover: 'hsl(var(--ring) / <alpha-value>)',
					light: 'hsl(var(--muted) / <alpha-value>)',
					divider: 'hsl(var(--border) / <alpha-value>)'
				},
				success: {
					DEFAULT: 'hsl(var(--success) / <alpha-value>)',
					text: 'hsl(var(--success) / <alpha-value>)',
					bg: 'hsl(var(--success) / 0.1)',
					border: 'hsl(var(--success) / <alpha-value>)'
				},
				warning: {
					DEFAULT: 'hsl(var(--warning) / <alpha-value>)',
					text: 'hsl(var(--warning) / <alpha-value>)',
					bg: 'hsl(var(--warning) / 0.1)',
					border: 'hsl(var(--warning) / <alpha-value>)'
				},
				danger: {
					DEFAULT: 'hsl(var(--destructive) / <alpha-value>)',
					text: 'hsl(var(--destructive) / <alpha-value>)',
					bg: 'hsl(var(--destructive) / 0.1)',
					border: 'hsl(var(--destructive) / <alpha-value>)'
				},
				info: {
					DEFAULT: 'hsl(var(--info) / <alpha-value>)',
					text: 'hsl(var(--info) / <alpha-value>)',
					bg: 'hsl(var(--info) / 0.1)',
					border: 'hsl(var(--info) / <alpha-value>)'
				}
			},
			sidebar: {
				DEFAULT: 'hsl(var(--sidebar-background) / <alpha-value>)',
				foreground: 'hsl(var(--sidebar-foreground) / <alpha-value>)',
				primary: 'hsl(var(--sidebar-primary) / <alpha-value>)',
				'primary-foreground': 'hsl(var(--sidebar-primary-foreground) / <alpha-value>)',
				accent: 'hsl(var(--sidebar-accent) / <alpha-value>)',
				'accent-foreground': 'hsl(var(--sidebar-accent-foreground) / <alpha-value>)',
				active: 'hsl(var(--sidebar-active) / <alpha-value>)',
				'active-foreground': 'hsl(var(--sidebar-active-foreground) / <alpha-value>)',
				border: 'hsl(var(--sidebar-border) / <alpha-value>)',
				ring: 'hsl(var(--sidebar-ring) / <alpha-value>)'
			}
		},
		borderRadius: {
			wolf: '6px',
			'wolf-sm': '4px',
				'wolf-md': '6px',
			'wolf-lg': '8px',
				'wolf-xl': '12px',
				'wolf-surface': '12px',
				'wolf-overlay': '12px',
				'wolf-sheet': '12px',
				'wolf-popover': '12px',
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
			'wolf-overlay': '0 4px 12px rgba(0, 0, 0, 0.12)',
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
				'touch-target': '44px',
				'input-desktop': '36px',
				'input-mobile': '44px'
			},
		height: {
			'touch-target': '44px',
				'button-sm': '32px',
				'button-md': '36px',
				'button-lg': '40px',
				'input-desktop': '36px',
				'input-mobile': '44px',
			'wolf-icon-xs': '16px',
			'wolf-icon-sm': '20px',
			'wolf-icon-md': '24px',
			'wolf-icon-lg': '32px',
				'wolf-context-tabs': '36px'
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
