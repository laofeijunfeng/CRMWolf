# 飞书登录集成指南

## 概述

本CRM系统已集成飞书OAuth 2.0登录，用户可以通过飞书账号一键登录系统。

## 前置条件

1. 在飞书开放平台创建自建应用
2. 获取应用的 `App ID` 和 `App Secret`
3. 配置应用的回调地址（Redirect URI）

## 配置步骤

### 1. 飞书开放平台配置

1. 登录 [飞书开放平台](https://open.feishu.cn/)
2. 创建或选择你的应用
3. 在"安全设置"中配置重定向URL：
   - 开发环境：`http://localhost:8000/auth/callback`
   - 生产环境：`https://your-domain.com/auth/callback`
4. 在"权限管理"中申请所需权限：
   - `contact:user.base:readonly` - 获取用户基本信息

### 2. 后端配置

在 `.env` 文件中配置飞书应用信息：

```env
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## 登录流程

### 方式一：使用示例页面

1. 打开 `feishu_login_example.html` 文件
2. 输入飞书应用的 App ID
3. 点击"跳转到飞书授权"按钮
4. 在飞书页面完成授权
5. 自动返回并完成登录

### 方式二：自定义前端实现

#### 步骤1：引导用户到飞书授权页面

```javascript
const APP_ID = 'your_app_id';
const REDIRECT_URI = 'http://localhost:8000/auth/callback';
const SCOPE = 'contact:user.base:readonly';
const STATE = generateRandomString(32);

const authUrl = `https://open.feishu.cn/open-apis/authen/v1/authorize?app_id=${APP_ID}&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&scope=${SCOPE}&state=${STATE}`;

window.location.href = authUrl;
```

#### 步骤2：处理授权回调

用户授权后，飞书会重定向到你的回调地址，URL中包含 `code` 参数：

```
http://localhost:8000/auth/callback?code=xxx&state=xxx
```

#### 步骤3：使用授权码登录

```javascript
const code = new URLSearchParams(window.location.search).get('code');

const response = await fetch('http://localhost:8000/auth/login?code=' + code, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    }
});

const data = await response.json();

// 保存token
localStorage.setItem('access_token', data.access_token);
localStorage.setItem('user_info', JSON.stringify(data.user));
```

#### 步骤4：后续请求携带Token

```javascript
const token = localStorage.getItem('access_token');

const response = await fetch('http://localhost:8000/users', {
    headers: {
        'Authorization': 'Bearer ' + token
    }
});
```

## API接口说明

### 登录接口

**接口地址：** `POST /auth/login`

**请求参数：**
- `code` (query): 飞书授权码

**响应示例：**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "name": "张三",
    "en_name": "zhangsan",
    "email": "zhangsan@example.com",
    "mobile": "+8613800138000",
    "avatar_url": "https://...",
    "region": "北京",
    "status": "active",
    "created_at": "2026-01-26T00:00:00Z",
    "updated_at": "2026-01-26T00:00:00Z"
  }
}
```

### 获取当前用户信息

**接口地址：** `GET /auth/me`

**请求头：**
```
Authorization: Bearer {access_token}
```

**响应示例：**
```json
{
  "id": 1,
  "name": "张三",
  "email": "zhangsan@example.com",
  ...
}
```

### 获取当前用户角色

**接口地址：** `GET /auth/me/roles`

**请求头：**
```
Authorization: Bearer {access_token}
```

**响应示例：**
```json
[
  {
    "id": 1,
    "name": "销售总监",
    "code": "SALES_DIRECTOR",
    "description": "销售总监，可以查看团队所有客户数据和报表"
  }
]
```

## 注意事项

1. **授权码有效期**：飞书授权码有效期为5分钟，只能使用一次
2. **Token有效期**：后端生成的JWT Token默认有效期为30分钟
3. **安全性**：
   - 不要在前端存储敏感信息
   - 使用HTTPS传输
   - 定期刷新Token
4. **错误处理**：
   - 授权码过期：重新引导用户授权
   - Token过期：重新登录或实现Token刷新机制

## 测试

1. 确保后端服务正在运行：`http://localhost:8000`
2. 打开示例页面：`feishu_login_example.html`
3. 输入你的飞书应用App ID
4. 完成授权流程

## 常见问题

**Q: 如何获取飞书应用的App ID？**
A: 登录飞书开放平台，创建应用后在应用详情页面可以看到。

**Q: 授权码在哪里获取？**
A: 用户在飞书授权页面点击"同意"后，飞书会通过重定向URL将授权码传递给你的应用。

**Q: Token过期了怎么办？**
A: 重新调用登录接口获取新的Token，或者实现Token自动刷新机制。

**Q: 如何实现Token自动刷新？**
A: 可以在前端拦截401错误，自动重新登录；或者使用飞书的refresh_token机制。
