<template>
  <div class="customer-detail-container">
    <div class="page-header">
      <div class="page-header__left">
        <el-button type="text" class="wolf-btn wolf-btn--back" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1 class="page-header__title">{{ customerDetail?.account_name }}</h1>
      </div>
      <div class="page-header__right">
        <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleEditCustomer">
          编辑
        </el-button>
      </div>
    </div>

    <div v-loading="loading" class="detail-content-container">
      <div v-if="!customerDetail" class="empty-state">
        <el-empty description="客户信息加载失败" />
      </div>

      <div v-else class="detail-content">
        <el-card shadow="never" class="info-card">
          <div class="info-top">
            <div class="info-left">
              <div class="title-section">
                <div class="customer-avatar">{{ customerDetail?.account_name?.charAt(0) || '客' }}</div>
                <div class="title-content">
                  <h2 class="entity-name">{{ customerDetail?.account_name }}</h2>
                  <div class="status-tags">
                    <el-tag v-if="customerDetail?.status === 0" :class="['wolf-tag', 'wolf-tag--info']" size="small">跟进中</el-tag>
                    <el-tag v-else-if="customerDetail?.status === 1" :class="['wolf-tag', 'wolf-tag--success']" size="small">已赢单</el-tag>
                    <el-tag v-else-if="customerDetail?.status === 2" :class="['wolf-tag', 'wolf-tag--danger']" size="small">已输单</el-tag>
                    <el-tag v-else-if="customerDetail?.status === 3" :class="['wolf-tag', 'wolf-tag--gray']" size="small">已失效</el-tag>
                    <el-tag v-if="customerDetail?.industry_info?.name" :class="['wolf-tag', 'wolf-tag--purple']" size="small">{{ customerDetail.industry_info.name }}</el-tag>
                    <el-tag v-if="customerDetail?.company_scale" :class="['wolf-tag', 'wolf-tag--warning']" size="small">{{ customerDetail.company_scale }}</el-tag>
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

          <div class="info-bottom">
            <div class="attributes-grid">
              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><Location /></el-icon>
                  <span class="attribute-label">客户来源</span>
                </div>
                <span class="attribute-value">{{ customerDetail?.source || '-' }}</span>
              </div>

              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><Location /></el-icon>
                  <span class="attribute-label">所在城市</span>
                </div>
                <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.city || customerDetail?.city === '' }">
                  {{ customerDetail?.city && customerDetail?.city !== '' ? customerDetail.city : '未填写' }}
                </span>
              </div>

              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><OfficeBuilding /></el-icon>
                  <span class="attribute-label">公司地址</span>
                </div>
                <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.address || customerDetail?.address === '' }">
                  {{ customerDetail?.address && customerDetail?.address !== '' ? customerDetail.address : '未填写' }}
                </span>
              </div>

              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><UserFilled /></el-icon>
                  <span class="attribute-label">负责销售</span>
                </div>
                <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.owner_info?.name }">
                  {{ customerDetail?.owner_info?.name || '待分配' }}
                </span>
              </div>

              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><ShoppingCart /></el-icon>
                  <span class="attribute-label">采购方式</span>
                </div>
                <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.default_procurement_method_info }">
                  {{ customerDetail?.default_procurement_method_info?.name || '未设置' }}
                </span>
              </div>

              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><Edit /></el-icon>
                  <span class="attribute-label">创建人</span>
                </div>
                <span class="attribute-value" :class="{ 'not-filled': !customerDetail?.creator_info?.name }">
                  {{ customerDetail?.creator_info?.name || '-' }}
                </span>
              </div>

              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><Clock /></el-icon>
                  <span class="attribute-label">创建时间</span>
                </div>
                <span class="attribute-value">{{ formatDate(customerDetail?.created_time) }}</span>
              </div>

              <div class="attribute-item">
                <div class="attribute-header">
                  <el-icon class="attribute-icon"><RefreshRight /></el-icon>
                  <span class="attribute-label">最后修改</span>
                </div>
                <span class="attribute-value">{{ formatDate(customerDetail?.last_modified_time) }}</span>
              </div>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="tabs-card">
          <div class="wolf-tabs">
            <div class="wolf-tabs__header">
              <div
                v-for="tab in tabs"
                :key="tab.key"
                class="wolf-tabs__item"
                :class="{ 'is-active': activeTab === tab.key }"
                @click="activeTab = tab.key"
              >
                {{ tab.label }}
              </div>
            </div>

            <div class="wolf-tabs__content">
              <!-- 客户跟进（操作时间线） -->
              <div v-show="activeTab === 'followup'" class="tab-panel">
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

                <Timeline
                  :logs="timelineLogs"
                  :loading="timelineLoading"
                  :has-more="timelineHasMore"
                  :filters="timelineFilters"
                  @load-more="handleTimelineLoadMore"
                  @filter-change="handleTimelineFilterChange"
                  @reset="handleTimelineReset"
                />
              </div>

              <!-- 联系人 -->
              <div v-show="activeTab === 'contacts'" class="tab-panel">
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
              <div v-show="activeTab === 'opportunities'" class="tab-panel">
                <div class="panel-header">
                  <span>商机列表</span>
                  <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="handleCreateOpportunity">
                    <el-icon><Plus /></el-icon>
                    新建商机
                  </el-button>
                </div>
                <el-spin :loading="opportunitiesLoading" style="width: 100%">
                  <div v-if="opportunities.length === 0" class="empty-opportunities">
                    <el-empty description="暂无商机" />
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
                </el-spin>
              </div>

              <!-- 合同 -->
              <div v-show="activeTab === 'contracts'" class="tab-panel">
                <div class="panel-header">
                  <span>合同列表</span>
                  <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="handleCreateContract">
                    <el-icon><Plus /></el-icon>
                    新建合同
                  </el-button>
                </div>
                <el-spin :loading="contractsLoading" style="width: 100%">
                  <div v-if="contracts.length === 0" class="empty-placeholder">
                    <el-empty description="暂无合同" />
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
                </el-spin>
              </div>

              <!-- 回款 -->
              <div v-show="activeTab === 'payments'" class="tab-panel">
                <div class="panel-header">
                  <span>回款计划</span>
                  <el-button type="primary" class="wolf-btn wolf-btn--primary-sm">
                    <el-icon><Plus /></el-icon>
                    新建回款计划
                  </el-button>
                </div>
                <el-spin :loading="paymentPlansLoading" style="width: 100%">
                  <div v-if="paymentPlans.length === 0" class="empty-placeholder">
                    <el-empty description="暂无回款计划" />
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
                </el-spin>
              </div>

              <!-- 发票 -->
              <div v-show="activeTab === 'invoices'" class="tab-panel">
                <!-- 发票抬头列表 -->
                <div class="invoice-titles-section">
                  <div class="section-title">
                    <span>发票抬头</span>
                    <el-button class="wolf-btn wolf-btn--primary-sm" @click="showInvoiceTitleModal">
                      <el-icon><Plus /></el-icon>
                      添加抬头
                    </el-button>
                  </div>
                  <el-spin :loading="invoiceTitlesLoading" style="width: 100%">
                    <div v-if="invoiceTitles.length === 0" class="empty-placeholder">
                      <el-empty description="暂无发票抬头，点击上方按钮添加" />
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
                  </el-spin>
                </div>

                <!-- 发票列表 -->
                <div class="invoice-list-section">
                  <div class="section-title">
                    <span>发票列表</span>
                  </div>
                  <el-spin :loading="invoicesLoading" style="width: 100%">
                    <div v-if="invoices.length === 0" class="empty-placeholder">
                      <el-empty description="暂无发票" />
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
                  </el-spin>
                </div>
              </div>
            </div>
          </div>
        </el-card>
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
  </template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft,
  Edit,
  Plus,
  CircleCheck,
  CircleClose,
  CircleCheckFilled,
  Clock,
  UserFilled,
  Calendar,
  PriceTag,
  Money,
  Coin,
  Location,
  OfficeBuilding,
  ShoppingCart,
  RefreshRight,
  Document
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Timeline from '@/components/Timeline/index.vue'
import customerApi, { type CustomerDetailResponse, type ContactCreate, type ContactUpdate } from '@/api/customer'
import customerFollowUpApi, { type CustomerFollowUpCreate, type CustomerFollowUpResponse } from '@/api/customerFollowUp'
import { opportunityApi, type Opportunity } from '@/api/opportunity'
import invoiceApi from '@/api/invoice'
import { useTimeline } from '@/composables/useTimeline'

