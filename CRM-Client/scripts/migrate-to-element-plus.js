/**
 * Arco Design Vue → Element Plus 迁移脚本
 * 批量替换组件和API调用
 */

const fs = require('fs');
const path = require('path');

// 组件映射表
const componentMappings = [
  // 基础组件
  { from: '<a-button', to: '<el-button' },
  { from: '</a-button>', to: '</el-button>' },
  { from: '<a-input', to: '<el-input' },
  { from: '</a-input>', to: '</el-input>' },
  { from: '<a-textarea', to: '<el-input type="textarea"' },
  { from: '</a-textarea>', to: '</el-input>' },
  { from: '<a-select', to: '<el-select' },
  { from: '</a-select>', to: '</el-select>' },
  { from: '<a-option', to: '<el-option' },
  { from: '</a-option>', to: '</el-option>' },
  { from: '<a-form', to: '<el-form' },
  { from: '</a-form>', to: '</el-form>' },
  { from: '<a-form-item', to: '<el-form-item' },
  { from: '</a-form-item>', to: '</el-form-item>' },
  { from: '<a-card', to: '<el-card' },
  { from: '</a-card>', to: '</el-card>' },
  { from: '<a-table', to: '<el-table' },
  { from: '</a-table>', to: '</el-table>' },
  { from: '<a-modal', to: '<el-dialog' },
  { from: '</a-modal>', to: '</el-dialog>' },
  { from: '<a-tabs', to: '<el-tabs' },
  { from: '</a-tabs>', to: '</el-tabs>' },
  { from: '<a-tab-pane', to: '<el-tab-pane' },
  { from: '</a-tab-pane>', to: '</el-tab-pane>' },
  { from: '<a-tag', to: '<el-tag' },
  { from: '</a-tag>', to: '</el-tag>' },
  { from: '<a-dropdown', to: '<el-dropdown' },
  { from: '</a-dropdown>', to: '</el-dropdown>' },
  { from: '<a-doption', to: '<el-dropdown-item' },
  { from: '</a-doption>', to: '</el-dropdown-item>' },
  { from: '<a-breadcrumb', to: '<el-breadcrumb' },
  { from: '</a-breadcrumb>', to: '</el-breadcrumb>' },
  { from: '<a-breadcrumb-item', to: '<el-breadcrumb-item' },
  { from: '</a-breadcrumb-item>', to: '</el-breadcrumb-item>' },
  { from: '<a-descriptions', to: '<el-descriptions' },
  { from: '</a-descriptions>', to: '</el-descriptions>' },
  { from: '<a-descriptions-item', to: '<el-descriptions-item' },
  { from: '</a-descriptions-item>', to: '</el-descriptions-item>' },
  { from: '<a-empty', to: '<el-empty' },
  { from: '</a-empty>', to: '</el-empty>' },
  { from: '<a-spin', to: '<el-skeleton' },
  { from: '</a-spin>', to: '</el-skeleton>' },
  { from: '<a-pagination', to: '<el-pagination' },
  { from: '</a-pagination>', to: '</el-pagination>' },
  { from: '<a-avatar', to: '<el-avatar' },
  { from: '</a-avatar>', to: '</el-avatar>' },
  { from: '<a-checkbox', to: '<el-checkbox' },
  { from: '</a-checkbox>', to: '</el-checkbox>' },
  { from: '<a-checkbox-group', to: '<el-checkbox-group' },
  { from: '</a-checkbox-group>', to: '</el-checkbox-group>' },
  { from: '<a-radio', to: '<el-radio' },
  { from: '</a-radio>', to: '</el-radio>' },
  { from: '<a-radio-group', to: '<el-radio-group' },
  { from: '</a-radio-group>', to: '</el-radio-group>' },
  { from: '<a-switch', to: '<el-switch' },
  { from: '</a-switch>', to: '</el-switch>' },
  { from: '<a-date-picker', to: '<el-date-picker' },
  { from: '</a-date-picker>', to: '</el-date-picker>' },
  { from: '<a-range-picker', to: '<el-date-picker type="daterange"' },
  { from: '</a-range-picker>', to: '</el-date-picker>' },
  { from: '<a-input-number', to: '<el-input-number' },
  { from: '</a-input-number>', to: '</el-input-number>' },
  { from: '<a-rate', to: '<el-rate' },
  { from: '</a-rate>', to: '</el-rate>' },
  { from: '<a-slider', to: '<el-slider' },
  { from: '</a-slider>', to: '</el-slider>' },
  { from: '<a-timeline', to: '<el-timeline' },
  { from: '</a-timeline>', to: '</el-timeline>' },
  { from: '<a-timeline-item', to: '<el-timeline-item' },
  { from: '</a-timeline-item>', to: '</el-timeline-item>' },
  { from: '<a-space', to: '<div class="space"', },
  { from: '</a-space>', to: '</div>' },

  // 属性映射
  { from: 'v-model:active-key', to: 'v-model' },
  { from: 'v-model:visible', to: 'v-model' },
  { from: ':active-key', to: 'v-model' },
  { from: 'title=', to: 'label=' },
  { from: 'field=', to: 'prop=' },
  { from: 'layout="vertical"', to: 'label-position="top"' },
  { from: ':columns=', to: '(需要手动转换)' },
  { from: '@ok', to: '@confirm' },
  { from: '@cancel', to: '@close' },

  // API映射
  { from: "Message.success(", to: "ElMessage.success(" },
  { from: "Message.error(", to: "ElMessage.error(" },
  { from: "Message.warning(", to: "ElMessage.warning(" },
  { from: "Message.info(", to: "ElMessage.info(" },
  { from: 'Modal.confirm({', to: 'ElMessageBox.confirm(' },
  { from: 'Modal.confirm\\({', to: 'ElMessageBox.confirm(' },

  // 导入映射
  { from: "from '@arco-design/web-vue'", to: "from 'element-plus'" },
  { from: "import { Message }", to: "import { ElMessage }" },
  { from: "import { Modal }", to: "import { ElMessageBox }" },
];

