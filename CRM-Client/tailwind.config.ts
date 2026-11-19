import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
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
			'ring-input': 'hsl(var(--ring-input) / <alpha-value>)',
			brand: {
				DEFAULT: 'hsl(var(--brand) / <alpha-value>)',
				foreground: 'hsl(var(--brand-foreground) / <alpha-value>)'
			},
			success: 'hsl(var(--status-success) / <alpha-value>)',
			warning: 'hsl(var(--status-warning) / <alpha-value>)',
			danger: 'hsl(var(--status-danger) / <alpha-value>)',
			info: 'hsl(var(--status-info) / <alpha-value>)',
			'wash-hover': 'var(--wash-hover)',
			'wash-selected': 'var(--wash-selected)',
			sidebar: {
				DEFAULT: 'hsl(var(--sidebar-background) / <alpha-value>)',
				foreground: 'hsl(var(--sidebar-foreground) / <alpha-value>)',
				primary: 'hsl(var(--sidebar-primary) / <alpha-value>)',
				'primary-foreground': 'hsl(var(--sidebar-primary-foreground) / <alpha-value>)',
				accent: 'hsl(var(--sidebar-accent) / <alpha-value>)',
				'accent-foreground': 'hsl(var(--sidebar-accent-foreground) / <alpha-value>)',
				border: 'hsl(var(--sidebar-border) / <alpha-value>)',
				ring: 'hsl(var(--sidebar-ring) / <alpha-value>)'
			}
		},
		borderRadius: {
			sm: 'var(--radius-sm)',
			md: 'var(--radius-md)',
			lg: 'var(--radius-lg)',
			xl: 'var(--radius-xl)',
		},
		boxShadow: {
			'1': 'var(--shadow-1)',
			'2': 'var(--shadow-2)',
			'3': 'var(--shadow-3)'
		},
		fontFamily: {
			sans: 'var(--font-sans)',
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
			display: ['24px', { lineHeight: '32px', fontWeight: '600' }],
			title: ['18px', { lineHeight: '28px', fontWeight: '600' }],
			'body-strong': ['16px', { lineHeight: '24px', fontWeight: '500' }],
			body: ['14px', { lineHeight: '20px' }],
			caption: ['12px', { lineHeight: '16px' }],
			// 13px 只用于 sm 控件内文字
			'control-sm': ['13px', { lineHeight: '20px' }],
			// 根字号为 14px，rem 档会缩放；Tailwind 同名字号档固定为 px，对齐 token 字阶
			xs: ['12px', { lineHeight: '16px' }],
			sm: ['14px', { lineHeight: '20px' }],
			base: ['14px', { lineHeight: '20px' }],
			lg: ['18px', { lineHeight: '28px' }],
			xl: ['20px', { lineHeight: '28px' }]
		},
		transitionDuration: {
			DEFAULT: 'var(--duration-base)',
			overlay: 'var(--duration-overlay)'
		},
		transitionTimingFunction: {
			DEFAULT: 'var(--ease-standard)',
			standard: 'var(--ease-standard)'
		},
			minHeight: {
				'touch-target': 'var(--touch-target)',
				control: 'var(--control-h-md)'
			},
		height: {
			'touch-target': 'var(--touch-target)',
			'control-xs': 'var(--control-h-xs)',
			'control-sm': 'var(--control-h-sm)',
			control: 'var(--control-h-md)',
			'control-lg': 'var(--control-h-lg)',
			'context-tabs': 'var(--context-tabs-height)'
		},
		minWidth: {
			'touch-target': 'var(--touch-target)'
		},
		padding: {
			'control-xs': 'var(--control-px-xs)',
			'control-sm': 'var(--control-px-sm)',
			control: 'var(--control-px-md)',
			'control-lg': 'var(--control-px-lg)'
		},
		gap: {
			'control-sm': 'var(--control-gap-sm)',
			control: 'var(--control-gap-md)'
		},
		opacity: {
			disabled: 'var(--disabled-opacity)'
		},
		size: {
			'control-sm': 'var(--control-h-sm)',
			control: 'var(--control-h-md)',
			'control-lg': 'var(--control-h-lg)',
			'icon-xs': 'var(--icon-xs)',
			'icon-sm': 'var(--icon-sm)',
			'icon-lg': 'var(--icon-lg)'
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
			},
			'collapsible-down': {
				from: {
					height: '0',
				},
				to: {
					height: 'var(--reka-collapsible-content-height)',
				},
			},
			'collapsible-up': {
				from: {
					height: 'var(--reka-collapsible-content-height)',
				},
				to: {
					height: '0',
				},
			},
		},
		animation: {
			'accordion-down': 'accordion-down 0.2s ease-out',
			'accordion-up': 'accordion-up 0.2s ease-out',
			'collapsible-down': 'collapsible-down 0.2s ease-out',
			'collapsible-up': 'collapsible-up 0.2s ease-out'
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