const route = useRoute()
const router = useRouter()

const customerId = ref<number>(parseInt(route.params.id as string))
const customerDetail = ref<CustomerDetailResponse | null>(null)
const loading = ref(false)
const followUps = ref<CustomerFollowUpResponse[]>([])
const selectedContact = ref<any>(null)

const activeTab = ref('followup')
const tabs = [
  { key: 'followup', label: '客户跟进' },
  { key: 'contacts', label: '联系人' },
  { key: 'opportunities', label: '商机' },
  { key: 'contracts', label: '合同' },
  { key: 'payments', label: '回款' },
  { key: 'invoices', label: '发票' }
]

const timeline = useTimeline({
  resourceType: 'CUSTOMER',
  resourceId: customerId.value,
  pageSize: 20
})

const timelineLogs = computed(() => timeline.logs.value)
const timelineLoading = computed(() => timeline.loading.value)
const timelineHasMore = computed(() => timeline.hasMore.value)
const timelineFilters = computed(() => timeline.filters.value)

const handleTimelineLoadMore = () => {
  timeline.loadMore()
}

const handleTimelineFilterChange = () => {
  timeline.refresh()
}

const handleTimelineReset = () => {
  timeline.resetFilters()
}

const lastFollowUp = computed(() => {
  return followUps.value.length > 0 ? followUps.value[0] : null
})

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
}) as any

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
}) as any

