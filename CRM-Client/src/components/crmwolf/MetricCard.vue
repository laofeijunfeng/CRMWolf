<script setup lang="ts">
import {
  Card,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

type MetricTone = 'positive' | 'negative' | 'neutral'

interface Props {
  title: string
  value?: string | number | null
  description?: string
  footer?: string
  subfooter?: string
  badge?: string
  tone?: MetricTone
  loading?: boolean
}

withDefaults(defineProps<Props>(), {
  value: null,
  description: '',
  footer: '',
  subfooter: '',
  badge: '',
  tone: 'neutral',
  loading: false
})
</script>

<template>
  <Card class="metric-card" :data-tone="tone" :aria-busy="loading ? 'true' : undefined">
    <CardHeader class="metric-card__header">
      <div class="metric-card__topline">
        <CardDescription class="metric-card__label">{{ title }}</CardDescription>
        <Badge v-if="badge && !loading" variant="outline" class="metric-card__badge">
          {{ badge }}
        </Badge>
      </div>

      <CardTitle class="metric-card__value">
        <span v-if="loading" class="metric-card__skeleton metric-card__skeleton--value"></span>
        <slot v-else name="value">{{ value ?? '-' }}</slot>
      </CardTitle>

      <div class="metric-card__description">
        <span v-if="loading" class="metric-card__skeleton"></span>
        <slot v-else name="description">
          <span v-if="description">{{ description }}</span>
        </slot>
      </div>
    </CardHeader>

    <CardFooter class="metric-card__footer">
      <div class="metric-card__footer-inner">
        <span v-if="loading" class="metric-card__skeleton metric-card__skeleton--short"></span>
        <slot v-else name="footer">
          <strong v-if="footer" class="metric-card__footer-title">{{ footer }}</strong>
        </slot>

        <slot v-if="!loading" name="subfooter">
          <span v-if="subfooter" class="metric-card__footer-note">{{ subfooter }}</span>
        </slot>
      </div>
    </CardFooter>
  </Card>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.metric-card {
  position: relative;
  min-width: 0;
  overflow: hidden;
  border-color: rgba($wolf-border-default-v2, 0.9);
  border-radius: $wolf-radius-xl-v2;
  background:
    linear-gradient(0deg, rgba($wolf-primary-v2, 0.06) 0%, rgba($wolf-primary-v2, 0.025) 34%, rgba(255, 255, 255, 0) 70%),
    linear-gradient(135deg, rgba($wolf-bg-muted-v2, 0.88) 0%, $wolf-bg-card-v2 46%, $wolf-bg-card-v2 100%);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}

.metric-card::before {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: '';
  border-radius: inherit;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
}

.metric-card[data-tone='positive'] {
  background:
    linear-gradient(0deg, rgba($wolf-primary-v2, 0.06) 0%, rgba($wolf-primary-v2, 0.025) 34%, rgba(255, 255, 255, 0) 70%),
    linear-gradient(135deg, rgba($wolf-bg-muted-v2, 0.92) 0%, $wolf-bg-card-v2 46%, $wolf-bg-card-v2 100%);
}

.metric-card[data-tone='negative'] {
  background:
    linear-gradient(0deg, rgba($wolf-primary-v2, 0.055) 0%, rgba($wolf-primary-v2, 0.022) 34%, rgba(255, 255, 255, 0) 70%),
    linear-gradient(135deg, rgba($wolf-bg-muted-v2, 0.92) 0%, $wolf-bg-card-v2 46%, $wolf-bg-card-v2 100%);
}

.metric-card__header {
  position: relative;
  gap: $wolf-space-sm-v2;
  min-height: 84px;
  padding: 14px 16px 6px;
}

.metric-card__topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 24px;
  gap: $wolf-space-md-v2;
}

.metric-card__label {
  min-width: 0;
  color: #475569;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: 1.4;
}

.metric-card__badge {
  flex: 0 0 auto;
  max-width: 48%;
  height: 24px;
  padding: 0 $wolf-space-sm-v2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border-color: rgba(15, 23, 42, 0.12);
  border-radius: $wolf-radius-full-v2;
  color: #334155;
  background: rgba(255, 255, 255, 0.72);
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: 22px;
  box-shadow: none;
}

.metric-card[data-tone='positive'] .metric-card__badge {
  color: #047857;
  background: rgba(236, 253, 245, 0.9);
  border-color: rgba($wolf-success-v2, 0.24);
}

.metric-card[data-tone='negative'] .metric-card__badge {
  color: #b91c1c;
  background: rgba(254, 242, 242, 0.92);
  border-color: rgba($wolf-danger-v2, 0.24);
}

.metric-card__value {
  min-width: 0;
  color: $wolf-text-primary-v2;
  font-family: $wolf-font-mono-v2;
  font-size: 30px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.05;
  letter-spacing: 0;
  word-break: break-word;
}

.metric-card__description {
  display: flex;
  align-items: center;
  min-width: 0;
  min-height: 20px;
  color: #334155;
  font-size: $wolf-font-size-caption-v2;
  line-height: 1.4;
}

.metric-card__footer {
  position: relative;
  align-items: flex-start;
  padding: 0 16px 12px;
}

.metric-card__footer-inner {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 3px;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 1.45;
}

.metric-card__footer-title {
  min-width: 0;
  color: #0f172a;
  font-weight: $wolf-font-weight-semibold-v2;
}

.metric-card__footer-note {
  min-width: 0;
  color: #64748b;
}

.metric-card__skeleton {
  display: block;
  width: 72%;
  height: 12px;
  background: $wolf-bg-muted-v2;
  border-radius: $wolf-radius-sm-v2;
}

.metric-card__skeleton--value {
  width: 48%;
  height: 34px;
}

.metric-card__skeleton--short {
  width: 46%;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .metric-card__header {
    min-height: 80px;
    padding: 12px 14px 6px;
  }

  .metric-card__value {
    font-size: 25px;
  }

  .metric-card__footer {
    padding: 0 14px 12px;
  }
}
</style>
