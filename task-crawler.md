# 🕷️ 爬虫开发任务

**优先级：P0**
**截止时间：今天 18:00**

## 项目：投标公司赚钱引擎 - 真实数据接入

## 数据源

### 1. 中国政府采购网
- **URL:** http://www.ccgp.gov.cn/
- **类型:** 政府采购招标
- **更新频率:** 每日更新

### 2. 国家电网电子商务平台
- **URL:** https://ecp.sgcc.com.cn/
- **类型:** 电力设备/服务招标
- **更新频率:** 每日更新

## 任务详情

### 1. 爬虫开发

**文件:** `crawler/gov_crawler.py`

**功能:**
- 抓取两个网站的招标公告
- 解析字段：标题、地区、预算、截止时间、描述、链接
- 存储到 SQLite 数据库
- 支持增量更新（避免重复）

### 2. API 更新

**文件:** `backend/main.py`

**更新:**
- `GET /api/projects` - 从数据库读取真实数据
- 保留筛选功能（category/location）

### 3. 定时任务

**文件:** `crawler/scheduler.py`

**功能:**
- 每天自动抓取一次
- 错误处理和日志记录

## 技术栈

- Python + Playwright（动态页面）
- BeautifulSoup4（静态解析）
- SQLite（数据存储）
- APScheduler（定时任务）

## 输出位置

```
~/.openclaw/workspace-dev-backend/
├── crawler/
│   ├── gov_crawler.py    # 爬虫主文件
│   ├── scheduler.py      # 定时任务
│   └── requirements.txt  # 爬虫依赖
├── main.py               # 更新 API
└── database.db           # SQLite 数据库
```

## 注意事项

1. **遵守 robots.txt** - 控制抓取频率
2. **User-Agent** - 使用合法标识
3. **错误处理** - 网络异常重试机制
4. **数据清洗** - 统一字段格式

---

**立即开始！时间紧急！** 🚀
