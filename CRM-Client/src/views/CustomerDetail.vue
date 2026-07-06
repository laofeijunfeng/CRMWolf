<template>
  <div class="customer-detail-page">
    <div v-loading="loading" class="detail-layout">
      <!-- 左侧导航 -->
      <CustomerDetailSidebar
        :customer-id="customerId"
        @nav-change="handleNavChange"
        @show-add-follow-up="showAddFollowUpModal"
        @show-add-contact="showAddContactModal"
        @profile-toggle="handleProfileToggle"
      />

      <!-- 右侧内容区 -->
      <div class="detail-content">
        <div v-if="!customerDetail" class="empty-state">
          <el-empty description="客户信息加载失败，请刷新页面或稍后重试" />
        </div>

      <div v-else>
        <!-- ✅ Task 5: 客户档案面板（可折叠） -->
        <div
          v-show="activeTab === 'profile' || profileExpanded"
          class="profile-panel"
          :class="{ expanded: profileExpanded, collapsed: !profileExpanded }"
        >
          <!-- ✅ 收起时：只显示简化版客户名称卡片 -->
          <div v-if="!profileExpanded" class="customer-name-card-compact">
            <div class="customer-avatar">{{ customerDetail?.account_name?.charAt(0) || '客' }}</div>
            <div class="customer-info">
              <div class="customer-name">{{ customerDetail?.account_name }}</div>
              <div class="customer-status">
                <span :class="['status-tag', getStatusClass(customerDetail?.status)]">
                  {{ getStatusText(customerDetail?.status) }}
                </span>
              </div>
            </div>
          </div>

          <!-- ✅ 展开时：显示完整客户档案 -->
          <template v-else>
            <!-- 客户信息卡片 -->
            <div class="info-card">
          <div class="info-content">
            <!-- 上部分：标题和统计 -->
            <div class="info-top">
              <div class="info-left">
                <div class="title-section">
                  <div class="title-avatar">{{ customerDetail?.account_name?.charAt(0) || '客' }}</div>
                  <div class="title-content">
                    <h2 class="title-name">{{ customerDetail?.account_name }}</h2>
                    <div class="title-tags">
                      <span :class="['status-tag', getStatusClass(customerDetail?.status)]">
                        {{ getStatusText(customerDetail?.status) }}
                      </span>
                      <span v-if="customerDetail?.industry_info?.name" class="status-tag status-info">
                        {{ customerDetail.industry_info.name }}
                      </span>
                      <span v-if="customerDetail?.company_scale" class="status-tag status-default">
                        {{ customerDetail.company_scale }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="info-right">
                <div class="stats-section">
                  <div class="stat-item">
                    <div class="stat-label">联系人数</div>
                    <div class="stat-value">{{ customerDetail?.contacts?.length || 0 }} 人</div>
                  </div>
                </div>
              </div>
            </div>

            <div class="info-divider"></div>

            <!-- 下部分：属性网格 -->
            <div class="info-bottom">
              <div class="attributes-grid">
                <div class="attribute-item">
                  <div class="attribute-label">客户来源</div>
                  <span class="attribute-value">{{ customerDetail?.source || '-' }}</span>
                </div>

                <div class="attribute-item">
                  <div class="attribute-label">所在城市</div>
                  <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.city }">
                    {{ customerDetail?.city || '未填写' }}
                  </span>
                </div>

                <div class="attribute-item">
                  <div class="attribute-label">公司地址</div>
                  <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.address }">
                    {{ customerDetail?.address || '未填写' }}
                  </span>
                </div>

                <div class="attribute-item">
                  <div class="attribute-label">负责销售</div>
                  <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.owner_info?.name }">
                    {{ customerDetail?.owner_info?.name || '待分配' }}
                  </span>
                </div>

                <div class="attribute-item">
                  <div class="attribute-label">采购方式</div>
                  <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.default_procurement_method_info }">
                    {{ customerDetail?.default_procurement_method_info?.name || '未设置' }}
                  </span>
                </div>

                <div class="attribute-item">
                  <div class="attribute-label">创建人</div>
                  <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.creator_info?.name }">
                    {{ customerDetail?.creator_info?.name || '-' }}
                  </span>
                </div>

                <div class="attribute-item">
                  <div class="attribute-label">创建时间</div>
                  <span class="attribute-value">{{ formatDateTime(customerDetail?.created_time) }}</span>
                </div>

                <div class="attribute-item">
                  <div class="attribute-label">最后修改</div>
                  <span class="attribute-value">{{ formatDateTime(customerDetail?.last_modified_time) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 热力值卡片（紧凑布局） -->
        <div class="score-card-compact">
          <div class="score-mini-circle">
            <el-progress
              type="circle"
              :percentage="customerDetail?.score || 0"
              :color="getScoreColor(customerDetail?.score)"
              :width="60"
              :stroke-width="4"
            />
          </div>
          <div class="score-mini-info">
            <div class="score-mini-header">
              <span class="score-mini-icon">{{ getScoreIcon(customerDetail?.score) }}</span>
              <span class="score-mini-value">{{ customerDetail?.score ?? '--' }}</span>
              <span class="score-mini-level">{{ getScoreLevel(customerDetail?.score) }}</span>
            </div>
            <div class="score-mini-details">
              <span v-for="(detail, idx) in scoreDetails.slice(0, 2)" :key="detail.id" class="detail-mini-item">
                {{ detail.factor_name }}: <span :class="detail.score_change >= 0 ? 'pos' : 'neg'">{{ detail.score_change >= 0 ? '+' : '' }}{{ detail.score_change }}</span>
                <span v-if="idx < 1 && scoreDetails.length > 1"> · </span>
              </span>
              <el-button link size="small" @click="showScoreDetails = true" v-if="scoreDetails.length > 0">详情</el-button>
            </div>
          </div>
        </div>

        <!-- 客户档案卡片 -->
        <div class="profile-card">
          <div class="card-title">
            <span>客户档案</span>
            <div class="profile-status">
              <template v-if="customerDetail?.profile_status === 'PENDING'">
                <el-tag class="wolf-tag wolf-tag--gray" size="small">等待生成</el-tag>
              </template>
              <template v-else-if="customerDetail?.profile_status === 'GENERATING'">
                <el-tag class="wolf-tag wolf-tag--warning" size="small">
                  <el-icon class="is-loading"><Loading /></el-icon>
                  正在生成
                </el-tag>
              </template>
              <template v-else-if="customerDetail?.profile_status === 'COMPLETED'">
                <el-tag class="wolf-tag wolf-tag--success" size="small">生成完成</el-tag>
              </template>
              <template v-else-if="customerDetail?.profile_status === 'FAILED'">
                <el-tag class="wolf-tag wolf-tag--danger" size="small">生成失败</el-tag>
              </template>
            </div>
          </div>

          <!-- 生成中动画 -->
          <div v-if="customerDetail?.profile_status === 'GENERATING'" class="profile-generating">
            <div class="generating-animation">
              <div class="pulse-dot"></div>
              <div class="pulse-dot"></div>
              <div class="pulse-dot"></div>
            </div>
            <div class="generating-text">AI 正在分析客户信息，预计需要 10-30 秒</div>
          </div>

          <!-- 生成失败提示 -->
          <div v-if="customerDetail?.profile_status === 'FAILED'" class="profile-error">
            <div class="error-content">
              <el-icon class="error-icon"><WarningFilled /></el-icon>
              <span class="error-text">{{ customerDetail?.profile_error_message || '档案生成失败' }}</span>
            </div>
            <el-button type="primary" size="small" class="wolf-btn wolf-btn--primary-sm" @click="handleRegenerateProfile">
              重新生成
            </el-button>
          </div>

          <!-- 档案内容 -->
          <div v-if="customerDetail?.profile_status === 'COMPLETED'" class="profile-content">
            <div class="attributes-grid">
              <div class="attribute-item">
                <div class="attribute-label">所属行业</div>
                <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.industry_info?.name }">
                  {{ customerDetail?.industry_info?.name || customerDetail?.industry || '未识别' }}
                </span>
              </div>

              <div class="attribute-item">
                <div class="attribute-label">公司官网</div>
                <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.company_website }">
                  <template v-if="customerDetail?.company_website">
                    <a :href="customerDetail.company_website" target="_blank" class="link-value">
                      {{ customerDetail.company_website }}
                    </a>
                  </template>
                  <template v-else>未找到</template>
                </span>
              </div>
            </div>

            <div class="profile-section">
              <div class="section-label">企业背景</div>
              <div class="section-content" :class="{ 'not-filled': !customerDetail?.company_background }">
                {{ customerDetail?.company_background || '暂无信息' }}
              </div>
            </div>

            <div class="profile-section">
              <div class="section-label">主营业务</div>
              <div class="section-content" :class="{ 'not-filled': !customerDetail?.main_business }">
                {{ customerDetail?.main_business || '暂无信息' }}
              </div>
            </div>

            <div class="profile-section">
              <div class="section-label">同行业客户</div>
              <div class="section-content">
                <template v-if="parsedSimilarCustomers.length > 0">
                  <div class="similar-customers-list">
                    <span v-for="name in parsedSimilarCustomers" :key="name" class="similar-customer-tag">
                      {{ name }}
                    </span>
                  </div>
                </template>
                <template v-else>
                  <span class="not-filled">暂无匹配</span>
                </template>
              </div>
            </div>

            <div v-if="customerDetail?.project_background" class="profile-section">
              <div class="section-label">项目需求背景</div>
              <div class="section-content">
                {{ customerDetail.project_background }}
              </div>
            </div>

            <div class="profile-footer">
              <span class="generated-time">生成时间：{{ formatDateTime(customerDetail?.profile_generated_time) }}</span>
              <el-button type="primary" size="small" class="wolf-btn wolf-btn--primary-sm" @click="handleRegenerateProfile">
                重新生成
              </el-button>
            </div>
          </div>
        </div>
          </template>
        </div><!-- ✅ Task 5: profile-panel 结束 -->

        <!-- 内容面板区 -->
        <div class="content-panels">
          <!-- 客户跟进（操作时间线） -->
          <div v-show="activeTab === 'followup'" class="content-panel">
                <div class="follow-up-summary" v-if="followUps.length > 0 && lastFollowUp">
                  <div class="summary-item">
                    <div class="summary-label">最后跟进</div>
                    <div class="summary-value">
                      {{ formatDate(lastFollowUp.created_time) }}
                      <el-tag size="small" class="method-tag">{{ lastFollowUp.method }}</el-tag>
                    </div>
                  </div>
                  <div class="summary-item">
                    <div class="summary-label">下次跟进</div>
                    <div class="summary-value" :class="getNextFollowUpClass()">
                      <template v-if="lastFollowUp.next_follow_time">
                        <component :is="getNextFollowUpIcon()" style="margin-right: 4px" />
                        {{ getNextFollowUpText() }}
                      </template>
                      <template v-else>
                        <span style="color: #909399">未设置</span>
                      </template>
                    </div>
                  </div>
                  <div class="summary-item">
                    <div class="summary-label">总计跟进</div>
                    <div class="summary-value">{{ followUps.length }} 次</div>
                  </div>
                </div>

                <div class="panel-header">
                  <span>操作时间线</span>
                  <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="showAddFollowUpModal">
                    <el-icon><Plus /></el-icon>
                    添加跟进
                  </el-button>
                </div>

                <FollowUpList
                  :follow-ups="followUps"
                  :loading="loading"
                  :current-user-id="String(userStore.userInfo?.id)"
                  @delete="handleFollowUpDelete"
                />
              </div>

          <!-- 联系人 -->
          <div v-show="activeTab === 'contacts'" class="content-panel">
                <div class="panel-header">
                  <span>联系人</span>
                  <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="showAddContactModal">
                    <el-icon><Plus /></el-icon>
                    添加联系人
                  </el-button>
                </div>
                <el-table :data="customerDetail?.contacts || []" style="width: 100%">
                  <el-table-column prop="name" label="姓名" min-width="120" />
                  <el-table-column prop="position" label="职务" min-width="120">
                    <template #default="{ row }">
                      {{ row.position || '-' }}
                    </template>
                  </el-table-column>
                  <el-table-column prop="mobile" label="手机" min-width="140" />
                  <el-table-column prop="email" label="邮箱" min-width="180">
                    <template #default="{ row }">
                      {{ row.email || '-' }}
                    </template>
                  </el-table-column>
                  <el-table-column prop="is_decision_maker" label="决策人" width="100">
                    <template #default="{ row }">
                      <el-tag v-if="row.is_decision_maker" :class="['wolf-tag', 'wolf-tag--warning']" size="small">是</el-tag>
                      <el-tag v-else :class="['wolf-tag', 'wolf-tag--gray']" size="small">否</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="is_primary" label="主联系人" width="120">
                    <template #default="{ row }">
                      <el-tag v-if="row.is_primary" :class="['wolf-tag', 'wolf-tag--primary']" size="small">是</el-tag>
                      <el-tag v-else :class="['wolf-tag', 'wolf-tag--gray']" size="small">否</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="200" fixed="right">
                    <template #default="{ row }">
                      <div class="wolf-table-actions">
                        <el-button
                          type="primary"
                          size="small"
                          class="wolf-btn wolf-btn--primary-sm"
                          @click="handleEditContact(row)"
                        >
                          编辑
                        </el-button>
                        <el-button
                          v-if="!row.is_primary"
                          type="text"
                          size="small"
                          class="wolf-btn wolf-btn--text"
                          @click="handleContactAction('setPrimary', row)"
                        >
                          设为主联系人
                        </el-button>
                        <el-button
                          type="text"
                          size="small"
                          class="wolf-btn wolf-btn--text-danger"
                          @click="handleContactAction('delete', row)"
                        >
                          删除
                        </el-button>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
              </div>

          <!-- 商机 -->
          <div v-show="activeTab === 'opportunities'" class="content-panel">
                <div class="panel-header">
                  <span>商机列表</span>
                  <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="handleCreateOpportunity">
                    <el-icon><Plus /></el-icon>
                    新建商机
                  </el-button>
                </div>
                <div v-loading="opportunitiesLoading" class="loading-container">
                  <div v-if="opportunities.length === 0" class="empty-opportunities">
                    <el-empty description="创建商机，追踪销售进展" />
                  </div>
                  <div v-else class="opportunities-list">
                    <div
                      v-for="item in opportunities"
                      :key="item.id"
                      class="opportunity-item"
                      @click="handleViewOpportunityDetail(item)"
                    >
                      <div class="opportunity-header">
                        <div class="opportunity-name">{{ item.opportunity_name }}</div>
                        <el-tag v-if="item.status === 0" :class="['wolf-tag', 'wolf-tag--primary']" size="small">跟进中</el-tag>
                        <el-tag v-else-if="item.status === 1" :class="['wolf-tag', 'wolf-tag--success']" size="small">已赢单</el-tag>
                        <el-tag v-else-if="item.status === 2" :class="['wolf-tag', 'wolf-tag--danger']" size="small">已输单</el-tag>
                      </div>
                      <div class="opportunity-info">
                        <div class="info-item">
                          <el-icon class="info-icon"><Money /></el-icon>
                          <span>{{ formatAmount(item.total_amount) }}</span>
                        </div>
                        <div class="info-item">
                          <el-icon class="info-icon"><Calendar /></el-icon>
                          <span>{{ formatDate(item.expected_closing_date) }}</span>
                        </div>
                        <div class="info-item">
                          <el-icon class="info-icon"><PriceTag /></el-icon>
                          <span>{{ item.stage_name || '-' }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

          <!-- 合同 -->
          <div v-show="activeTab === 'contracts'" class="content-panel">
                <div class="panel-header">
                  <span>合同列表</span>
                  <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="handleCreateContract">
                    <el-icon><Plus /></el-icon>
                    新建合同
                  </el-button>
                </div>
                <div v-loading="contractsLoading" class="loading-container">
                  <div v-if="contracts.length === 0" class="empty-placeholder">
                    <el-empty description="创建合同，管理签约流程" />
                  </div>
                  <div v-else class="contract-list">
                    <div
                      v-for="item in contracts"
                      :key="item.id"
                      class="contract-item"
                      @click="router.push(`/contracts/${item.id}`)"
                    >
                      <div class="contract-item-header">
                        <div class="contract-name">{{ item.contract_name }}</div>
                        <el-tag :class="['wolf-tag', getContractStatusClass(item.status)]" size="small">
                          {{ item.status_info?.name || getContractStatusText(item.status) }}
                        </el-tag>
                      </div>
                      <div class="contract-item-meta">
                        <span class="meta-item">
                          <el-icon><Document /></el-icon>
                          {{ item.contract_number }}
                        </span>
                        <span class="meta-item">
                          <el-icon><Money /></el-icon>
                          {{ formatAmount(item.total_amount) }}
                        </span>
                        <span class="meta-item">
                          <el-icon><Calendar /></el-icon>
                          {{ item.expiry_date || '无到期日期' }}
                        </span>
                      </div>
                      <div class="contract-item-tags">
                        <el-tag :class="['wolf-tag', 'wolf-tag--info']" size="small">
                          {{ item.license_type_name || getLicenseTypeText(item.license_type) }}
                        </el-tag>
                        <el-tag v-if="item.license_type === 'SUBSCRIPTION'" :class="['wolf-tag', 'wolf-tag--primary']" size="small">
                          {{ item.subscription_years ? `${item.subscription_years}年` : '订阅' }}
                        </el-tag>
                        <el-tag :class="['wolf-tag', 'wolf-tag--success']" size="small">
                          {{ item.user_count }}人
                        </el-tag>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

          <!-- 回款 -->
          <div v-show="activeTab === 'payments'" class="content-panel">
                <div class="panel-header">
                  <span>回款计划</span>
                  <el-button type="primary" class="wolf-btn wolf-btn--primary-sm">
                    <el-icon><Plus /></el-icon>
                    新建回款计划
                  </el-button>
                </div>
                <div v-loading="paymentPlansLoading" class="loading-container">
                  <div v-if="paymentPlans.length === 0" class="empty-placeholder">
                    <el-empty description="创建回款计划，追踪回款进度" />
                  </div>
                  <div v-else class="payment-list">
                    <div v-for="item in paymentPlans" :key="item.id" class="payment-item">
                      <div class="payment-item-header">
                        <div class="stage-name">{{ item.stage_name }}</div>
                        <el-tag :class="['wolf-tag', getPaymentStatusClass(item.status)]" size="small">
                          {{ item.status_name || '未设置' }}
                        </el-tag>
                      </div>
                      <div class="payment-item-info">
                        <div class="attributes-grid">
                          <div class="attribute-item">
                            <div class="attribute-header">
                              <el-icon class="attribute-icon"><Coin /></el-icon>
                              <span class="attribute-label">计划金额</span>
                            </div>
                            <span class="attribute-value">{{ formatAmount(String(item.planned_amount)) }}</span>
                          </div>
                          <div class="attribute-item">
                            <div class="attribute-header">
                              <el-icon class="attribute-icon"><CircleCheckFilled /></el-icon>
                              <span class="attribute-label">已回款</span>
                            </div>
                            <span class="attribute-value">{{ formatAmount(String(item.paid_amount || 0)) }}</span>
                          </div>
                          <div class="attribute-item">
                            <div class="attribute-header">
                              <el-icon class="attribute-icon"><Clock /></el-icon>
                              <span class="attribute-label">待回款</span>
                            </div>
                            <span class="attribute-value">{{ formatAmount(String(item.remaining_amount || 0)) }}</span>
                          </div>
                          <div class="attribute-item">
                            <div class="attribute-header">
                              <el-icon class="attribute-icon"><Document /></el-icon>
                              <span class="attribute-label">开票状态</span>
                            </div>
                            <span class="attribute-value">{{ item.invoice_status_name || '未开票' }}</span>
                          </div>
                          <div class="attribute-item">
                            <div class="attribute-header">
                              <el-icon class="attribute-icon"><Calendar /></el-icon>
                              <span class="attribute-label">计划日期</span>
                            </div>
                            <span class="attribute-value">{{ item.due_date }}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

          <!-- 发票 -->
          <div v-show="activeTab === 'invoices'" class="content-panel">
                <!-- 发票抬头列表 -->
                <div class="invoice-titles-section">
                  <div class="section-title">
                    <span>发票抬头</span>
                    <el-button class="wolf-btn wolf-btn--primary-sm" @click="showInvoiceTitleModal">
                      <el-icon><Plus /></el-icon>
                      添加抬头
                    </el-button>
                  </div>
                  <div v-loading="invoiceTitlesLoading" class="loading-container">
                    <div v-if="invoiceTitles.length === 0" class="empty-placeholder">
                      <el-empty description="添加发票抬头，便于开票申请" />
                    </div>
                    <div v-else class="invoice-tiles-list">
                      <div
                        v-for="title in invoiceTitles"
                        :key="title.id"
                        class="invoice-title-item"
                        :class="{ 'is-default': title.is_default }"
                        @click="editInvoiceTitle(title)"
                      >
                        <div class="title-content">
                          <div class="title-main">
                            <div class="title-name">{{ title.title }}</div>
                            <el-tag v-if="title.is_default" type="success" size="small">默认</el-tag>
                            <el-tag :type="title.title_type === 'COMPANY' ? 'primary' : 'info'" size="small">
                              {{ title.title_type === 'COMPANY' ? '单位' : '个人' }}
                            </el-tag>
                          </div>
                          <div class="title-details">
                            <div class="detail-row">
                              <span class="detail-label">纳税人识别号</span>
                              <span class="detail-value">{{ title.taxpayer_id }}</span>
                            </div>
                            <div v-if="title.bank_name" class="detail-row">
                              <span class="detail-label">开户行</span>
                              <span class="detail-value">{{ title.bank_name }}</span>
                            </div>
                            <div v-if="title.bank_account" class="detail-row">
                              <span class="detail-label">开户账号</span>
                              <span class="detail-value">{{ title.bank_account }}</span>
                            </div>
                            <div v-if="title.address" class="detail-row">
                              <span class="detail-label">开票地址</span>
                              <span class="detail-value">{{ title.address }}</span>
                            </div>
                            <div v-if="title.phone" class="detail-row">
                              <span class="detail-label">电话</span>
                              <span class="detail-value">{{ title.phone }}</span>
                            </div>
                          </div>
                        </div>
                        <div class="title-actions">
                          <el-button class="wolf-btn wolf-btn--primary-sm" @click.stop="createInvoice(title)">
                            <el-icon><Plus /></el-icon>
                            申请发票
                          </el-button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 发票列表 -->
                <div class="invoice-list-section">
                  <div class="section-title">
                    <span>发票列表</span>
                  </div>
                  <div v-loading="invoicesLoading" class="loading-container">
                    <div v-if="invoices.length === 0" class="empty-placeholder">
                      <el-empty description="申请发票，管理开票流程" />
                    </div>
                    <div v-else class="invoice-list">
                      <div v-for="item in invoices" :key="item.id" class="invoice-item" @click="goToInvoiceDetail(item.id)">
                        <div class="invoice-item-header">
                          <div class="invoice-title">{{ item.application_number }}</div>
                          <el-tag :class="['wolf-tag', getInvoiceStatusClass(item.status)]" size="small">
                            {{ getInvoiceStatusText(item.status) }}
                          </el-tag>
                        </div>
                        <div class="invoice-item-info">
                          <div class="attributes-grid">
                            <div class="attribute-item">
                              <div class="attribute-header">
                                <el-icon class="attribute-icon"><Document /></el-icon>
                                <span class="attribute-label">发票类型</span>
                              </div>
                              <span class="attribute-value">{{ getInvoiceTypeText(item.invoice_type) }}</span>
                            </div>
                            <div class="attribute-item">
                              <div class="attribute-header">
                                <el-icon class="attribute-icon"><Money /></el-icon>
                                <span class="attribute-label">开票金额</span>
                              </div>
                              <span class="attribute-value">{{ formatAmount(item.invoice_amount) }}</span>
                            </div>
                            <div v-if="item.contract_name" class="attribute-item">
                              <div class="attribute-header">
                                <el-icon class="attribute-icon"><ShoppingCart /></el-icon>
                                <span class="attribute-label">关联合同</span>
                              </div>
                              <span class="attribute-value">{{ item.contract_name }}</span>
                            </div>
                            <div v-if="item.stage_name" class="attribute-item">
                              <div class="attribute-header">
                                <el-icon class="attribute-icon"><Clock /></el-icon>
                                <span class="attribute-label">回款阶段</span>
                              </div>
                              <span class="attribute-value">{{ item.stage_name }}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
        </div>
      </div>
    </div>

  <el-dialog
      v-model="addContactModalVisible"
      title="添加联系人"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="contactForm" :rules="contactFormRules" label-position="top" ref="contactFormRef">
        <el-form-item prop="name" label="姓名" required>
          <el-input v-model="contactForm.name" placeholder="请输入联系人姓名" />
        </el-form-item>
        <el-form-item prop="gender" label="性别">
          <el-radio-group v-model="contactForm.gender">
            <el-radio value="0">未知</el-radio>
            <el-radio value="1">男</el-radio>
            <el-radio value="2">女</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item prop="position" label="职务">
          <el-input v-model="contactForm.position" placeholder="请输入职务" />
        </el-form-item>
        <el-form-item prop="mobile" label="手机号" required>
          <el-input v-model="contactForm.mobile" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item prop="email" label="邮箱">
          <el-input v-model="contactForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item prop="wechat_id" label="微信ID">
          <el-input v-model="contactForm.wechat_id" placeholder="请输入微信ID" />
        </el-form-item>
        <el-form-item prop="is_decision_maker" label="关键决策人">
          <el-switch v-model="contactForm.is_decision_maker" />
        </el-form-item>
        <el-form-item prop="remark" label="备注">
          <el-input v-model="contactForm.remark" type="textarea" placeholder="请输入备注" :maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addContactModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAddContactOk">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="editContactModalVisible"
      title="编辑联系人"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="editContactForm" :rules="contactFormRules" label-position="top" ref="editContactFormRef">
        <el-form-item prop="name" label="姓名" required>
          <el-input v-model="editContactForm.name" placeholder="请输入联系人姓名" />
        </el-form-item>
        <el-form-item prop="gender" label="性别">
          <el-radio-group v-model="editContactForm.gender">
            <el-radio value="0">未知</el-radio>
            <el-radio value="1">男</el-radio>
            <el-radio value="2">女</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item prop="position" label="职务">
          <el-input v-model="editContactForm.position" placeholder="请输入职务" />
        </el-form-item>
        <el-form-item prop="mobile" label="手机号" required>
          <el-input v-model="editContactForm.mobile" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item prop="email" label="邮箱">
          <el-input v-model="editContactForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item prop="wechat_id" label="微信ID">
          <el-input v-model="editContactForm.wechat_id" placeholder="请输入微信ID" />
        </el-form-item>
        <el-form-item prop="is_decision_maker" label="关键决策人">
          <el-switch v-model="editContactForm.is_decision_maker" />
        </el-form-item>
        <el-form-item prop="remark" label="备注">
          <el-input v-model="editContactForm.remark" type="textarea" placeholder="请输入备注" :maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editContactModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleEditContactOk">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="addFollowUpModalVisible"
      title="添加跟进记录"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="followUpForm" :rules="followUpFormRules" label-position="top" ref="followUpFormRef">
        <el-form-item prop="method" label="跟进方式" required>
          <el-radio-group v-model="followUpForm.method">
            <el-radio value="电话">电话</el-radio>
            <el-radio value="微信">微信</el-radio>
            <el-radio value="拜访">拜访</el-radio>
            <el-radio value="邮件">邮件</el-radio>
            <el-radio value="其他">其他</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item prop="content" label="跟进内容" required>
          <el-input
            v-model="followUpForm.content"
            type="textarea"
            placeholder="请输入跟进内容"
            :maxlength="500"
            :rows="4"
            show-word-limit
          />
        </el-form-item>
        <el-form-item prop="next_follow_time" label="下次跟进时间">
          <el-date-picker
            v-model="followUpForm.next_follow_time"
            type="datetime"
            placeholder="请选择下次跟进时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item prop="next_action" label="下一步动作">
          <el-input
            v-model="followUpForm.next_action"
            type="textarea"
            placeholder="请输入下一步动作计划"
            :maxlength="200"
            :rows="2"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addFollowUpModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAddFollowUpOk">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="invoiceTitleFormVisible"
      :title="isEditingTitle ? '编辑发票抬头' : '添加发票抬头'"
      width="600px"
      :close-on-click-modal="false"
      class="invoice-title-form-dialog"
    >
      <el-form :model="invoiceTitleForm" :rules="invoiceTitleFormRules" label-width="120px" ref="invoiceTitleFormRef">
        <el-form-item prop="title_type" label="抬头类型" required>
          <el-radio-group v-model="invoiceTitleForm.title_type">
            <el-radio value="COMPANY">单位</el-radio>
            <el-radio value="PERSONAL">个人</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item prop="title" label="开票抬头" required>
          <el-input v-model="invoiceTitleForm.title" placeholder="请输入开票抬头" :maxlength="255" show-word-limit />
        </el-form-item>

        <el-form-item prop="taxpayer_id" label="纳税人识别号" required>
          <el-input v-model="invoiceTitleForm.taxpayer_id" placeholder="请输入纳税人识别号" :maxlength="100" />
        </el-form-item>

        <el-form-item prop="bank_name" label="开户行">
          <el-input v-model="invoiceTitleForm.bank_name" placeholder="选填" :maxlength="255" />
        </el-form-item>

        <el-form-item prop="bank_account" label="开户账号">
          <el-input v-model="invoiceTitleForm.bank_account" placeholder="选填" :maxlength="100" />
        </el-form-item>

        <el-form-item prop="address" label="开票地址">
          <el-input v-model="invoiceTitleForm.address" placeholder="选填" :maxlength="500" show-word-limit />
        </el-form-item>

        <el-form-item prop="phone" label="电话">
          <el-input v-model="invoiceTitleForm.phone" placeholder="选填" :maxlength="50" />
        </el-form-item>

        <el-form-item prop="is_default" label="设为默认">
          <el-switch v-model="invoiceTitleForm.is_default" />
          <span class="form-item-hint">开启后将自动取消原有的默认抬头</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <div class="dialog-footer-left">
            <el-button v-if="isEditingTitle" type="danger" class="wolf-btn wolf-btn--danger" @click="handleDeleteInvoiceTitle">
              删除
            </el-button>
          </div>
          <div class="dialog-footer-right">
            <el-button @click="invoiceTitleFormVisible = false">取消</el-button>
            <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleSaveInvoiceTitle">
              保存
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 热力值明细弹窗 -->
    <el-dialog v-model="showScoreDetails" title="热力值计算明细" width="600px">
      <el-table :data="scoreDetails" stripe>
        <el-table-column prop="factor_name" label="因子" width="150" />
        <el-table-column prop="actual_value" label="实际值" width="120">
          <template #default="{ row }">
            {{ row.actual_value || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="weight_value" label="权重" width="80" />
        <el-table-column label="分数变化" width="100">
          <template #default="{ row }">
            <span :class="row.score_change >= 0 ? 'positive' : 'negative'">
              {{ row.score_change >= 0 ? '+' : '' }}{{ row.score_change }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="原因说明">
          <template #default="{ row }">
            {{ row.reason || '-' }}
          </template>
        </el-table-column>
      </el-table>
      <div v-if="scoreDetails.length === 0" class="score-details-empty">
        <el-empty description="计算热力值，评估客户活跃度" />
      </div>
    </el-dialog>
    </div><!-- detail-content -->
  </div><!-- detail-layout -->
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Plus,
  CircleCheck,
  CircleClose,
  Clock,
  Calendar,
  PriceTag,
  Money,
  Coin,
  ShoppingCart,
  Document,
  Loading,
  WarningFilled
} from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import FollowUpList from '@/components/FollowUpList.vue'
import CustomerDetailSidebar from '@/components/CustomerDetailSidebar.vue'
import customerApi, { type CustomerDetailResponse, type ContactCreate, type ContactUpdate } from '@/api/customer'
import customerFollowUpApi, { type CustomerFollowUpCreate, type CustomerFollowUpResponse } from '@/api/customerFollowUp'
import { opportunityApi, type Opportunity } from '@/api/opportunity'
import invoiceApi from '@/api/invoice'
import { getCustomerScore, getScoreIcon, getScoreColor, getScoreLevel, type ScoreDetail } from '@/api/score'
import { useUserStore } from '@/stores/user'
import { useHeaderStore } from '@/stores/header'
import type { HeaderAction } from '@/stores/header'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const headerStore = useHeaderStore()

onMounted(() => {
  headerStore.setBack(true, '/customers')
})

onUnmounted(() => {
  headerStore.clear()
})

const customerId = ref<number>(parseInt(route.params['id'] as string))
const customerDetail = ref<CustomerDetailResponse | null>(null)
const loading = ref(false)
const followUps = ref<CustomerFollowUpResponse[]>([])
const selectedContact = ref<any>(null)

// 热力值相关
const showScoreDetails = ref(false)
const scoreDetails = ref<ScoreDetail[]>([])

// ✅ Task 4: 智能折叠状态
const profileExpanded = ref<boolean>(true)  // 默认：展开
const userExpandedProfile = ref<boolean>(false)  // 用户是否手动展开过

const activeTab = ref('profile')  // ✅ Task 4: 默认激活客户档案

// 导航切换处理（✅ Task 4: 添加智能折叠逻辑）
const handleNavChange = (navKey: string): void => {
  activeTab.value = navKey

  // ✅ 智能折叠逻辑：
  // - 馰次切换：自动收起客户档案（节省空间）
  // - 用户手动展开后：不自动收起（尊重用户控制权）
  if (navKey !== 'profile' && !userExpandedProfile.value) {
    profileExpanded.value = false  // 自动收起
  }
}

// ✅ Task 4: 监听客户档案展开/收起（来自 CustomerDetailSidebar）
const handleProfileToggle = (expanded: boolean): void => {
  profileExpanded.value = expanded

  // ✅ 记录用户是否手动展开
  if (expanded) {
    userExpandedProfile.value = true
  }
}

const handleFollowUpDelete = async (followUp: { id: number }) => {
  try {
    await customerFollowUpApi.deleteFollowUp(followUp['id'])
    showSuccess('删除', '跟进记录')
    await fetchFollowUps()
  } catch (error: unknown) {
    showError(error, '删除跟进记录')
  }
}

const lastFollowUp = computed(() => {
  return followUps.value.length > 0 ? followUps.value[0] : null
})

const parsedSimilarCustomers = computed(() => {
  if (!customerDetail.value?.similar_customers) return []
  try {
    const parsed = JSON.parse(customerDetail.value.similar_customers)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
})

const handleRegenerateProfile = async () => {
  try {
    loading.value = true
    await customerApi.regenerateProfile(customerId.value)
    showSuccess('重新生成', '客户档案')
    // Refresh customer detail to show GENERATING status
    await fetchCustomerDetail()
  } catch (error: unknown) {
    showError(error, '重新生成客户档案')
  } finally {
    loading.value = false
  }
}

const getNextFollowUpClass = () => {
  if (!lastFollowUp.value?.next_follow_time) return ''
  const nextTime = new Date(lastFollowUp.value.next_follow_time)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const tomorrow = new Date(today)
  tomorrow.setDate(tomorrow.getDate() + 1)

  if (nextTime < today) return 'overdue'
  if (nextTime <= tomorrow) return 'today'
  return 'future'
}

const getNextFollowUpIcon = () => {
  const statusClass = getNextFollowUpClass()
  if (statusClass === 'overdue') return CircleClose
  if (statusClass === 'today') return Clock
  return CircleCheck
}

const getNextFollowUpText = () => {
  if (!lastFollowUp.value?.next_follow_time) return ''
  const nextTime = new Date(lastFollowUp.value.next_follow_time)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const tomorrow = new Date(today)
  tomorrow.setDate(tomorrow.getDate() + 1)

  if (nextTime < today) {
    const daysOverdue = Math.floor((today.getTime() - nextTime.getTime()) / (1000 * 60 * 60 * 24))
    return `已超期 ${daysOverdue} 天`
  }

  if (nextTime <= tomorrow) {
    return '今日需跟进'
  }

  const daysUntil = Math.floor((nextTime.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
  return `还有 ${daysUntil} 天`
}

const addContactModalVisible = ref(false)
const contactFormRef = ref()
const contactForm = reactive<ContactCreate>({
  name: '',
  gender: '0',
  position: '',
  mobile: '',
  email: '',
  wechat_id: '',
  is_decision_maker: false,
  remark: ''
})

const editContactModalVisible = ref(false)
const editContactFormRef = ref()
const editContactForm = reactive<ContactUpdate>({
  name: '',
  gender: '0',
  position: '',
  mobile: '',
  email: '',
  wechat_id: '',
  is_decision_maker: false,
  remark: ''
})

const contactFormRules = {
  name: [{ required: true, message: '请输入联系人姓名', trigger: 'blur' }],
  mobile: [{ required: true, message: '请输入手机号', trigger: 'blur' }]
}

const addFollowUpModalVisible = ref(false)
const followUpFormRef = ref()
const followUpForm = reactive<CustomerFollowUpCreate>({
  method: '电话',
  content: '',
  next_follow_time: '',
  next_action: ''
})

const followUpFormRules = {
  method: [{ required: true, message: '请选择跟进方式', trigger: 'change' }],
  content: [{ required: true, message: '请输入跟进内容', trigger: 'blur' }]
}

const opportunities = ref<Opportunity[]>([])
const opportunitiesLoading = ref(false)

const contracts = ref<any[]>([])
const contractsLoading = ref(false)

const paymentPlans = ref<any[]>([])
const paymentPlansLoading = ref(false)

const invoices = ref<any[]>([])
const invoicesLoading = ref(false)

const invoiceTitles = ref<any[]>([])
const invoiceTitlesLoading = ref(false)
const invoiceTitleFormVisible = ref(false)
const isEditingTitle = ref(false)
const currentEditTitleId = ref<number | null>(null)
const invoiceTitleFormRef = ref()

const invoiceTitleForm = reactive({
  title_type: 'COMPANY' as 'COMPANY' | 'PERSONAL',
  title: '',
  taxpayer_id: '',
  bank_name: '',
  bank_account: '',
  address: '',
  phone: '',
  is_default: false
})

const invoiceTitleFormRules = {
  title_type: [{ required: true, message: '请选择抬头类型' }],
  title: [
    { required: true, message: '请输入开票抬头' },
    { min: 1, max: 255, message: '开票抬头长度为1-255个字符' }
  ],
  taxpayer_id: [
    { required: true, message: '请输入纳税人识别号' },
    { min: 1, max: 100, message: '纳税人识别号长度为1-100个字符' }
  ]
}

const fetchCustomerDetail = async () => {
  try {
    const data = await customerApi.getCustomerDetail(customerId.value)
    customerDetail.value = data

    // 获取热力值明细
    if (data?.score !== null) {
      try {
        const scoreRes = await getCustomerScore(customerId.value)
        scoreDetails.value = scoreRes.details || []
      } catch {
        // 热力值明细获取失败不影响主流程
        scoreDetails.value = []
      }
    }
  } catch (error: unknown) {
    console.error('获取客户详情失败', error)
    showError(error, '获取客户详情')
  }
}

const fetchFollowUps = async () => {
  try {
    const data = await customerFollowUpApi.getFollowUps(customerId.value)
    followUps.value = Array.isArray(data) ? data : (data.data || [])
  } catch (error: unknown) {
    console.error('获取跟进记录失败', error)
  }
}

const fetchContracts = async () => {
  try {
    contractsLoading.value = true
    const data = await customerApi.getContracts(customerId.value)
    contracts.value = data || []
  } catch (error: unknown) {
    console.error('获取合同列表失败', error)
    showError(error, '获取合同列表')
  } finally {
    contractsLoading.value = false
  }
}

const fetchPaymentPlans = async () => {
  try {
    paymentPlansLoading.value = true
    const data = await customerApi.getPaymentPlans(customerId.value)
    paymentPlans.value = data || []
  } catch (error: unknown) {
    console.error('获取回款计划失败', error)
    showError(error, '获取回款计划')
  } finally {
    paymentPlansLoading.value = false
  }
}

const fetchInvoices = async () => {
  try {
    invoicesLoading.value = true
    const data = await customerApi.getInvoices(customerId.value)
    invoices.value = data || []
  } catch (error: unknown) {
    console.error('获取发票列表失败', error)
    showError(error, '获取发票列表')
  } finally {
    invoicesLoading.value = false
  }
}

const fetchInvoiceTitles = async () => {
  try {
    invoiceTitlesLoading.value = true
    const data = await invoiceApi.getInvoiceTitles(customerId.value)
    invoiceTitles.value = data?.invoice_titles || []
  } catch (error: unknown) {
    console.error('获取发票抬头列表失败', error)
    showError(error, '获取发票抬头列表')
  } finally {
    invoiceTitlesLoading.value = false
  }
}

const getContractStatusClass = (status: string) => {
  const statusMap: Record<string, string> = {
    '草稿': 'wolf-tag--gray',
    '待审批': 'wolf-tag--warning',
    '已驳回': 'wolf-tag--danger',
    '生效中': 'wolf-tag--success',
    '已完成': 'wolf-tag--primary',
    '已终止': 'wolf-tag--danger'
  }
  return statusMap[status] || 'wolf-tag--gray'
}

const getContractStatusText = (status: string) => {
  return status || '未知'
}

const getLicenseTypeText = (type: string) => {
  const typeMap: Record<string, string> = {
    'SUBSCRIPTION': '订阅制',
    'PERPETUAL': '买断制'
  }
  return typeMap[type] || type
}

const getPaymentStatusClass = (status: string) => {
  const statusMap: Record<string, string> = {
    '待回款': 'wolf-tag--warning',
    '已逾期': 'wolf-tag--danger',
    '部分回款': 'wolf-tag--info',
    '已完成': 'wolf-tag--success'
  }
  return statusMap[status] || 'wolf-tag--gray'
}

const getInvoiceStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    'DRAFT': '草稿',
    'PENDING_REVIEW': '待审批',
    'APPROVED': '已通过',
    'REJECTED': '已驳回',
    'ISSUED': '已开票'
  }
  return statusMap[status] || status || '未知'
}

const getInvoiceStatusClass = (status: string) => {
  const statusMap: Record<string, string> = {
    'DRAFT': 'wolf-tag--gray',
    'PENDING_REVIEW': 'wolf-tag--warning',
    'APPROVED': 'wolf-tag--success',
    'REJECTED': 'wolf-tag--danger',
    'ISSUED': 'wolf-tag--primary'
  }
  return statusMap[status] || 'wolf-tag--gray'
}

const getInvoiceTypeText = (type: string) => {
  const typeMap: Record<string, string> = {
    'VAT_SPECIAL': '增值税专用发票',
    'VAT_NORMAL': '普通发票'
  }
  return typeMap[type] || type || '未知'
}

const showInvoiceTitleModal = () => {
  isEditingTitle.value = false
  currentEditTitleId.value = null
  Object.assign(invoiceTitleForm, {
    title_type: 'COMPANY',
    title: '',
    taxpayer_id: '',
    bank_name: '',
    bank_account: '',
    address: '',
    phone: '',
    is_default: false
  })
  invoiceTitleFormVisible.value = true
}

const editInvoiceTitle = (title: { id: number }) => {
  isEditingTitle.value = true
  currentEditTitleId.value = title.id
  Object.assign(invoiceTitleForm, {
    title_type: title.title_type,
    title: title.title,
    taxpayer_id: title.taxpayer_id,
    bank_name: title.bank_name || '',
    bank_account: title.bank_account || '',
    address: title.address || '',
    phone: title.phone || '',
    is_default: title.is_default || false
  })
  invoiceTitleFormVisible.value = true
}

const handleSaveInvoiceTitle = async () => {
  try {
    await invoiceTitleFormRef.value?.validate()
    
    if (isEditingTitle.value && currentEditTitleId.value) {
      await invoiceApi.updateInvoiceTitle(currentEditTitleId.value, {
        title_type: invoiceTitleForm.title_type,
        title: invoiceTitleForm.title,
        taxpayer_id: invoiceTitleForm.taxpayer_id,
        bank_name: invoiceTitleForm.bank_name || null,
        bank_account: invoiceTitleForm.bank_account || null,
        address: invoiceTitleForm.address || null,
        phone: invoiceTitleForm.phone || null,
        is_default: invoiceTitleForm.is_default
      })
      showSuccess('更新', '发票抬头')
    } else {
      const { is_default, ...createData } = invoiceTitleForm
      const result = await invoiceApi.createInvoiceTitle(customerId.value, createData)
      
      if (is_default && result?.id) {
        await invoiceApi.setDefaultInvoiceTitle(result.id)
      }
      
      showSuccess('添加', '发票抬头')
    }
    
    invoiceTitleFormVisible.value = false
    await fetchInvoiceTitles()
  } catch (error: unknown) {
    if (error?.response?.data?.detail) {
      showError(error, '保存发票抬头')
    } else if (error?.message) {
      showError(error, '保存发票抬头')
    } else {
      console.error('保存失败', error)
      showError(new Error('保存失败'), '发票抬头')
    }
  }
}

const handleDeleteInvoiceTitle = async () => {
  if (!currentEditTitleId.value) return
  
  try {
    await ElMessageBox.confirm(
      '确定要删除该发票抬头吗？',
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await invoiceApi.deleteInvoiceTitle(currentEditTitleId.value)
    showSuccess('删除', '跟进记录')
    invoiceTitleFormVisible.value = false
    await fetchInvoiceTitles()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message === 'cancel') return
    console.error('删除发票抬头失败', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '删除发票抬头')
  }
}

const createInvoice = (title: { id: number }) => {
  router.push({
    name: 'InvoiceCreate',
    query: {
      customer_id: customerId.value,
      invoice_title_id: title.id
    }
  })
}

const goToInvoiceDetail = (invoiceId: number) => {
  router.push({
    name: 'InvoiceDetail',
    params: {
      id: invoiceId
    }
  })
}

const showAddContactModal = () => {
  Object.assign(contactForm, {
    name: '',
    gender: '0',
    position: '',
    mobile: '',
    email: '',
    wechat_id: '',
    is_decision_maker: false,
    remark: ''
  })
  addContactModalVisible.value = true
}

const handleAddContactOk = async () => {
  try {
    await contactFormRef.value?.validate()
    await customerApi.createContact(customerId.value, contactForm)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('添加', '联系人')
    addContactModalVisible.value = false
    await fetchCustomerDetail()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message) {
      console.error('[CustomerDetail] handleAddContactOk error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '添加联系人')
    }
  }
}

const handleEditContact = (record: { id: number }) => {
  Object.assign(editContactForm, {
    ...record,
    gender: record.gender?.toString() || '0'
  })
  selectedContact.value = record
  editContactModalVisible.value = true
}

const handleEditContactOk = async () => {
  try {
    await editContactFormRef.value?.validate()
    await customerApi.updateContact(selectedContact.value.id, editContactForm)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('更新', '联系人')
    editContactModalVisible.value = false
    await fetchCustomerDetail()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message) {
      console.error('[CustomerDetail] handleEditContactOk error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '更新联系人')
    }
  }
}

const handleSetPrimary = async (record: { id: number }) => {
  try {
    await customerApi.setPrimaryContact(record.id)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('设置主联系人', '联系人')
    await fetchCustomerDetail()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message) {
      console.error('[CustomerDetail] handleSetPrimary error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '设置主联系人')
    }
  }
}

const handleDeleteContact = async (record: { id: number }) => {
  try {
    await ElMessageBox.confirm(
      `确认要删除联系人 "${record.name}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await customerApi.deleteContact(record.id)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('删除', '联系人')
    await fetchCustomerDetail()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message !== 'cancel') {
      console.error('[CustomerDetail] handleDeleteContact error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '删除联系人')
    }
  }
}

const handleContactAction = (cmd: string, record: { id: number }) => {
  if (cmd === 'setPrimary') {
    handleSetPrimary(record)
  } else if (cmd === 'delete') {
    handleDeleteContact(record)
  }
}

const showAddFollowUpModal = () => {
  Object.assign(followUpForm, {
    method: '电话',
    content: '',
    next_follow_time: '',
    next_action: ''
  })
  addFollowUpModalVisible.value = true
}

const handleAddFollowUpOk = async () => {
  try {
    await followUpFormRef.value?.validate()
    await customerFollowUpApi.createFollowUp(customerId.value, followUpForm)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('添加', '跟进记录')
    addFollowUpModalVisible.value = false
    await fetchFollowUps()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message) {
      console.error('[CustomerDetail] handleAddFollowUpOk error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '添加跟进记录')
    }
  }
}

const handleBack = () => {
  router.back()
}

const handleEditCustomer = () => {
  router.push(`/customers/${customerId.value}/edit`)
}

const fetchOpportunities = async () => {
  try {
    opportunitiesLoading.value = true
    const data = await opportunityApi.getOpportunities({ customer_id: customerId.value })
    opportunities.value = data || []
  } catch (error) {
    console.error('Failed to fetch opportunities:', error)
  } finally {
    opportunitiesLoading.value = false
  }
}

const handleViewOpportunityDetail = (opportunity: Opportunity) => {
  router.push(`/opportunities/${opportunity.id}`)
}

const handleCreateOpportunity = () => {
  router.push(`/customers/${customerId.value}/opportunities/create`)
}

const handleCreateContract = () => {
  router.push({
    path: '/contracts/create',
    query: { customerId: customerId.value }
  })
}

const formatDate = (dateStr: string | undefined) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

const formatAmount = (amount: string | number) => {
  if (!amount) return '¥0'
  const numAmount = typeof amount === 'string' ? parseFloat(amount) : amount
  return `¥${numAmount.toLocaleString()}`
}

// 客户状态样式
const getStatusClass = (status: string) => {
  const statusMap: Record<number, string> = {
    0: 'status-following',
    1: 'status-success',
    2: 'status-lost',
    3: 'status-pool'
  }
  return statusMap[status] || 'status-default'
}

const getStatusText = (status: string) => {
  const statusMap: Record<number, string> = {
    0: '跟进中',
    1: '成交',
    2: '丢失',
    3: '公海'
  }
  return statusMap[status] || '未知'
}

const formatDateTime = (dateStr: string | Date) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

onMounted(async () => {
  await Promise.all([
    fetchCustomerDetail(),
    fetchFollowUps(),
    fetchOpportunities(),
    fetchContracts(),
    fetchPaymentPlans(),
    fetchInvoices(),
    fetchInvoiceTitles()
  ])
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

// ✅ Task 5: 补充过渡动画变量（与 CustomerDetailSidebar.scss 一致）
$wolf-transition-normal: 0.15s ease-out;

// 加载容器 - 为 v-loading 指令提供最小高度
.loading-container {
  min-height: 120px;
  position: relative;
}

.customer-detail-page {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 页面标题区 - sticky 设计（与 LeadDetail.vue 一致）
.page-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: $wolf-bg-card;
  border-bottom: 1px solid $wolf-border-default;
  height: $wolf-header-height;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 $wolf-page-padding;
}

.header-left {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  flex: 1;
  min-width: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  flex-shrink: 0;
}


.back-btn {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: $wolf-radius-md !important;
  background: transparent !important;
  border: none !important;
  color: $wolf-text-tertiary;

  &:hover {
    background: $wolf-bg-hover !important;
    color: $wolf-text-secondary;
  }
}

.page-title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

// 详情内容容器 - 撑满页面宽度
.detail-content {
  padding: $wolf-page-padding;
}

.empty-state {
  padding: $wolf-space-lg;
}

// 信息卡片（撑满页面宽度）
.info-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

// 客户档案卡片
.profile-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: $wolf-space-md;
  padding-bottom: $wolf-space-sm;
  border-bottom: 1px solid $wolf-border-light;
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.profile-status {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
}

.profile-generating {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $wolf-space-md;
  padding: $wolf-space-lg 0;
}

.generating-animation {
  display: flex;
  gap: $wolf-space-sm;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  background: $wolf-primary;
  border-radius: $wolf-radius-full;
  animation: pulse 1.5s ease-in-out infinite;

  &:nth-child(2) {
    animation-delay: 0.3s;
  }

  &:nth-child(3) {
    animation-delay: 0.6s;
  }
}

@keyframes pulse {
  0%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  50% {
    transform: scale(1.2);
    opacity: 1;
  }
}

.generating-text {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.profile-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: $wolf-space-md;
  background: $wolf-danger-bg;
  border-radius: $wolf-radius-md;
}

.error-content {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.error-icon {
  font-size: 20px;
  color: $wolf-danger-text;
}

.error-text {
  font-size: $wolf-font-size-body;
  color: $wolf-danger-text;
}

.profile-content {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

.profile-section {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
}

.section-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.section-content {
  font-size: $wolf-font-size-body;
  color: $wolf-text-secondary;
  line-height: 1.6;

  &.not-filled {
    color: $wolf-text-placeholder;
    font-style: italic;
  }
}

.similar-customers-list {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs;
}

.similar-customer-tag {
  padding: 4px 12px;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-secondary;
}

.link-value {
  color: $wolf-text-link;
  text-decoration: none;

  &:hover {
    color: $wolf-text-link-hover;
    text-decoration: underline;
  }
}

.profile-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: $wolf-space-md;
  border-top: 1px solid $wolf-border-light;
}

.generated-time {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

// 双栏布局
.detail-layout {
  display: flex;
  height: calc(100vh - $wolf-header-height);
  background: $wolf-bg-page;
}

.detail-content {
  flex: 1;
  padding: $wolf-page-padding;
  overflow-y: auto;
  min-width: 0;
}

.customer-detail-page {
  height: 100%;
  background: $wolf-bg-page;
}

// 内容面板容器
.content-panels {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

.content-panel {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

// 移动端：单栏布局
@media (max-width: 768px) {
  .detail-layout {
    flex-direction: column;
  }

  .detail-content {
    padding: $wolf-space-md;
  }

  .content-panels {
    gap: $wolf-space-sm;
  }
}

// 面板头部
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-md;
  font-size: $wolf-font-size-auxiliary;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-secondary;
}

.info-content {
  display: flex;
  flex-direction: column;
}

.info-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: $wolf-space-lg;
}

.info-left {
  flex: 1;
}

.title-section {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.title-avatar {
  width: 48px;
  height: 48px;
  border-radius: $wolf-radius-full;
  background: $wolf-primary;
  color: $wolf-text-inverse;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold;
}

.title-content {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
}

.title-name {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
}

.title-tags {
  display: flex;
  gap: $wolf-space-xs;
  flex-wrap: wrap;
}

.info-right {
  flex-shrink: 0;
}

.stats-section {
  display: flex;
  gap: $wolf-space-lg;
}

.stat-item {
  text-align: right;
}

.stat-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-bottom: $wolf-space-xs;
}

.stat-value {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.info-divider {
  height: 1px;
  background: $wolf-border-light;
  margin: $wolf-space-md 0;
}

.info-bottom {
  padding-top: $wolf-space-sm;
}

// 属性网格
.attributes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: $wolf-space-md;
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
}

.attribute-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.attribute-value {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-secondary;
  font-weight: $wolf-font-weight-medium;

  &.not-filled {
    color: $wolf-text-placeholder;
    font-style: italic;
  }
}

// 状态标签
.status-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  border-radius: $wolf-radius-sm;
}

.status-following {
  background: $wolf-warning-bg;
  color: $wolf-warning-text;
}

.status-converted {
  background: $wolf-success-bg;
  color: $wolf-success-text;
}

.status-invalid {
  background: $wolf-danger-bg;
  color: $wolf-danger-text;
}

.status-success {
  background: $wolf-success-bg;
  color: $wolf-success-text;
}

.status-lost {
  background: $wolf-danger-bg;
  color: $wolf-danger-text;
}

.status-pool {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-info {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-default {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.info-content {
  display: flex;
  flex-direction: column;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-md;
  font-size: $wolf-font-size-auxiliary;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-secondary;
}

// 跟进摘要
.follow-up-summary {
  background: $wolf-bg-page;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  display: flex;
  justify-content: space-around;
  align-items: center;
  margin-bottom: $wolf-space-md;

  .summary-item {
    text-align: center;

    .summary-label {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      margin-bottom: $wolf-space-xs;
    }

    .summary-value {
      font-size: $wolf-font-size-auxiliary;
      font-weight: $wolf-font-weight-medium;
      color: $wolf-text-secondary;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: $wolf-space-xs;

      &.overdue {
        color: $wolf-danger-text;
      }

      &.today {
        color: $wolf-warning-text;
      }

      &.future {
        color: $wolf-success-text;
      }
    }
  }
}

// 表格样式由全局 wolf-design.scss 统一控制

// 表格操作
.wolf-table-actions {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
}

.wolf-btn--text {
  color: $wolf-text-link;
  font-size: $wolf-font-size-caption;
  cursor: pointer;
  padding: 4px 8px;

  &:hover { color: $wolf-text-link-hover; }
}

.wolf-btn--text-danger {
  color: $wolf-danger-text;
  font-size: $wolf-font-size-caption;
  cursor: pointer;
  padding: 4px 8px;

  &:hover { opacity: 0.8; }
}

// 小按钮
.wolf-btn--primary-sm {
  height: $wolf-button-height-sm;
  padding: $wolf-button-padding-sm;
  font-size: $wolf-font-size-caption;
}

// 空状态
.empty-placeholder {
  padding: $wolf-space-lg 0;
}

.empty-opportunities {
  padding: $wolf-space-lg 0;
}

// 商机列表
.opportunities-list {
  .opportunity-item {
    padding: $wolf-space-md;
    background: $wolf-bg-card;
    border: 1px solid $wolf-border-default;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-sm;
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover {
      border-color: $wolf-primary;
      box-shadow: $wolf-shadow-hover;
    }

    .opportunity-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: $wolf-space-xs;

      .opportunity-name {
        font-weight: $wolf-font-weight-medium;
        color: $wolf-text-primary;
      }
    }

    .opportunity-info {
      display: flex;
      flex-wrap: wrap;
      gap: $wolf-space-md;

      .info-item {
        display: flex;
        align-items: center;
        gap: $wolf-space-xs;
        font-size: $wolf-font-size-caption;
        color: $wolf-text-tertiary;

        .info-icon {
          font-size: 14px;
        }
      }
    }
  }
}

// 合同/回款/发票列表
.contract-list,
.payment-list,
.invoice-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm;
}

.contract-item,
.payment-item,
.invoice-item {
  padding: $wolf-space-md;
  background: $wolf-bg-card;
  border: 1px solid $wolf-border-default;
  border-radius: $wolf-radius-md;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    border-color: $wolf-primary;
    box-shadow: $wolf-shadow-hover;
  }
}

.contract-item-header,
.payment-item-header,
.invoice-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-sm;
}

.contract-name,
.stage-name,
.invoice-title {
  font-size: $wolf-font-size-auxiliary;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.contract-item-meta {
  display: flex;
  gap: $wolf-space-md;
  flex-wrap: wrap;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;

  .el-icon {
    font-size: 14px;
  }
}

.contract-item-tags {
  display: flex;
  gap: $wolf-space-xs;
  flex-wrap: wrap;
  margin-top: $wolf-space-sm;
}

.payment-item-info {
  margin-top: $wolf-space-sm;
}

.invoice-item-info {
  margin-top: $wolf-space-sm;
}

// 发票抬头区域
.invoice-titles-section,
.invoice-list-section {
  margin-bottom: $wolf-space-lg;

  &:last-child {
    margin-bottom: 0;
  }
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: $wolf-space-md;
  font-size: $wolf-font-size-auxiliary;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-secondary;
}

.invoice-tiles-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm;
}

.invoice-title-item {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  padding: $wolf-space-md;
  background: $wolf-bg-card;
  border: 1px solid $wolf-border-default;
  border-radius: $wolf-radius-md;
  transition: all 0.2s ease;
  cursor: pointer;

  &:hover {
    border-color: $wolf-primary;
    box-shadow: $wolf-shadow-card;
  }

  &.is-default {
    border-color: $wolf-success-text;
    background: $wolf-success-bg;
  }
}

.title-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm;
}

.title-main {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  flex-wrap: wrap;
}

.title-name {
  font-size: $wolf-font-size-auxiliary;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.title-details {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  font-size: $wolf-font-size-caption;
}

.detail-label {
  color: $wolf-text-tertiary;
  flex-shrink: 0;
  min-width: 80px;
}

.detail-value {
  color: $wolf-text-secondary;
  font-weight: $wolf-font-weight-medium;
}

.title-actions {
  display: flex;
  align-items: center;
  margin-left: $wolf-space-md;
}

// 弹窗样式
.el-dialog {
  :deep(.el-dialog__header) {
    padding: $wolf-space-md;
    border-bottom: 1px solid $wolf-border-light;
    margin: 0;
  }

  :deep(.el-dialog__title) {
    font-size: $wolf-font-size-title;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-primary;
  }

  :deep(.el-dialog__body) {
    padding: $wolf-space-md;
  }

  :deep(.el-dialog__footer) {
    padding: $wolf-space-md;
    border-top: 1px solid $wolf-border-light;
  }
}

.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.dialog-footer-left {
  display: flex;
  gap: $wolf-space-xs;
}

.dialog-footer-right {
  display: flex;
  gap: $wolf-space-xs;
}

.form-item-hint {
  margin-left: $wolf-space-xs;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

// 响应式
@media (max-width: 768px) {
  .customer-detail-page { height: auto; }
  .page-header { padding: $wolf-space-md; }
  .detail-content { padding: $wolf-space-md; }
  .info-card { padding: $wolf-space-md; }
  .score-card { padding: $wolf-space-md; }
  .tabs-card { padding: $wolf-space-md; }
  .info-top { flex-direction: column; gap: $wolf-space-md; }
  .info-right { width: 100%; }
  .stats-section { justify-content: flex-start; }
  .stat-item { text-align: left; }
  .attributes-grid { grid-template-columns: 1fr; }
  .tabs-header { flex-wrap: wrap; gap: $wolf-space-xs; }
  .contract-list, .payment-list, .invoice-list { gap: $wolf-space-xs; }
}

// 热力值卡片样式（紧凑布局）
.score-card-compact {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.score-mini-circle {
  flex-shrink: 0;
}

.score-mini-info {
  flex: 1;
  min-width: 0;
}

.score-mini-header {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  margin-bottom: $wolf-space-xs;
}

.score-mini-icon {
  font-size: 18px;
}

.score-mini-value {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.score-mini-level {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
  background: $wolf-bg-page;
  padding: 2px $wolf-space-xs;
  border-radius: $wolf-radius-sm;
}

.score-mini-details {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
}

.detail-mini-item {
  white-space: nowrap;
}

.pos {
  color: $wolf-success-text;
  font-weight: $wolf-font-weight-medium;
}

.neg {
  color: $wolf-danger-text;
  font-weight: $wolf-font-weight-medium;
}

.score-details-empty {
  padding: $wolf-space-lg;
}

.factor-name {
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-auxiliary;
}

.score-change {
  font-weight: $wolf-font-weight-medium;
  font-size: $wolf-font-size-auxiliary;

  &.positive {
    color: $wolf-success-text;
  }

  &.negative {
    color: $wolf-danger-text;
  }
}

.score-empty {
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-auxiliary;
  text-align: center;
  padding: $wolf-space-md;
}

.score-details-empty {
  padding: $wolf-space-lg;
}

// ✅ Task 5: 简化版客户名称卡片（收起状态）
.customer-name-card-compact {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-sm $wolf-space-md;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-sm;
  border: 1px solid $wolf-border-light;
  margin-bottom: $wolf-space-md;

  .customer-avatar {
    width: 40px;
    height: 40px;
    border-radius: $wolf-radius-full;
    background: $wolf-primary-light;
    color: $wolf-primary;
    font-size: 18px;
    font-weight: $wolf-font-weight-semibold;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .customer-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .customer-name {
    font-size: $wolf-font-size-title;  // 16px
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-primary;
  }

  .customer-status {
    font-size: $wolf-font-size-caption;  // 12px
    color: $wolf-text-tertiary;
  }
}

// ✅ Task 5: 客户档案面板样式
.profile-panel {
  transition: all $wolf-transition-normal;

  &.collapsed {
    // 收起状态：只显示简化版卡片
  }

  &.expanded {
    // 展开状态：显示完整客户档案
  }
}
</style>
