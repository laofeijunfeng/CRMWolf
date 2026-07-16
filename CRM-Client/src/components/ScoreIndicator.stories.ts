/**
 * ScoreIndicator 组件 stories
 *
 * 热力值指示器，用于显示客户/线索的活跃度评分
 */
import type { Meta, StoryObj } from '@storybook/vue3'
import ScoreIndicator from './ScoreIndicator.vue'

const meta: Meta<typeof ScoreIndicator> = {
  title: 'Components/ScoreIndicator',
  component: ScoreIndicator,
  tags: ['autodocs'],
  argTypes: {
    score: {
      control: 'number',
      description: '分数值 (null 表示未知)'
    },
    mode: {
      control: 'select',
      options: ['badge', 'card'],
      description: '显示模式'
    },
    showLevel: {
      control: 'boolean',
      description: '是否显示级别文字标签'
    }
  }
}

export default meta
type Story = StoryObj<typeof ScoreIndicator>

// 高分（≥80）
export const High: Story = {
  args: {
    score: 92,
    mode: 'badge'
  }
}

// 中高（≥60）
export const MediumHigh: Story = {
  args: {
    score: 75,
    mode: 'badge'
  }
}

// 中等（≥40）
export const Medium: Story = {
  args: {
    score: 55,
    mode: 'badge'
  }
}

// 低分（<40）
export const Low: Story = {
  args: {
    score: 25,
    mode: 'badge'
  }
}

// 未知
export const Unknown: Story = {
  args: {
    score: null,
    mode: 'badge'
  }
}

// 卡片模式
export const CardMode: Story = {
  args: {
    score: 88,
    mode: 'card',
    showLevel: true
  }
}

// 所有级别对比
export const AllLevels: Story = {
  render: () => ({
    components: { ScoreIndicator },
    template: `
      <div class="flex gap-4 items-center">
        <ScoreIndicator :score="92" mode="badge" />
        <ScoreIndicator :score="75" mode="badge" />
        <ScoreIndicator :score="55" mode="badge" />
        <ScoreIndicator :score="25" mode="badge" />
        <ScoreIndicator :score="null" mode="badge" />
      </div>
    `
  })
}