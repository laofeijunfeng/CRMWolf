import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger
} from '@/components/ui/context-menu'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger
} from '@/components/ui/hover-card'
import {
  Popover,
  PopoverContent,
  PopoverTrigger
} from '@/components/ui/popover'

const attached: VueWrapper[] = []

const mountOpen = (components: Record<string, unknown>, template: string): VueWrapper => {
  const wrapper = mount({
    components,
    setup: () => ({ open: ref(true) }),
    template,
    attachTo: document.body
  })
  attached.push(wrapper)
  return wrapper
}

const findOpenSurface = (label: string): HTMLElement => {
  const openNodes = Array.from(document.body.querySelectorAll<HTMLElement>('[data-state="open"]'))
  const surface = openNodes.find(node => (
    node.textContent?.includes(label) === true
    && node.classList.contains('rounded-wolf-overlay')
  ))
  if (surface === undefined) {
    throw new Error(`Open overlay surface not found for ${label}: ${openNodes.map(node => node.className).join(' | ')}`)
  }
  return surface
}

const expectOverlaySurface = (surface: HTMLElement): void => {
  expect(surface.classList.contains('rounded-wolf-overlay')).toBe(true)
  expect(surface.classList.contains('shadow-wolf-overlay')).toBe(true)
  expect(surface.classList.contains('shadow-md')).toBe(false)
  expect(surface.classList.contains('shadow-lg')).toBe(false)
  expect(surface.classList.contains('shadow-wolf-dropdown')).toBe(false)
}

describe('overlay surface contract', () => {
  afterEach(() => {
    while (attached.length > 0) {
      attached.pop()?.unmount()
    }
  })

  it('gives Popover content overlay radius and shadow', async () => {
    mountOpen(
      { Popover, PopoverContent, PopoverTrigger },
      `
        <Popover v-model:open="open">
          <PopoverTrigger>打开面板</PopoverTrigger>
          <PopoverContent>筛选面板</PopoverContent>
        </Popover>
      `
    )
    await nextTick()
    expectOverlaySurface(findOpenSurface('筛选面板'))
  })

  it('gives DropdownMenu content overlay radius and shadow', async () => {
    mountOpen(
      { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger },
      `
        <DropdownMenu v-model:open="open">
          <DropdownMenuTrigger>打开菜单</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem>下拉菜单项</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      `
    )
    await nextTick()
    expectOverlaySurface(findOpenSurface('下拉菜单项'))
  })

  it('gives HoverCard content overlay radius and shadow', async () => {
    mountOpen(
      { HoverCard, HoverCardContent, HoverCardTrigger },
      `
        <HoverCard v-model:open="open" :open-delay="0" :close-delay="0">
          <HoverCardTrigger>打开卡片</HoverCardTrigger>
          <HoverCardContent>悬停卡片</HoverCardContent>
        </HoverCard>
      `
    )
    await nextTick()
    expectOverlaySurface(findOpenSurface('悬停卡片'))
  })

  it('gives ContextMenu content overlay radius and shadow', async () => {
    const wrapper = mount({
      components: { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuTrigger },
      template: `
        <ContextMenu>
          <ContextMenuTrigger class="overlay-surface-context-trigger">打开右键</ContextMenuTrigger>
          <ContextMenuContent>
            <ContextMenuItem>右键菜单项</ContextMenuItem>
          </ContextMenuContent>
        </ContextMenu>
      `,
      attachTo: document.body
    })
    attached.push(wrapper)
    wrapper.get('.overlay-surface-context-trigger').element.dispatchEvent(new MouseEvent('contextmenu', {
      clientX: 48,
      clientY: 64,
      button: 2,
      bubbles: true,
      cancelable: true
    }))
    await flushPromises()
    await nextTick()
    await flushPromises()
    expectOverlaySurface(findOpenSurface('右键菜单项'))
  })
})