// 图标映射
const iconMappings = [
  { from: '<icon-edit />', to: '<el-icon><Edit /></el-icon>' },
  { from: '<icon-plus />', to: '<el-icon><Plus /></el-icon>' },
  { from: '<icon-delete />', to: '<el-icon><Delete /></el-icon>' },
  { from: '<icon-search />', to: '<el-icon><Search /></el-icon>' },
  { from: '<icon-refresh />', to: '<el-icon><Refresh /></el-icon>' },
  { from: '<icon-check-circle />', to: '<el-icon><CircleCheck /></el-icon>' },
  { from: '<icon-close-circle />', to: '<el-icon><CircleClose /></el-icon>' },
  { from: '<icon-user />', to: '<el-icon><User /></el-icon>' },
  { from: '<icon-user-add />', to: '<el-icon><UserFilled /></el-icon>' },
  { from: '<icon-sync />', to: '<el-icon><RefreshRight /></el-icon>' },
  { from: '<icon-more />', to: '<el-icon><More /></el-icon>' },
  { from: 'IconEdit', to: 'Edit' },
  { from: 'IconPlus', to: 'Plus' },
  { from: 'IconDelete', to: 'Delete' },
  { from: 'IconSearch', to: 'Search' },
  { from: 'IconRefresh', to: 'Refresh' },
  { from: 'IconCheckCircle', to: 'CircleCheck' },
  { from: 'IconCloseCircle', to: 'CircleClose' },
  { from: 'IconUser', to: 'User' },
  { from: 'IconUserAdd', to: 'UserFilled' },
  { from: 'IconSync', to: 'RefreshRight' },
  { from: 'IconMore', to: 'More' },
  { from: "from '@arco-design/web-vue/es/icon'", to: "from '@element-plus/icons-vue'" },
];

/**
 * 迁移单个文件
 */
function migrateFile(filePath) {
  console.log(`Processing: ${filePath}`);

  let content = fs.readFileSync(filePath, 'utf8');
  let modified = false;

  // 应用组件映射
  componentMappings.forEach(mapping => {
    const regex = new RegExp(mapping.from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
    if (regex.test(content)) {
      content = content.replace(regex, mapping.to);
      modified = true;
    }
  });

  // 应用图标映射
  iconMappings.forEach(mapping => {
    const regex = new RegExp(mapping.from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
    if (regex.test(content)) {
      content = content.replace(regex, mapping.to);
      modified = true;
    }
  });

  if (modified) {
    fs.writeFileSync(filePath, content, 'utf8');
    console.log(`✓ Migrated: ${filePath}`);
    return true;
  }

  return false;
}

/**
 * 递归处理目录
 */
function migrateDirectory(dir) {
  const files = fs.readdirSync(dir);

  files.forEach(file => {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);

    if (stat.isDirectory()) {
      // 跳过node_modules和.git
      if (file !== 'node_modules' && file !== '.git' && file !== 'dist') {
        migrateDirectory(filePath);
      }
    } else if (file.endsWith('.vue') || file.endsWith('.ts') || file.endsWith('.js')) {
      migrateFile(filePath);
    }
  });
}

// 执行迁移
const viewsDir = path.join(__dirname, '../src/views');
migrateDirectory(viewsDir);

console.log('\n✨ Migration completed!');
console.log('⚠️  Please review the changes and manually adjust:');
console.log('   - Table column definitions (use <el-table-column> instead of :columns)');
console.log('   - Modal API (ElMessageBox.confirm has different signature)');
console.log('   - Icon imports (need to import from @element-plus/icons-vue)');
console.log('   - Form validation rules (add trigger: "blur" or "change")');
