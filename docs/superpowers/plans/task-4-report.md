# Task 4 Report: Refactor ContractsPanel to use ListCard

**Date:** 2026-07-15
**Task:** Migrate ContractsPanel.vue to ListCard component with aria-labels

## Status: COMPLETED

## Changes Made

### File Modified
- `CRM-Client/src/components/panels/ContractsPanel.vue`

### Key Changes
1. **Replaced Card structure with ListCard component**
   - Removed: Card, CardHeader, CardContent imports
   - Added: ListCard import

2. **Used ListCard slots**
   - `#headerActions`: Contains "新建合同" button
   - `#itemMain`: Displays contract name, status badge, and details
   - `#itemActions`: ExternalLink button with aria-label

3. **Added aria-label for accessibility**
   - ExternalLink button: `查看合同 ${item.contract_name} 详情`

4. **Maintained existing functionality**
   - Navigation to contract detail page
   - Status badge mapping
   - Currency and date formatting
   - Click handling on row items

## Code Comparison

### Before (Card-based)
```vue
<template>
  <Card class="contracts-panel">
    <CardHeader class="p-4 border-b ...">
      <h3>合同</h3>
      <Button @click="handleAdd">新建合同</Button>
    </CardHeader>
    <CardContent class="p-0">
      <div v-if="contracts.length === 0">暂无合同</div>
      <div v-else class="divide-y ...">
        <div v-for="contract in contracts" @click="handleView(contract.id)">
          <!-- item content -->
          <Button @click.stop="handleView(contract.id)">
            <ExternalLink />
          </Button>
        </div>
      </div>
    </CardContent>
  </Card>
</template>
```

### After (ListCard-based)
```vue
<template>
  <ListCard title="合同" :items="contracts" empty-text="暂无合同">
    <template #headerActions>
      <Button @click="handleAdd">新建合同</Button>
    </template>
    <template #itemMain="{ item }">
      <!-- item content -->
    </template>
    <template #itemActions="{ item }">
      <Button :aria-label="`查看合同 ${item.contract_name} 详情`" @click.stop="handleView(item.id)">
        <ExternalLink />
      </Button>
    </template>
  </ListCard>
</template>
```

## Testing

### Type Check
- Command: `npm run type-check`
- Result: PASSED (no errors for ContractsPanel.vue)
- Note: Existing errors in other files are pre-existing

### Lint
- Command: `npm run lint`
- Result: PASSED (no errors)
- Note: Fixed strict-boolean-expressions warning by explicitly checking `dateStr === null || dateStr === ''` instead of `!dateStr`

## Accessibility Improvements
- Added `aria-label` to ExternalLink button: `查看合同 ${item.contract_name} 详情`
- Provides context for screen readers when navigating contracts

## Commit
```
refactor: migrate ContractsPanel to ListCard with aria-labels
```

## Concerns
None. Implementation follows the plan exactly.