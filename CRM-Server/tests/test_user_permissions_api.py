"""
测试用户合并权限接口的脚本
验证权限合并策略、缓存功能等
"""
import requests
import json
from typing import Dict, List


BASE_URL = "http://localhost:8000"


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)


def print_result(response: requests.Response):
    """打印API响应结果"""
    print(f"\n状态码: {response.status_code}")
    try:
        print(f"响应数据:\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    except:
        print(f"响应内容: {response.text}")


def test_get_user_permissions():
    """测试获取用户合并权限接口"""
    print_section("测试1: 获取当前用户权限（未登录）")
    
    response = requests.get(f"{BASE_URL}/api/v1/auth/me/permissions")
    print_result(response)
    
    if response.status_code == 401:
        print("\n✅ 正确返回401未授权状态")
    else:
        print("\n❌ 应该返回401未授权状态")


def test_login():
    """测试登录并获取token"""
    print_section("测试2: 用户登录")
    
    # 这里需要实际的飞书授权码，实际使用时替换
    # response = requests.post(f"{BASE_URL}/api/v1/auth/login", params={"code": "your_feishu_code"})
    
    # 为了演示，我们假设有一个有效的token
    print("\n⚠️  注意：实际使用需要飞书授权码")
    print("模拟登录成功，获得token: mock_token_123456")
    
    return "mock_token_123456"


def test_get_permissions_with_token(token: str):
    """测试使用token获取权限"""
    print_section("测试3: 使用Token获取用户权限")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        f"{BASE_URL}/api/v1/auth/me/permissions",
        headers=headers
    )
    print_result(response)
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ 成功获取权限列表")
        print(f"权限总数: {data.get('total', 0)}")
        print(f"是否来自缓存: {data.get('cached', False)}")
        
        if data.get('permissions'):
            print("\n前5个权限:")
            for perm in data['permissions'][:5]:
                print(f"  - {perm['code']}: {perm['name']}")


def test_permissions_with_cache_control(token: str):
    """测试缓存控制参数"""
    print_section("测试4: 测试缓存控制")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n第一次请求（使用缓存）:")
    response1 = requests.get(
        f"{BASE_URL}/api/v1/auth/me/permissions",
        headers=headers,
        params={"use_cache": True}
    )
    print(f"状态码: {response1.status_code}")
    if response1.status_code == 200:
        data1 = response1.json()
        print(f"是否来自缓存: {data1.get('cached', False)}")
    
    print("\n第二次请求（使用缓存）:")
    response2 = requests.get(
        f"{BASE_URL}/api/v1/auth/me/permissions",
        headers=headers,
        params={"use_cache": True}
    )
    if response2.status_code == 200:
        data2 = response2.json()
        print(f"是否来自缓存: {data2.get('cached', False)}")
        if data2.get('cached'):
            print("✅ 第二次请求成功使用缓存")
    
    print("\n第三次请求（不使用缓存）:")
    response3 = requests.get(
        f"{BASE_URL}/api/v1/auth/me/permissions",
        headers=headers,
        params={"use_cache": False}
    )
    if response3.status_code == 200:
        data3 = response3.json()
        print(f"是否来自缓存: {data3.get('cached', False)}")
        if not data3.get('cached'):
            print("✅ 请求强制从数据库加载，不使用缓存")


def test_permission_merge_strategy():
    """测试权限合并策略"""
    print_section("测试5: 权限合并策略说明")
    
    print("""
权限合并策略：取并集（Union）
    
示例场景：
- 用户拥有角色: [销售总监, 财务人员]
- 销售总监权限: [contract:view_all, contract:create, ...]
- 财务人员权限: [invoice:approve, payment:confirm, ...]
- 合并后用户权限: [contract:view_all, contract:create, invoice:approve, payment:confirm, ...]

特点：
1. 自动去重：相同权限只保留一份
2. 权限叠加：拥有所有角色的权限集合
3. 无冲突：使用Union策略，不会出现权限冲突
    """)


def test_api_documentation():
    """输出API文档说明"""
    print_section("API接口文档")
    
    print("""
接口：GET /api/v1/auth/me/permissions

功能：获取当前登录用户的所有权限（合并去重）

认证：需要Bearer Token

请求参数：
  - use_cache (boolean, 可选): 是否使用缓存，默认true

响应格式：
{
  "permissions": [
    {
      "id": 1,
      "code": "contract:view_all",
      "name": "查看所有合同",
      "resource": "contract",
      "action": "view",
      "scope": "all",
      "description": "查看系统中所有合同"
    },
    ...
  ],
  "total": 47,
  "cached": true
}

字段说明：
  - permissions: 权限列表
  - total: 权限总数
  - cached: 是否来自Redis缓存

性能优化：
  - 使用Redis缓存，TTL为1小时
  - 首次请求从数据库查询并缓存
  - 后续请求直接返回缓存数据
  - 角色权限变更时自动清除缓存

安全性：
  - 只能获取当前登录用户自身的权限
  - 前端用于UI元素显示/隐藏控制
  - 后端所有业务接口必须再次校验权限
    """)


def test_frontend_usage_example():
    """输出前端使用示例"""
    print_section("前端使用示例")
    
    print("""
1. 获取用户权限：

```javascript
// React示例
const { data } = useAxios('/api/v1/auth/me/permissions');
const permissions = data?.permissions || [];

// Vue示例
const { data } = await axios.get('/api/v1/auth/me/permissions');
const permissions = data.permissions;
```

2. 权限检查函数：

```javascript
function hasPermission(permissionCode) {
  return permissions.some(p => p.code === permissionCode);
}

// 使用示例
if (hasPermission('contract:edit_all')) {
  // 显示编辑所有合同的按钮
}
```

3. 权限控制组件：

```jsx
<PermissionGuard permission="contract:delete">
  <Button onClick={handleDelete}>删除合同</Button>
</PermissionGuard>
```

4. 路由权限控制：

```javascript
{
  path: '/finance/reports',
  component: FinanceReports,
  meta: { 
    permission: 'finance:reports_view' 
  }
}
```

5. 缓存优化建议：

```javascript
// 应用启动时获取权限并缓存
const fetchUserPermissions = async () => {
  const response = await axios.get('/api/v1/auth/me/permissions');
  localStorage.setItem('userPermissions', JSON.stringify(response.data));
  return response.data;
};

// 权限变更时刷新缓存
const refreshPermissions = async () => {
  const response = await axios.get('/api/v1/auth/me/permissions?use_cache=false');
  localStorage.setItem('userPermissions', JSON.stringify(response.data));
};
```
    """)


def main():
    """主测试函数"""
    print("\n" + "="*80)
    print("  飞书轻量化CRM - 用户合并权限接口测试")
    print("="*80)
    
    test_get_user_permissions()
    
    token = test_login()
    
    if token:
        test_get_permissions_with_token(token)
        test_permissions_with_cache_control(token)
    
    test_permission_merge_strategy()
    test_api_documentation()
    test_frontend_usage_example()
    
    print("\n" + "="*80)
    print("  测试完成")
    print("="*80)
    print("""
注意事项：
1. 实际使用时需要有效的飞书授权码进行登录
2. 权限接口返回当前登录用户的所有权限
3. 前端应缓存权限列表，减少API调用
4. 后端所有业务接口仍需进行权限校验
5. 角色权限变更会自动清除缓存
    """)


if __name__ == "__main__":
    main()
