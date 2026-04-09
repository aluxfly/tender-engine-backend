"""
投标公司赚钱引擎 MVP 后端 API
FastAPI 单文件实现
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import random
from datetime import datetime
from docx import Document
from io import BytesIO
from fastapi.responses import StreamingResponse
import sqlite3
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="投标公司赚钱引擎 API",
    description="MVP 版本 - 项目查询、中标预测、标书生成",
    version="1.0.0"
)

# 启用 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据库路径
DB_PATH = Path(__file__).parent / 'database.db'

# 静态文件目录
STATIC_DIR = Path(__file__).parent / 'static'


# ==================== 前端页面路由 ====================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """提供首页"""
    index_path = STATIC_DIR / 'index.html'
    if index_path.exists():
        with open(index_path, 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    raise HTTPException(status_code=404, detail="Page not found")


@app.get("/projects", response_class=HTMLResponse)
async def serve_projects():
    """提供项目列表页"""
    page_path = STATIC_DIR / 'projects.html'
    if page_path.exists():
        with open(page_path, 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    raise HTTPException(status_code=404, detail="Page not found")


@app.get("/project-detail", response_class=HTMLResponse)
async def serve_project_detail():
    """提供项目详情页"""
    page_path = STATIC_DIR / 'project-detail.html'
    if page_path.exists():
        with open(page_path, 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    raise HTTPException(status_code=404, detail="Page not found")


@app.get("/bid", response_class=HTMLResponse)
async def serve_bid():
    """提供标书生成页"""
    page_path = STATIC_DIR / 'bid.html'
    if page_path.exists():
        with open(page_path, 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    raise HTTPException(status_code=404, detail="Page not found")


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ==================== 模拟数据 (备用) ====================

PROJECTS = [
    {
        "id": 1,
        "name": "智慧城市交通管理系统",
        "budget": 2800000,
        "deadline": "2026-05-15",
        "category": "软件开发",
        "location": "北京",
        "description": "建设城市级智能交通管理平台"
    },
    {
        "id": 2,
        "name": "企业 ERP 系统升级",
        "budget": 1500000,
        "deadline": "2026-04-30",
        "category": "软件开发",
        "location": "上海",
        "description": "现有 ERP 系统功能扩展与性能优化"
    },
    {
        "id": 3,
        "name": "数据中心网络改造",
        "budget": 3200000,
        "deadline": "2026-06-01",
        "category": "基础设施",
        "location": "深圳",
        "description": "数据中心网络架构升级与设备更新"
    },
    {
        "id": 4,
        "name": "移动办公平台建设",
        "budget": 980000,
        "deadline": "2026-05-20",
        "category": "软件开发",
        "location": "杭州",
        "description": "企业移动办公 APP 及后台管理系统"
    },
    {
        "id": 5,
        "name": "AI 客服系统开发",
        "budget": 1200000,
        "deadline": "2026-04-25",
        "category": "人工智能",
        "location": "广州",
        "description": "基于大模型的智能客服系统"
    },
    {
        "id": 6,
        "name": "云存储平台建设",
        "budget": 2100000,
        "deadline": "2026-05-10",
        "category": "云计算",
        "location": "成都",
        "description": "企业级云存储与文件管理系统"
    },
    {
        "id": 7,
        "name": "物联网监控平台",
        "budget": 1800000,
        "deadline": "2026-06-15",
        "category": "物联网",
        "location": "武汉",
        "description": "工业设备物联网监控与预警系统"
    },
    {
        "id": 8,
        "name": "大数据分析平台",
        "budget": 2500000,
        "deadline": "2026-05-05",
        "category": "大数据",
        "location": "南京",
        "description": "企业数据仓库与 BI 分析平台"
    },
    {
        "id": 9,
        "name": "网络安全加固项目",
        "budget": 1600000,
        "deadline": "2026-04-28",
        "category": "网络安全",
        "location": "西安",
        "description": "企业网络安全体系加固与渗透测试"
    },
    {
        "id": 10,
        "name": "区块链供应链系统",
        "budget": 3500000,
        "deadline": "2026-06-20",
        "category": "区块链",
        "location": "天津",
        "description": "基于区块链的供应链追溯管理平台"
    }
]


# ==================== 请求/响应模型 ====================

class PredictRequest(BaseModel):
    project_id: int
    company_name: Optional[str] = "默认投标公司"
    bid_amount: Optional[float] = None


class PredictResponse(BaseModel):
    project_id: int
    project_name: str
    prediction: str  # 高/中/低
    confidence: float
    advice: str


class BidGenerateRequest(BaseModel):
    project_id: int
    company_name: str
    contact_person: str
    contact_phone: str
    bid_amount: float


# ==================== API 端点 ====================

@app.get("/")
def root():
    """API 首页"""
    # 获取数据库统计
    db_stats = {"total": 0}
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM bid_notices')
        row = cursor.fetchone()
        if row:
            db_stats["total"] = row["count"]
        conn.close()
    except:
        pass
    
    return {
        "message": "投标公司赚钱引擎 API - 真实数据版本",
        "version": "1.1.0",
        "database": {
            "total_notices": db_stats["total"],
            "status": "active" if db_stats["total"] > 0 else "empty"
        },
        "endpoints": {
            "projects": "GET /api/projects",
            "predict": "POST /api/predict",
            "bid_generate": "POST /api/bid/generate",
            "stats": "GET /api/stats",
            "crawl": "POST /api/crawl"
        }
    }


@app.get("/api/projects", response_model=List[dict])
def get_projects(category: Optional[str] = None, location: Optional[str] = None, limit: int = 50):
    """
    获取项目列表（真实招标数据）
    
    - category: 按类别筛选（可选）
    - location: 按地点筛选（可选）
    - limit: 返回数量限制（默认 50）
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 构建查询
        query = '''
            SELECT id, title as name, budget, deadline, category, region as location, 
                   description, source_url, source_site, publish_date
            FROM bid_notices
            WHERE 1=1
        '''
        params = []
        
        if category:
            query += ' AND category LIKE ?'
            params.append(f'%{category}%')
        
        if location:
            query += ' AND region LIKE ?'
            params.append(f'%{location}%')
        
        query += ' ORDER BY deadline ASC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        # 转换为字典列表
        results = []
        for row in rows:
            results.append({
                'id': row['id'],
                'name': row['name'],
                'budget': row['budget'],
                'deadline': row['deadline'],
                'category': row['category'],
                'location': row['location'],
                'description': row['description'],
                'source_url': row['source_url'],
                'source_site': row['source_site'],
                'publish_date': row['publish_date']
            })
        
        # 如果数据库为空，返回模拟数据
        if not results:
            results = PROJECTS[:limit]
            if category:
                results = [p for p in results if p["category"] == category]
            if location:
                results = [p for p in results if p["location"] == location]
        
        return results
        
    except Exception as e:
        logger.error(f"获取项目列表失败：{e}")
        # 降级返回模拟数据
        results = PROJECTS[:limit]
        if category:
            results = [p for p in results if p["category"] == category]
        if location:
            results = [p for p in results if p["location"] == location]
        return results