const contactFormRules = {
  name: [{ required: true, message: '请输入联系人姓名', trigger: 'blur' }],
  mobile: [{ required: true, message: '请输入手机号', trigger: 'blur' }]
}

const addFollowUpModalVisible = ref(false)
const followUpFormRef = ref()
const followUpForm = reactive<CustomerFollowUpCreate>({
  method: '电话',
  content: '',
  next_follow_time: ''
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
    const data = await customerApi.getCustomerDetail(customerId.value) as any
    customerDetail.value = data
  } catch (error: any) {
    console.error('获取客户详情失败', error)
    ElMessage.error('获取客户详情失败')
  }
}

const fetchFollowUps = async () => {
  try {
    const data = await customerFollowUpApi.getFollowUps(customerId.value) as any
    followUps.value = data.data || []
  } catch (error: any) {
    console.error('获取跟进记录失败', error)
  }
}

const fetchContracts = async () => {
  try {
    contractsLoading.value = true
    const data = await customerApi.getContracts(customerId.value) as any
    contracts.value = data || []
  } catch (error: any) {
    console.error('获取合同列表失败', error)
    ElMessage.error('获取合同列表失败')
  } finally {
    contractsLoading.value = false
  }
}

const fetchPaymentPlans = async () => {
  try {
    paymentPlansLoading.value = true
    const data = await customerApi.getPaymentPlans(customerId.value) as any
    paymentPlans.value = data || []
  } catch (error: any) {
    console.error('获取回款计划失败', error)
    ElMessage.error('获取回款计划失败')
  } finally {
    paymentPlansLoading.value = false
  }
}

const fetchInvoices = async () => {
  try {
    invoicesLoading.value = true
    const data = await customerApi.getInvoices(customerId.value) as any
    invoices.value = data || []
  } catch (error: any) {
    console.error('获取发票列表失败', error)
    ElMessage.error('获取发票列表失败')
  } finally {
    invoicesLoading.value = false
  }
}

const fetchInvoiceTitles = async () => {
  try {
    invoiceTitlesLoading.value = true
    const data = await invoiceApi.getInvoiceTitles(customerId.value) as any
    invoiceTitles.value = data?.invoice_titles || []
  } catch (error: any) {
    console.error('获取发票抬头列表失败', error)
    ElMessage.error('获取发票抬头列表失败')
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

const editInvoiceTitle = (title: any) => {
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
      ElMessage.success('更新成功')
    } else {
      const { is_default, ...createData } = invoiceTitleForm
      const result = await invoiceApi.createInvoiceTitle(customerId.value, createData) as any
      
      if (is_default && result?.id) {
        await invoiceApi.setDefaultInvoiceTitle(result.id)
      }
      
      ElMessage.success('添加成功')
    }
    
    invoiceTitleFormVisible.value = false
    await fetchInvoiceTitles()
  } catch (error: any) {
    if (error?.response?.data?.detail) {
      ElMessage.error(error.response.data.detail)
    } else if (error?.message) {
      ElMessage.error(error.message)
    } else {
      console.error('保存失败', error)
      ElMessage.error('保存失败')
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
    ElMessage.success('删除成功')
    invoiceTitleFormVisible.value = false
    await fetchInvoiceTitles()
  } catch (error: any) {
    if (error === 'cancel') return
    console.error('删除失败', error)
    ElMessage.error('删除失败')
  }
}

const handleInvoiceTitleUpdated = () => {
  fetchInvoiceTitles()
}

const showInvoiceApplicationModal = () => {
  ElMessage.info('发票申请功能开发中...')
}

const createInvoice = (title: any) => {
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
    ElMessage.success('添加联系人成功')
    addContactModalVisible.value = false
    await fetchCustomerDetail()
  } catch (error: any) {
    if (error?.message) {
      ElMessage.error(error.message)
    }
  }
}

