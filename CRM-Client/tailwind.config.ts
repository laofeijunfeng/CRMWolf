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
			display: 'var(--font-display)',
			mono: 'var(--font-mono)'
		},
		fontSize: {
			display: ['var(--font-size-display)', { lineHeight: 'var(--line-height-display)', fontWeight: '600' }],
			title: ['var(--font-size-title)', { lineHeight: 'var(--line-height-title)', fontWeight: '600' }],
			'body-strong': ['var(--font-size-body-strong)', { lineHeight: 'var(--line-height-body-strong)', fontWeight: '500' }],
			body: ['var(--font-size-body)', { lineHeight: 'var(--line-height-body)' }],
			caption: ['var(--font-size-caption)', { lineHeight: 'var(--line-height-caption)' }],
			// 13px 只用于 sm 控件内文字
			'control-sm': ['var(--font-size-control-sm)', { lineHeight: 'var(--line-height-body)' }],
			// 根字号为 14px，rem 档会缩放；Tailwind 同名字号档固定到 token 字阶
			xs: ['var(--font-size-caption)', { lineHeight: 'var(--line-height-caption)' }],
			sm: ['var(--font-size-body)', { lineHeight: 'var(--line-height-body)' }],
			base: ['var(--font-size-body)', { lineHeight: 'var(--line-height-body)' }],
			lg: ['var(--font-size-title)', { lineHeight: 'var(--line-height-title)' }]
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
				'control-xs': 'var(--control-h-xs)',
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
			'touch-target': 'var(--touch-target)',
			menu: 'var(--menu-min-width)'
		},
		// 根字号为 14px，rem 间距档（p-1、gap-2…）会按 0.875 缩放；space-N 档固定为 px，与 $space-N 一致
		spacing: {
			'space-1': '4px',
			'space-2': '8px',
			'space-3': '12px',
			'space-4': '16px',
			'space-6': '24px',
			'space-8': '32px'
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
		textColor: {
			// 状态色的文字与图标：基色 --status-fg-mix + 前景，与 [data-tone] 同一条派生
			tone: {
				success: 'color-mix(in srgb, hsl(var(--status-success)) var(--status-fg-mix), hsl(var(--foreground)))',
				warning: 'color-mix(in srgb, hsl(var(--status-warning)) var(--status-fg-mix), hsl(var(--foreground)))',
				danger: 'color-mix(in srgb, hsl(var(--status-danger)) var(--status-fg-mix), hsl(var(--foreground)))',
				info: 'color-mix(in srgb, hsl(var(--status-info)) var(--status-fg-mix), hsl(var(--foreground)))'
			}
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
