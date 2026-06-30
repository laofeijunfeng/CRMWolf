#!/bin/bash
# 权限修复验证测试脚本
# 用法: ./test_permissions.sh

BASE_URL="http://localhost:8000"
TOKEN_ADMIN=""      # TEAM_ADMIN token
TOKEN_MEMBER=""      # SALES_MEMBER token
TOKEN_FINANCE=""     # FINANCE token

echo "============================================================"
echo "CRM权限修复验证测试"
echo "============================================================"

# 测试1: 销售成员列表权限（应该只看自己的数据）
test_member_list() {
    echo ""
    echo "[测试1] 销售成员查看客户列表（应该只看自己的）"
    echo "GET $BASE_URL/v1/customers"

    if [ -n "$TOKEN_MEMBER" ]; then
        response=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN_MEMBER" "$BASE_URL/v1/customers")
        code=$(echo "$response" | tail -1)
        body=$(echo "$response" | head -n -1)

        if [ "$code" = "200" ]; then
            count=$(echo "$body" | grep -c "\"id\"" || echo "0")
            echo "✅ HTTP $code - 返回 $count 个客户"
            echo "检查: 应该只返回 owner_id=当前用户ID 的客户"
        else
            echo "❌ HTTP $code - 请求失败"
        fi
    else
        echo "⚠️  未配置 TOKEN_MEMBER，跳过测试"
    fi
}

# 测试2: 销售成员编辑他人客户（应该返回403）
test_member_edit_other() {
    echo ""
    echo "[测试2] 销售成员编辑他人的客户（应该返回403）"
    echo "PUT $BASE_URL/v1/customers/{OTHER_CUSTOMER_ID}"

    if [ -n "$TOKEN_MEMBER" ]; then
        # 需要一个其他用户的客户ID
        OTHER_CUSTOMER_ID="1"  # 替换为实际ID

        response=$(curl -s -w "\n%{http_code}" -X PUT \
            -H "Authorization: Bearer $TOKEN_MEMBER" \
            -H "Content-Type: application/json" \
            -d '{"account_name":"测试修改"}' \
            "$BASE_URL/v1/customers/$OTHER_CUSTOMER_ID")

        code=$(echo "$response" | tail -1)

        if [ "$code" = "403" ]; then
            echo "✅ HTTP 403 - 正确拒绝（权限修复生效）"
        elif [ "$code" = "200" ]; then
            echo "❌ HTTP 200 - 错误！销售成员不应能编辑他人客户"
        else
            echo "⚠️  HTTP $code - 其他响应"
        fi
    else
        echo "⚠️  未配置 TOKEN_MEMBER，跳过测试"
    fi
}

# 测试3: 管理员删除他人数据（应该成功）
test_admin_delete_other() {
    echo ""
    echo "[测试3] 管理员删除他人的客户（应该成功）"
    echo "DELETE $BASE_URL/v1/customers/{OTHER_CUSTOMER_ID}"

    if [ -n "$TOKEN_ADMIN" ]; then
        OTHER_CUSTOMER_ID="2"  # 替换为实际ID

        response=$(curl -s -w "\n%{http_code}" -X DELETE \
            -H "Authorization: Bearer $TOKEN_ADMIN" \
            "$BASE_URL/v1/customers/$OTHER_CUSTOMER_ID")

        code=$(echo "$response" | tail -1)

        if [ "$code" = "200" ] || [ "$code" = "204" ]; then
            echo "✅ HTTP $code - 成功删除（delete:all权限生效）"
        elif [ "$code" = "403" ]; then
            echo "❌ HTTP 403 - 权限不足（delete:all未生效）"
        else
            echo "⚠️  HTTP $code - 其他响应（可能是404）"
        fi
    else
        echo "⚠️  未配置 TOKEN_ADMIN，跳过测试"
    fi
}

# 测试4: 财务审批发票（应该成功）
test_finance_approve() {
    echo ""
    echo "[测试4] 财务审批发票申请（应该成功）"
    echo "POST $BASE_URL/v1/invoice-applications/{id}/review"

    if [ -n "$TOKEN_FINANCE" ]; then
        APPLICATION_ID="1"  # 替换为实际ID

        response=$(curl -s -w "\n%{http_code}" -X POST \
            -H "Authorization: Bearer $TOKEN_FINANCE" \
            -H "Content-Type: application/json" \
            -d '{"action":"approve","comment":"测试审批"}' \
            "$BASE_URL/v1/invoice-applications/$APPLICATION_ID/review")

        code=$(echo "$response" | tail -1)

        if [ "$code" = "200" ]; then
            echo "✅ HTTP 200 - 审批成功（invoice:approve权限生效）"
        elif [ "$code" = "403" ]; then
            echo "❌ HTTP 403 - 权限不足"
        else
            echo "⚠️  HTTP $code - 其他响应"
        fi
    else
        echo "⚠️  未配置 TOKEN_FINANCE，跳过测试"
    fi
}

# 测试5: 销售成员删除自己的客户（应该成功）
test_member_delete_own() {
    echo ""
    echo "[测试5] 销售成员删除自己的客户（应该成功）"
    echo "DELETE $BASE_URL/v1/customers/{OWN_CUSTOMER_ID}"

    if [ -n "$TOKEN_MEMBER" ]; then
        OWN_CUSTOMER_ID="3"  # 替换为销售成员自己的客户ID

        response=$(curl -s -w "\n%{http_code}" -X DELETE \
            -H "Authorization: Bearer $TOKEN_MEMBER" \
            "$BASE_URL/v1/customers/$OWN_CUSTOMER_ID")

        code=$(echo "$response" | tail -1)

        if [ "$code" = "200" ] || [ "$code" = "204" ]; then
            echo "✅ HTTP $code - 成功删除（delete:own权限生效）"
        elif [ "$code" = "403" ]; then
            echo "❌ HTTP 403 - 权限不足（delete:own未配置）"
        else
            echo "⚠️  HTTP $code - 其他响应"
        fi
    else
        echo "⚠️  未配置 TOKEN_MEMBER，跳过测试"
    fi
}

# 执行所有测试
echo ""
echo "开始执行测试..."
echo ""

test_member_list
test_member_edit_other
test_admin_delete_other
test_finance_approve
test_member_delete_own

echo ""
echo "============================================================"
echo "测试完成"
echo "============================================================"
echo ""
echo "注意: 需要配置 TOKEN_ADMIN/TOKEN_MEMBER/TOKEN_FINANCE 环境变量"
echo "获取Token方式: POST /auth/login 或 /auth/login-password"