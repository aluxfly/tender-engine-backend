# 🚀 后端部署指南

## 方案一：Railway（推荐）

### 1. 登录 Railway
访问 https://railway.app/ 并登录 GitHub 账号

### 2. 创建新项目
1. 点击 "New Project"
2. 选择 "Deploy from GitHub repo"
3. 授权访问仓库

### 3. 配置环境变量
```
PORT=8000
```

### 4. 自动部署
Railway 会自动检测 Python 项目并部署

---

## 方案二：Render（备选）

### 1. 登录 Render
访问 https://render.com/

### 2. 创建 Web Service
1. 点击 "New +" → "Web Service"
2. 连接 GitHub 仓库
3. 配置：
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT`

### 3. 环境变量
```
PORT=8000
```

---

## 方案三：本地运行 + Ngrok（测试用）

```bash
# 安装依赖
pip install -r requirements.txt

# 启动后端
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000

# 暴露公网（需要 ngrok）
ngrok http 8000
```

---

## 前端 API 配置

部署后端后，修改前端 `projects.html` 中的 API 地址：

```javascript
// 修改前
const API_BASE = 'http://localhost:8000';

// 修改后（Railway 部署后）
const API_BASE = 'https://your-project.railway.app';
```

---

## 当前状态

| 组件 | 状态 | 位置 |
|------|------|------|
| 前端 | ✅ 已部署 | Netlify |
| 后端 | ⏳ 待部署 | Railway/Render |
| 数据库 | ✅ 15 条真实数据 | SQLite |

---

**选择方案后，我可以帮你执行部署！** 🚀
