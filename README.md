# 投标公司赚钱引擎 - 后端 API

## 项目结构

```
~/.openclaw/workspace-dev-backend/
├── main.py                 # FastAPI 主应用
├── database.db             # SQLite 数据库
├── crawler/
│   ├── gov_crawler.py      # 爬虫主文件
│   ├── scheduler.py        # 定时任务调度器
│   └── requirements.txt    # 爬虫依赖
├── requirements.txt        # 项目依赖
└── README.md               # 本文档
```

## 快速开始

### 1. 安装依赖

```bash
pip3 install -r requirements.txt --break-system-packages
```

### 2. 运行爬虫

```bash
cd ~/.openclaw/workspace-dev-backend
python3 -c "from crawler.gov_crawler import crawl_all; crawl_all()"
```

### 3. 启动 API 服务

```bash
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. 访问 API

- API 首页：http://localhost:8000/
- 项目列表：http://localhost:8000/api/projects
- 统计信息：http://localhost:8000/api/stats
- 手动触发爬虫：POST http://localhost:8000/api/crawl

## API 端点

### GET /
API 首页，显示版本信息和数据库状态

### GET /api/projects
获取招标公告列表

**参数:**
- `category` (可选): 按类别筛选
- `location` (可选): 按地区筛选
- `limit` (可选): 返回数量限制，默认 50

**示例:**
```bash
curl http://localhost:8000/api/projects?location=北京&limit=10
```

### POST /api/predict
预测中标概率

**请求体:**
```json
{
  "project_id": 1,
  "company_name": "某某公司",
  "bid_amount": 1500000
}
```

### POST /api/bid/generate
生成投标文件（Word 格式）

**请求体:**
```json
{
  "project_id": 1,
  "company_name": "某某公司",
  "contact_person": "张三",
  "contact_phone": "13800138000",
  "bid_amount": 1500000
}
```

### GET /api/stats
获取数据库统计信息

### POST /api/crawl
手动触发爬虫任务

## 数据源

### 1. 中国政府采购网
- URL: http://www.ccgp.gov.cn/
- 类型：政府采购招标

### 2. 国家电网电子商务平台
- URL: https://ecp.sgcc.com.cn/
- 类型：电力设备/服务招标

## 定时任务

运行定时任务调度器（每天 06:00 自动执行）：

```bash
python3 crawler/scheduler.py
```

## 数据库结构

```sql
CREATE TABLE bid_notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,          -- 标题
    region TEXT,                   -- 地区
    budget REAL,                   -- 预算（元）
    deadline TEXT,                 -- 截止日期
    description TEXT,              -- 描述
    source_url TEXT UNIQUE,        -- 来源链接
    source_site TEXT,              -- 来源网站
    category TEXT,                 -- 类别
    publish_date TEXT,             -- 发布日期
    crawl_time TEXT,               -- 抓取时间
    content_hash TEXT UNIQUE       -- 内容哈希（去重）
);
```

## 注意事项

1. **遵守 robots.txt** - 爬虫已设置合理延迟
2. **User-Agent** - 使用合法标识
3. **错误处理** - 网络异常自动重试
4. **数据去重** - 使用 content_hash 避免重复

---

**版本:** 1.1.0  
**更新时间:** 2026-04-09
# 触发部署 Sun Apr 19 08:11:35 AM CST 2026
