#!/bin/bash
# optimize-customer-detail.sh
# 专门优化 CustomerDetail.vue 的 ElMessage 调用

FILE="CRM-Client/src/views/CustomerDetail.vue"

# ✅ 已完成：import 已添加 showError, showSuccess

# 批量替换 ElMessage.error（通用错误）
sed -i '' "s/ElMessage.error('获取客户详情失败')/showError(error, '获取客户详情')/" "$FILE"
sed -i '' "s/ElMessage.error('获取合同列表失败')/showError(error, '获取合同列表')/" "$FILE"
sed -i '' "s/ElMessage.error('获取回款计划失败')/showError(error, '获取回款计划')/" "$FILE"
sed -i '' "s/ElMessage.error('获取发票列表失败')/showError(error, '获取发票列表')/" "$FILE"
sed -i '' "s/ElMessage.error('获取发票抬头列表失败')/showError(error, '获取发票抬头列表')/" "$FILE"

# 批量替换 ElMessage.success（通用成功）
sed -i '' "s/ElMessage.success('更新成功')/showSuccess('更新', '发票抬头')/" "$FILE"
sed -i '' "s/ElMessage.success('添加成功')/showSuccess('添加', '发票抬头')/" "$FILE"
sed -i '' "s/ElMessage.success('删除成功')/showSuccess('删除', '跟进记录')/" "$FILE"
sed -i '' "s/ElMessage.success('档案正在重新生成')/showSuccess('重新生成', '客户档案')/" "$FILE"

# 批量替换带 error.message 的错误提示
sed -i '' "s/ElMessage.error(error.message || '删除失败')/showError(error, '删除跟进记录')/" "$FILE"
sed -i '' "s/ElMessage.error(error.message || '重新生成失败')/showError(error, '重新生成客户档案')/" "$FILE"

# 批量替换详细的错误提示
sed -i '' "s/ElMessage.error(error.response.data.detail)/showError(error, '保存发票抬头')/" "$FILE"
sed -i '' "s/ElMessage.error(error.message)/showError(error, '保存发票抬头')/" "$FILE"
sed -i '' "s/ElMessage.error('保存失败')/showError(new Error('保存失败'), '发票抬头')/" "$FILE"

echo "✅ CustomerDetail.vue optimization completed!"
echo "请手动检查并调整 context 参数以确保准确性"