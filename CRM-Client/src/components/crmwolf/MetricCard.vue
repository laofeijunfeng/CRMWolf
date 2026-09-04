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
  border-color: hsl(var(--border) / 0.9);
  border-radius: $wolf-radius-xl-v2;
  background:
    linear-gradient(0deg, hsl(var(--primary) / 0.06) 0%, hsl(var(--primary) / 0.025) 34%, hsl(var(--background) / 0) 70%),
    linear-gradient(135deg, hsl(var(--muted) / 0.88) 0%, hsl(var(--card)) 46%, hsl(var(--card)) 100%);
  box-shadow: 0 1px 2px hsl(var(--foreground) / 0.03);
}

.metric-card::before {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: '';
  border-radius: inherit;
  box-shadow: inset 0 1px 0 hsl(var(--background) / 0.85);
}

.metric-card[data-tone='positive'] {
  background:
    linear-gradient(0deg, hsl(var(--primary) / 0.06) 0%, hsl(var(--primary) / 0.025) 34%, hsl(var(--background) / 0) 70%),
    linear-gradient(135deg, hsl(var(--muted) / 0.92) 0%, hsl(var(--card)) 46%, hsl(var(--card)) 100%);
}

.metric-card[data-tone='negative'] {
  background:
    linear-gradient(0deg, hsl(var(--primary) / 0.055) 0%, hsl(var(--primary) / 0.022) 34%, hsl(var(--background) / 0) 70%),
    linear-gradient(135deg, hsl(var(--muted) / 0.92) 0%, hsl(var(--card)) 46%, hsl(var(--card)) 100%);
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
  color: hsl(var(--muted-foreground));
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
  border-color: hsl(var(--foreground) / 0.12);
  border-radius: $wolf-radius-full-v2;
  color: hsl(var(--card-foreground));
  background: hsl(var(--background) / 0.72);
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: 22px;
  box-shadow: none;
}

.metric-card[data-tone='positive'] .metric-card__badge {
  color: hsl(var(--success));
  background: hsl(var(--success) / 0.1);
  border-color: hsl(var(--success) / 0.24);
}

.metric-card[data-tone='negative'] .metric-card__badge {
  color: hsl(var(--destructive));
  background: hsl(var(--destructive) / 0.1);
  border-color: hsl(var(--destructive) / 0.24);
}

.metric-card__value {
  min-width: 0;
  color: hsl(var(--foreground));
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
  color: hsl(var(--card-foreground));
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
  color: hsl(var(--muted-foreground));
  font-size: $wolf-font-size-caption-v2;
  line-height: 1.45;
}

.metric-card__footer-title {
  min-width: 0;
  color: hsl(var(--foreground));
  font-weight: $wolf-font-weight-semibold-v2;
}

.metric-card__footer-note {
  min-width: 0;
  color: hsl(var(--muted-foreground));
}

.metric-card__skeleton {
  display: block;
  width: 72%;
  height: 12px;
  background: hsl(var(--muted));
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
