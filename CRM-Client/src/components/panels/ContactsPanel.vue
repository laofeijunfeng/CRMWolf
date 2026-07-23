<script setup lang="ts">
/**
 * ContactsPanel.vue - 联系人面板组件
 *
 * 使用 ListCard 组件确保风格统一
 * 技术栈：shadcn-vue + variables-v2.scss
 * 无障碍：所有图标按钮均有 aria-label
 */
import { Plus, Pencil, Trash2, Star } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import ListCard from '@/components/crmwolf/ListCard.vue'
import type { ContactResponse } from '@/api/customer'

interface Props {
  customerId: number
  contacts: ContactResponse[]
  showAdd?: boolean
  canEdit?: boolean
  canDelete?: boolean
  canSetPrimary?: boolean
}

withDefaults(defineProps<Props>(), {
  showAdd: true,
  canEdit: true,
  canDelete: true,
  canSetPrimary: true
})

const emit = defineEmits<{
  'add': []
  'edit': [contact: ContactResponse]
  'delete': [contactId: number]
  'set-primary': [contactId: number]
}>()

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
  <ListCard
    title="联系人"
    :items="contacts"
    empty-text="暂无联系人"
  >
    <template #headerActions>
      <Button v-if="showAdd" size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建联系人
      </Button>
    </template>

    <template #itemMain="{ item }">
      <span class="font-medium text-wolf-text-primary-v2 truncate">{{ item.name }}</span>
    </template>

    <template #itemMeta="{ item }">
      <span>{{ item.position || '-' }}</span>
      <span> · {{ item.mobile || '-' }}</span>
      <span v-if="item.email"> · {{ item.email }}</span>
    </template>

    <template #itemBadges="{ item }">
      <Badge v-if="item.is_primary" variant="secondary" class="text-xs px-2 py-0.5">
        <Star class="w-3 h-3 mr-1" />
        主要联系人
      </Badge>
      <Badge v-if="item.is_decision_maker" variant="secondary" class="text-xs px-2 py-0.5">
        决策者
      </Badge>
    </template>

    <template #itemActions="{ item }">
      <Button
        v-if="canEdit"
        variant="ghost"
        size="sm"
        :aria-label="`编辑联系人 ${item.name}`"
        @click.stop="handleEdit(item)"
      >
        <Pencil class="w-4 h-4" />
      </Button>
      <Button
        v-if="canDelete"
        variant="ghost"
        size="sm"
        :aria-label="`删除联系人 ${item.name}`"
        @click.stop="handleDelete(item.id)"
      >
        <Trash2 class="w-4 h-4 text-wolf-danger-text-v2" />
      </Button>
      <Button
        v-if="canSetPrimary && !item.is_primary"
        variant="ghost"
        size="sm"
        :aria-label="`将 ${item.name} 设为主要联系人`"
        @click.stop="handleSetPrimary(item.id)"
      >
        <Star class="w-4 h-4" />
      </Button>
    </template>
  </ListCard>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>