const handleEditContact = (record: any) => {
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
    ElMessage.success('更新联系人成功')
    editContactModalVisible.value = false
    await fetchCustomerDetail()
  } catch (error: any) {
    if (error?.message) {
      ElMessage.error(error.message)
    }
  }
}

const handleSetPrimary = async (record: any) => {
  try {
    await customerApi.setPrimaryContact(record.id)
    ElMessage.success('设置主联系人成功')
    await fetchCustomerDetail()
  } catch (error: any) {
    if (error?.message) {
      ElMessage.error(error.message)
    }
  }
}

const handleDeleteContact = async (record: any) => {
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
    ElMessage.success('删除联系人成功')
    await fetchCustomerDetail()
  } catch (error: any) {
    if (error !== 'cancel' && error?.message) {
      ElMessage.error(error.message)
    }
  }
}

const handleContactAction = (cmd: string, record: any) => {
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
    next_follow_time: ''
  })
  addFollowUpModalVisible.value = true
}

const handleAddFollowUpOk = async () => {
  try {
    await followUpFormRef.value?.validate()
    await customerFollowUpApi.createFollowUp(customerId.value, followUpForm)
    ElMessage.success('添加跟进记录成功')
    addFollowUpModalVisible.value = false
    await fetchFollowUps()
    timeline.refresh()
  } catch (error: any) {
    if (error?.message) {
      ElMessage.error(error.message)
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
    const data = await opportunityApi.getOpportunities({ customer_id: customerId.value }) as any
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
  timeline.fetchLogs(1, false)  // 首次加载第 1 页，不追加
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.customer-detail-container {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 页面标题区
.page-header {
  margin-bottom: $wolf-space-lg;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-header__left {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.page-header__title {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
}

.page-header__right {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
}

// 返回按钮
.wolf-btn--back {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: $wolf-radius-sm !important;
  color: $wolf-text-tertiary;
  background: transparent;

  &:hover {
    background: $wolf-bg-hover !important;
    color: $wolf-text-secondary;
  }
}

// 详情内容容器
.detail-content-container {
  max-width: 1000px;
}

// 信息卡片
.info-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
  margin-bottom: $wolf-space-md;
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

.customer-avatar {
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

.entity-name {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0;
}

.status-tags {
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
  padding-top: $wolf-space-md;
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

.attribute-header {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
}

.attribute-icon {
  font-size: 14px;
  color: $wolf-text-tertiary;
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

// 标签页卡片
.tabs-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

// 标签页样式
.wolf-tabs__header {
  display: flex;
  gap: $wolf-space-md;
  border-bottom: 1px solid $wolf-border-default;
  margin-bottom: $wolf-space-md;
}

.wolf-tabs__item {
  padding: $wolf-space-sm 0;
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
  cursor: pointer;
  position: relative;
  transition: color 0.2s ease;

  &:hover {
    color: $wolf-text-secondary;
  }

  &.is-active {
    color: $wolf-text-secondary;
    font-weight: $wolf-font-weight-medium;

    &::after {
      content: '';
      position: absolute;
      bottom: -1px;
      left: 0;
      right: 0;
      height: 2px;
      background: $wolf-primary;
    }
  }
}

.wolf-tabs__content {
  min-height: 200px;
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

.status-default {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
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
  .customer-detail-container { padding: $wolf-space-md; }
  .info-card { padding: $wolf-space-md; }
  .tabs-card { padding: $wolf-space-md; }
  .info-top { flex-direction: column; gap: $wolf-space-md; }
  .info-right { width: 100%; }
  .stats-section { justify-content: flex-start; }
  .stat-item { text-align: left; }
  .attributes-grid { grid-template-columns: 1fr; }
  .wolf-tabs__header { flex-wrap: wrap; gap: $wolf-space-xs; }
  .contract-list, .payment-list, .invoice-list { gap: $wolf-space-xs; }
}
</style>
