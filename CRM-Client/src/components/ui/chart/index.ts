import type { Component, Ref } from "vue"
import { createContext } from "reka-ui"

export { default as ChartContainer } from "./ChartContainer.vue"
export { default as ChartLegendContent } from "./ChartLegendContent.vue"
export { default as ChartTooltipContent } from "./ChartTooltipContent.vue"
export { componentToString } from "./utils"

export type ChartConfig = Record<string, {
  label?: string | Component
  icon?: string | Component
  color?: string
}>

interface ChartContextProps {
  id: string
  config: Ref<ChartConfig>
}

export const [useChart, provideChartContext] = createContext<ChartContextProps>("Chart")

export { VisCrosshair as ChartCrosshair, VisTooltip as ChartTooltip } from "@unovis/vue"
