/**
 * Sheet (Drawer) Component - z-index 层级管理
 *
 * z-index: z-[200] (Drawer 层，介于 Navigation 和 Modal)
 *
 * 层级关系（详见 docs/LAYOUT.md）：
 * - Dialog (z-1000) > Sheet (z-200) > TopBar (z-90)
 * - Drawer 遮挡导航，但允许 Modal 在其上方打开
 *
 * 规范依据：
 * - docs/LAYOUT.md - z-index 层级管理
 * - UI/UX Pro Max §5: z-index-management
 * - AppLayout.vue $z-index-modal: 1000
 */
import type { VariantProps } from "class varience-authority"
import { cva } from "class-variance-authority"

export { default as Sheet } from "./Sheet.vue"
export { default as SheetClose } from "./SheetClose.vue"
export { default as SheetContent } from "./SheetContent.vue"
export { default as SheetDescription } from "./SheetDescription.vue"
export { default as SheetFooter } from "./SheetFooter.vue"
export { default as SheetHeader } from "./SheetHeader.vue"
export { default as SheetTitle } from "./SheetTitle.vue"
export { default as SheetTrigger } from "./SheetTrigger.vue"

/**
 * Sheet Variants - z-index 层级管理
 *
 * 关键：DialogContent (z-[201]) 高于 DialogOverlay (z-[200])
 * - Content 在 Overlay 之上，确保内容可见
 * - Drawer 遮挡 TopBar (z-90) 和 Sidebar (z-100)
 * - 同时低于 Dialog (z-1000)，允许 Modal 在 Sheet 上方打开
 */
export const sheetVariants = cva(
  "fixed z-[201] gap-4 bg-background p-6 shadow-lg transition ease-in-out data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:duration-300 data-[state=open]:duration-500",
  {
    variants: {
      side: {
        top: "inset-x-0 top-0 border-b data-[state=closed]:slide-out-to-top data-[state=open]:slide-in-from-top",
        bottom:
            "inset-x-0 bottom-0 border-t data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom",
        left: "inset-y-0 left-0 h-full w-3/4 border-r data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left sm:max-w-sm",
        right:
            "inset-y-0 right-0 h-full w-3/4 border-l data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:max-w-sm",
      },
    },
    defaultVariants: {
      side: "right",
    },
  },
)

export type SheetVariants = VariantProps<typeof sheetVariants>
