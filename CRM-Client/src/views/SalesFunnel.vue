<template>
  <div class="sales-funnel-container">
    <el-card :body-style="{ padding: '16px' }">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center; width: 100%">
          <span>销售漏斗分析</span>
          <div class="header-actions">
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              style="width: 280px"
              @change="handleDateChange"
            />
            <el-button :icon="Refresh" @click="handleRefresh">
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <div v-loading="loading" style="width: 100%">
        <div v-if="funnelData.length > 0" class="funnel-content">
          <div class="funnel-chart">
            <div
              v-for="(item, index) in funnelData"
              :key="item.stage_id"
              class="funnel-stage"
              :style="{ width: getStageWidth(item.opportunity_count) }"
            >
              <div class="stage-info">
                <div class="stage-name">{{ item.stage_name }}</div>
                <div class="stage-metrics">
                  <div class="metric">
                    <span class="label">商机数：</span>
                    <span class="value">{{ item.opportunity_count }}</span>
                  </div>
                  <div class="metric">
                    <span class="label">总金额：</span>
                    <span class="value">{{ formatAmount(item.total_amount) }}</span>
                  </div>
                  <div class="metric">
                    <span class="label">平均：</span>
                    <span class="value">{{ formatAmount(item.average_amount) }}</span>
                  </div>
                  <div class="metric">
                    <span class="label">赢率：</span>
                    <span class="value">{{ item.win_probability }}%</span>
                  </div>
                </div>
              </div>
              <div class="conversion-rate" v-if="index > 0">
                转化率: {{ getConversionRate(index) }}%
              </div>
            </div>
          </div>

          <el-divider />

          <el-row :gutter="16">
            <el-col :span="12">
              <el-card header="阶段分布" :body-style="{ padding: '16px' }">
                <div class="chart-container">
                  <div
                    v-for="item in funnelData"
                    :key="item.stage_id"
                    class="bar-item"
                  >
                    <div class="bar-label">{{ item.stage_name }}</div>
                    <div class="bar-wrapper">
                      <div
                        class="bar-fill"
                        :style="{
                          width: getBarWidth(item.opportunity_count),
                          backgroundColor: getStageColor(item.stage_id)
                        }"
                      >
                        <span class="bar-value">{{ item.opportunity_count }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card header="金额分布" :body-style="{ padding: '16px' }">
                <div class="chart-container">
                  <div
                    v-for="item in funnelData"
                    :key="item.stage_id"
                    class="bar-item"
                  >
                    <div class="bar-label">{{ item.stage_name }}</div>
                    <div class="bar-wrapper">
                      <div
                        class="bar-fill"
                        :style="{
                          width: getAmountBarWidth(item.total_amount),
                          backgroundColor: getStageColor(item.stage_id)
                        }"
                      >
                        <span class="bar-value">{{ formatAmount(item.total_amount) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>

          <el-divider />

          <el-table
            :data="funnelData"
            :border="true"
            size="small"
            style="width: 100%"
          >
            <el-table-column prop="stage_name" label="阶段名称" width="150" />
            <el-table-column prop="opportunity_count" label="商机数量" width="100" align="right" />
            <el-table-column prop="total_amount" label="总金额" width="150" align="right">
              <template #default="{ row }">
                {{ formatAmount(row.total_amount) }}
              </template>
            </el-table-column>
            <el-table-column prop="average_amount" label="平均金额" width="150" align="right">
              <template #default="{ row }">
                {{ formatAmount(row.average_amount) }}
              </template>
            </el-table-column>
            <el-table-column prop="win_probability" label="赢率" width="100" align="right">
              <template #default="{ row }">
                {{ row.win_probability }}%
              </template>
            </el-table-column>
            <el-table-column label="占比" width="100" align="right">
              <template #default="{ row }">
                {{ getStagePercentage(row.opportunity_count) }}%
              </template>
            </el-table-column>
          </el-table>
        </div>

        <el-empty v-else description="添加商机，构建销售漏斗" />
      </div>
    </el-card>

    <el-card
      v-if="stageDurationData.length > 0"
      header="阶段耗时分析"
      :body-style="{ padding: '16px' }"
      style="margin-top: 16px"
    >
      <el-table
        :data="stageDurationData"
        :border="true"
        size="small"
        style="width: 100%"
      >
        <el-table-column prop="stage_name" label="阶段名称" width="200" />
        <el-table-column prop="avg_duration_days" label="平均停留天数" width="150" align="right">
          <template #default="{ row }">
            {{ row.avg_duration_days }} 天
          </template>
        </el-table-column>
        <el-table-column prop="min_duration_days" label="最短停留" width="150" align="right">
          <template #default="{ row }">
            {{ row.min_duration_days }} 天
          </template>
        </el-table-column>
        <el-table-column prop="max_duration_days" label="最长停留" width="150" align="right">
          <template #default="{ row }">
            {{ row.max_duration_days }} 天
          </template>
        </el-table-column>
        <el-table-column prop="opportunity_count" label="商机数量" width="120" align="right" />
        <el-table-column label="效率评估" width="150">
          <template #default="{ row }">
            <el-tag v-if="row.avg_duration_days <= 7" type="success">高效</el-tag>
            <el-tag v-else-if="row.avg_duration_days <= 14" type="primary">正常</el-tag>
            <el-tag v-else-if="row.avg_duration_days <= 30" type="warning">缓慢</el-tag>
            <el-tag v-else type="danger">瓶颈</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { opportunityApi, type SalesFunnelData, type StageDurationData } from '@/api/opportunity'

const loading = ref(false)
const funnelData = ref<SalesFunnelData[]>([])
const stageDurationData = ref<StageDurationData[]>([])
const dateRange = ref<any[]>([])

const fetchSalesFunnel = async () => {
  loading.value = true
  try {
    const params: any = {}
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = new Date(dateRange.value[0]).toISOString().split('T')[0]
      params.end_date = new Date(dateRange.value[1]).toISOString().split('T')[0]
    }
    
    const data = await opportunityApi.getSalesFunnel(params) as any
    funnelData.value = data
  } catch (error: any) {
    console.error('获取销售漏斗数据失败', error)
    ElMessage.error('获取销售漏斗数据失败')
  } finally {
    loading.value = false
  }
}

const fetchStageDuration = async () => {
  try {
    const params: any = {}
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = new Date(dateRange.value[0]).toISOString().split('T')[0]
      params.end_date = new Date(dateRange.value[1]).toISOString().split('T')[0]
    }
    
    const data = await opportunityApi.getStageDuration(params) as any
    stageDurationData.value = data
  } catch (error: any) {
    console.error('获取阶段耗时数据失败', error)
  }
}