@app.post("/api/predict", response_model=PredictResponse)
def predict_bid_success(request: PredictRequest):
    """
    预测中标概率
    
    返回高/中/低三种预测结果
    """
    # 查找项目
    project = next((p for p in PROJECTS if p["id"] == request.project_id), None)
    
    if not project:
        raise HTTPException(status_code=404, detail=f"项目 ID {request.project_id} 不存在")
    
    # 随机生成预测结果
    predictions = [
        {"level": "高", "confidence": 0.85, "advice": "建议积极投标，中标概率较大"},
        {"level": "中", "confidence": 0.55, "advice": "可考虑投标，需优化报价策略"},
        {"level": "低", "confidence": 0.25, "advice": "谨慎评估，建议调整投标策略"}
    ]
    
    result = random.choice(predictions)
    
    return PredictResponse(
        project_id=request.project_id,
        project_name=project["name"],
        prediction=result["level"],
        confidence=result["confidence"],
        advice=result["advice"]
    )


@app.post("/api/bid/generate")
def generate_bid_document(request: BidGenerateRequest):
    """
    生成投标文件（Word 格式）
    
    返回可下载的 .docx 文件
    """
    # 查找项目
    project = next((p for p in PROJECTS if p["id"] == request.project_id), None)
    
    if not project:
        raise HTTPException(status_code=404, detail=f"项目 ID {request.project_id} 不存在")
    
    # 创建 Word 文档
    doc = Document()
    
    # 标题
    doc.add_heading('投标文件', 0)
    
    # 项目信息
    doc.add_heading('一、项目信息', level=1)
    doc.add_paragraph(f'项目名称：{project["name"]}')
    doc.add_paragraph(f'项目预算：¥{project["budget"]:,.2f}')
    doc.add_paragraph(f'截止日期：{project["deadline"]}')
    doc.add_paragraph(f'项目类别：{project["category"]}')
    doc.add_paragraph(f'项目地点：{project["location"]}')
    doc.add_paragraph(f'项目描述：{project["description"]}')
    
    # 投标公司信息
    doc.add_heading('二、投标公司信息', level=1)
    doc.add_paragraph(f'公司名称：{request.company_name}')
    doc.add_paragraph(f'联系人：{request.contact_person}')
    doc.add_paragraph(f'联系电话：{request.contact_phone}')
    
    # 报价信息
    doc.add_heading('三、投标报价', level=1)
    doc.add_paragraph(f'投标金额：¥{request.bid_amount:,.2f}')
    
    # 生成时间
    doc.add_heading('四、生成时间', level=1)
    doc.add_paragraph(f'文件生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    
    # 保存到内存
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=bid_{project['id']}_{request.company_name}.docx"}
    )


@app.get("/api/stats")
def get_stats():
    """获取数据库统计信息"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 总数
        cursor.execute('SELECT COUNT(*) as count FROM bid_notices')
        total = cursor.fetchone()["count"]
        
        # 按来源统计
        cursor.execute('SELECT source_site, COUNT(*) as count FROM bid_notices GROUP BY source_site')
        by_source = {row["source_site"]: row["count"] for row in cursor.fetchall()}
        
        # 按地区统计
        cursor.execute('SELECT region, COUNT(*) as count FROM bid_notices WHERE region != "" GROUP BY region ORDER BY count DESC LIMIT 10')
        by_region = {row["region"]: row["count"] for row in cursor.fetchall()}
        
        # 最新更新时间
        cursor.execute('SELECT MAX(crawl_time) as last_update FROM bid_notices')
        last_update = cursor.fetchone()["last_update"]
        
        conn.close()
        
        return {
            "total": total,
            "by_source": by_source,
            "by_region": by_region,
            "last_update": last_update,
            "status": "success"
        }
    except Exception as e:
        logger.error(f"获取统计失败：{e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/crawl")
def trigger_crawl():
    """手动触发爬虫任务"""
    try:
        from crawler.gov_crawler import crawl_all
        
        logger.info("手动触发爬虫任务...")
        results = crawl_all()
        
        return {
            "status": "success",
            "message": "爬虫任务执行完成",
            "results": results
        }
    except Exception as e:
        logger.error(f"爬虫任务失败：{e}")
        raise HTTPException(status_code=500, detail=f"爬虫执行失败：{str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
