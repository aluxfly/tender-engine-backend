# ⚙️ 后端开发任务

**优先级：P0**
**截止时间：今天 18:00（6 小时内）**

## 项目：投标公司赚钱引擎 MVP

### 极简后端（单文件 API）

**技术栈：** Python + FastAPI（单文件 `main.py`）

### 核心功能
1. **项目 API** - `GET /api/projects`（返回静态数据）
2. **预测 API** - `POST /api/predict`（返回随机高/中/低）
3. **标书 API** - `POST /api/bid/generate`（生成简单 Word）

### 数据模型

```sql
-- 项目表
CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  title TEXT,
  region TEXT,
  budget REAL,
  deadline DATE,
  description TEXT,
  source_url TEXT,
  created_at DATETIME
);

-- 用户表
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email TEXT,
  wechat TEXT,
  created_at DATETIME
);

-- 标书模板表
CREATE TABLE templates (
  id INTEGER PRIMARY KEY,
  name TEXT,
  category TEXT,
  content TEXT,
  created_at DATETIME
);
```

### 输出位置
代码保存到 `~/.openclaw/workspace-dev-backend/`

---

**开始工作！** 🚀