const handleDateChange = () => {
  fetchSalesFunnel()
  fetchStageDuration()
}

const handleRefresh = () => {
  fetchSalesFunnel()
  fetchStageDuration()
}

const getMaxCount = () => {
  if (funnelData.value.length === 0) return 1
  return Math.max(...funnelData.value.map(item => item.opportunity_count))
}

const getMaxAmount = () => {
  if (funnelData.value.length === 0) return 1
  return Math.max(...funnelData.value.map(item => item.total_amount))
}

const getStageWidth = (count: number) => {
  if (funnelData.value.length === 0) return '100%'
  const max = getMaxCount()
  const percentage = (count / max) * 100
  return `${Math.max(percentage, 20)}%`
}

const getBarWidth = (count: number) => {
  if (funnelData.value.length === 0) return '0%'
  const max = getMaxCount()
  const percentage = (count / max) * 100
  return `${percentage}%`
}

const getAmountBarWidth = (amount: number) => {
  if (funnelData.value.length === 0) return '0%'
  const max = getMaxAmount()
  const percentage = (amount / max) * 100
  return `${percentage}%`
}

const getConversionRate = (index: number) => {
  if (index === 0) return 100
  const current = funnelData.value[index].opportunity_count
  const previous = funnelData.value[index - 1].opportunity_count
  if (previous === 0) return 0
  return ((current / previous) * 100).toFixed(1)
}

const getStagePercentage = (count: number) => {
  const total = funnelData.value.reduce((sum, item) => sum + item.opportunity_count, 0)
  if (total === 0) return 0
  return ((count / total) * 100).toFixed(1)
}

const getStageColor = (stageId: number) => {
  // 中性色梯度，低饱和，符合极简中性风设计规范
  const colors = ['#4A6FA5', '#5A7BA8', '#6A8BAB', '#7A9BAE', '#8AABB1', '#9ABBB4', '#AACBB7', '#BADBBA']
  const index = funnelData.value.findIndex(item => item.stage_id === stageId)
  return colors[index % colors.length]
}

const formatAmount = (amount: number) => {
  if (!amount) return '¥0'
  return `¥${(amount / 10000).toFixed(2)}万`
}

onMounted(() => {
  fetchSalesFunnel()
  fetchStageDuration()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.sales-funnel-container {
  padding: 0;
}

.funnel-content {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

.funnel-chart {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-card-padding;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
}

.funnel-stage {
  padding: $wolf-space-md $wolf-space-lg;
  background: $wolf-primary;
  border-radius: $wolf-radius-md;
  color: $wolf-text-inverse;
  box-shadow: $wolf-shadow-card;
  transition: all 0.2s ease;
  position: relative;
}

.funnel-stage:hover {
  transform: translateY(-2px);
  box-shadow: $wolf-shadow-hover;
}

.stage-info {
  text-align: center;
}

.stage-name {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  margin-bottom: $wolf-space-sm;
}

.stage-metrics {
  display: flex;
  justify-content: center;
  gap: $wolf-space-lg;
  flex-wrap: wrap;
}

.metric {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.metric .label {
  font-size: $wolf-font-size-caption;
  opacity: 0.9;
  margin-bottom: $wolf-space-xs;
}

.metric .value {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
}

.conversion-rate {
  position: absolute;
  right: -100px;
  top: 50%;
  transform: translateY(-50%);
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  white-space: nowrap;
}

.chart-container {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm;
}

.bar-item {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.bar-label {
  width: 120px;
  font-size: $wolf-font-size-body;
  color: $wolf-text-secondary;
  flex-shrink: 0;
}

.bar-wrapper {
  flex: 1;
  height: 28px;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-sm;
  overflow: hidden;
  position: relative;
}

.bar-fill {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: $wolf-space-sm;
  color: $wolf-text-inverse;
  font-size: $wolf-font-size-auxiliary;
  font-weight: $wolf-font-weight-medium;
  transition: width 0.3s ease;
}

.bar-value {
  white-space: nowrap;
}

.header-actions {
  display: flex;
  gap: $wolf-space-sm;
  align-items: center;
}
</style>
