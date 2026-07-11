<script setup lang="ts">
/**
 * ContactsPanel.vue - 联系人面板组件
 *
 * 用于 CustomerDetailSheet 中的联系人列表展示
 * 支持新建、编辑、删除、设置主要联系人等操作
 *
 * 技术栈：shadcn-vue + variables-v2.scss
 */
import { Plus, Pencil, Trash2, Star } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type { ContactResponse } from '@/api/customer'

// ==================== Props & Emits ====================
interface Props {
  customerId: number
  contacts: ContactResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'add': []
  'edit': [contact: ContactResponse]
  'delete': [contactId: number]
  'set-primary': [contactId: number]
}>()

// ==================== Methods ====================
const handleAdd = (): void => {
  emit('add')
}

const handleEdit = (contact: ContactResponse): void => {
  emit('edit', contact)
}

const handleDelete = (contactId: number): void => {
  emit('delete', contactId)
}

const handleSetPrimary = (contactId: number): void => {
  emit('set-primary', contactId)
}
</script>

<template>
  <div class="contacts-panel">
    <!-- Panel Header -->
    <div class="panel-header">
      <h3 class="panel-title">联系人</h3>
      <Button size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建联系人
      </Button>
    </div>

    <!-- Panel Content -->
    <div class="panel-content">
      <!-- Empty State -->
      <div v-if="contacts.length === 0" class="empty-state">
        暂无联系人
      </div>

      <!-- Contact List -->
      <div v-else class="contact-list">
        <div
          v-for="contact in contacts"
          :key="contact.id"
          class="contact-item"
        >
          <div class="contact-info">
            <div class="contact-header">
              <span class="contact-name">{{ contact.name }}</span>
              <Badge v-if="contact.is_primary" variant="secondary" class="primary-badge">
                <Star class="w-3 h-3 mr-1" />
                主要联系人
              </Badge>
              <Badge v-if="contact.is_decision_maker" variant="secondary" class="decision-maker-badge">
                决策者
              </Badge>
            </div>
            <div class="contact-details">
              {{ contact.position || '-' }} · {{ contact.mobile }}
              <span v-if="contact.email">· {{ contact.email }}</span>
            </div>
          </div>
          <div class="contact-actions">
            <Button variant="ghost" size="sm" @click="handleEdit(contact)">
              <Pencil class="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="sm" @click="handleDelete(contact.id)">
              <Trash2 class="w-4 h-4 text-wolf-danger-text-v2" />
            </Button>
            <Button
              v-if="!contact.is_primary"
              variant="ghost"
              size="sm"
              @click="handleSetPrimary(contact.id)"
            >
              <Star class="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.contacts-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: $wolf-space-md-v2 $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
}

.panel-title {
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
}

.panel-content {
  flex: 1;
  overflow: auto;
}

.empty-state {
  padding: $wolf-space-2xl-v2;
  text-align: center;
  color: $wolf-text-tertiary-v2;
}

.contact-list {
  display: flex;
  flex-direction: column;
}

.contact-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: $wolf-space-md-v2 $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
  transition: $wolf-transition-v2;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: $wolf-bg-hover-v2;
  }
}

.contact-info {
  flex: 1;
  min-width: 0;
}

.contact-header {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  margin-bottom: $wolf-space-xs-v2;
}

.contact-name {
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-primary-v2;
}

.primary-badge {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  padding: 2px 6px;
}

.decision-maker-badge {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  padding: 2px 6px;
}

.contact-details {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

.contact-actions {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  flex-shrink: 0;
  margin-left: $wolf-space-md-v2;
}
</style>