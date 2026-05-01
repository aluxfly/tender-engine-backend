"""
投标公司赚钱引擎 MVP 后端 API
FastAPI 单文件实现
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import random
from datetime import datetime
from docx import Document
from io import BytesIO
from fastapi.responses import StreamingResponse
import sqlite3
from pathlib import Path
import logging
import json

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    logger.info("应用启动中...")
    init_database()
    logger.info("应用启动完成")
    yield
    # 关闭时清理（如有需要）
    logger.info("应用关闭")


app = FastAPI(
    title="投标公司赚钱引擎 API",
    description="MVP 版本 - 项目查询、中标预测、标书生成",
    version="1.0.0",
    lifespan=lifespan
)

# 启用 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 前端页面由手动路由服务（见下方 @app.get("/") 等）

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


def init_database():
    """初始化数据库 - 如果为空则加载初始数据"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bid_notices'")
        if not cursor.fetchone():
            logger.info("创建 bid_notices 表...")
            cursor.execute('''
                CREATE TABLE bid_notices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    region TEXT,
                    budget REAL,
                    deadline TEXT,
                    description TEXT,
                    source_url TEXT,
                    source_site TEXT,
                    source TEXT,
                    category TEXT,
                    publish_date TEXT,
                    crawl_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    content_hash TEXT
                )
            ''')
            conn.commit()
        else:
            # 迁移：检查是否有 source 字段
            cursor.execute("PRAGMA table_info(bid_notices)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'source' not in columns:
                logger.info("添加 source 字段...")
                cursor.execute("ALTER TABLE bid_notices ADD COLUMN source TEXT")
                conn.commit()
        
        # 检查数据是否为空
        cursor.execute('SELECT COUNT(*) as count FROM bid_notices')
        count = cursor.fetchone()['count']
        
        if count == 0:
            logger.info("数据库为空，加载初始数据...")
            initial_data_path = Path(__file__).parent / 'initial_data.json'
            
            if initial_data_path.exists():
                import json
                with open(initial_data_path, 'r', encoding='utf-8') as f:
                    initial_data = json.load(f)
                
                for item in initial_data:
                    cursor.execute('''
                        INSERT INTO bid_notices 
                        (title, region, budget, deadline, description, source_url, source_site, source, category, publish_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        item['title'],
                        item['region'],
                        item['budget'],
                        item['deadline'],
                        item['description'],
                        item['source_url'],
                        item['source_site'],
                        item.get('source', ''),
                        item['category'],
                        item['publish_date']
                    ))
                
                conn.commit()
                logger.info(f"已加载 {len(initial_data)} 条初始数据")
            else:
                logger.warning("初始数据文件不存在")
        else:
            logger.info(f"数据库已有 {count} 条数据，跳过初始化")
        
        conn.close()
        logger.info(f"数据库初始化完成")
        
    except Exception as e:
        logger.error(f"数据库初始化失败：{e}")


# ==================== 模拟数据已删除 ====================
# 只使用数据库真实数据，不再提供模拟数据降级


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
    project_type: Optional[str] = "物联网卡"  # 物联网卡/布控球
    custom_fields: Optional[Dict[str, Any]] = None  # 自定义字段


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
            "crawl": "POST /api/crawl",
            "reload_data": "POST /api/reload-data"
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
                   description, source_url, source_site, source, publish_date
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
                'source': row['source'],
                'publish_date': row['publish_date']
            })
        
        return results
    
    except Exception as e:
        logger.error(f"获取项目失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/filter")
def filter_projects(keywords: Optional[str] = None, project_type: Optional[str] = None):
    """
    筛选项目（物联网卡/布控球）
    
    - keywords: 关键词，逗号分隔
    - project_type: 项目类型（物联网卡/布控球）
    """
    try:
        # 读取示例数据文件
        import json
        data_file = Path(__file__).parent / 'data.json'
        
        if not data_file.exists():
            return []
        
        with open(data_file, 'r', encoding='utf-8') as f:
            all_projects = json.load(f)
        
        # 筛选逻辑
        if not keywords and not project_type:
            return all_projects[:15]  # 默认返回 15 条
        
        filtered = []
        keyword_list = keywords.split(',') if keywords else []
        
        for project in all_projects:
            match = False
            
            # 按类型筛选
            if project_type and project.get('type') == project_type:
                match = True
            
            # 按关键词筛选
            if keyword_list:
                project_name = project.get('name', '').lower()
                for kw in keyword_list:
                    if kw.lower() in project_name:
                        match = True
                        break
            
            if match:
                filtered.append(project)
        
        return filtered[:15]  # 最多返回 15 条
    
    except Exception as e:
        logger.error(f"筛选项目失败：{e}")
        return []


@app.post("/api/predict", response_model=PredictResponse)
def predict_bid_success(request: PredictRequest):
    """
    预测中标概率
    
    返回高/中/低三种预测结果
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, title FROM bid_notices WHERE id = ?', (request.project_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail=f"项目 ID {request.project_id} 不存在")
        
        project_name = row['title']
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询项目失败：{e}")
        raise HTTPException(status_code=500, detail=f"数据库查询失败：{str(e)}")
    
    # 随机生成预测结果
    predictions = [
        {"level": "高", "confidence": 0.85, "advice": "建议积极投标，中标概率较大"},
        {"level": "中", "confidence": 0.55, "advice": "可考虑投标，需优化报价策略"},
        {"level": "低", "confidence": 0.25, "advice": "谨慎评估，建议调整投标策略"}
    ]
    
    result = random.choice(predictions)
    
    return PredictResponse(
        project_id=request.project_id,
        project_name=project_name,
        prediction=result["level"],
        confidence=result["confidence"],
        advice=result["advice"]
    )


@app.post("/api/bid/generate")
def generate_bid_document(request: BidGenerateRequest):
    """
    生成投标文件（Word 格式）
    
    支持物联网卡和布控球两种模板
    返回可下载的 .docx 文件
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, title, budget, deadline, category, region, description FROM bid_notices WHERE id = ?', (request.project_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail=f"项目 ID {request.project_id} 不存在")
        
        project = {
            'id': row['id'],
            'name': row['title'],
            'budget': row['budget'],
            'deadline': row['deadline'],
            'category': row['category'],
            'location': row['region'],
            'description': row['description']
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询项目失败：{e}")
        raise HTTPException(status_code=500, detail=f"数据库查询失败：{str(e)}")
    
    # 根据项目类型选择模板
    template_type = request.project_type if request.project_type in ['物联网卡', '布控球'] else '物联网卡'
    
    # 加载模板文件
    template = None
    if template_type == '物联网卡':
        template_path = Path(__file__).parent / 'templates' / 'iot-sim-card-template.json'
    else:
        template_path = Path(__file__).parent / 'templates' / 'surveillance-ball-template.json'
    
    if template_path.exists():
        with open(template_path, 'r', encoding='utf-8') as f:
            template = json.load(f)
    
    # 创建 Word 文档
    from docx.shared import Pt
    from docx.oxml.ns import qn
    
    doc = Document()
    
    # 设置中文字体支持
    doc.styles['Normal'].font.name = '宋体'
    doc.styles['Normal']._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    doc.styles['Normal']._element.rPr.rFonts.set(qn('w:ascii'), '宋体')
    
    # 标题
    title = doc.add_heading(f'{template_type}投标文件', 0)
    title.runs[0].font.name = '宋体'
    title.runs[0]._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    
    # 项目信息
    heading1 = doc.add_heading('一、项目信息', level=1)
    heading1.runs[0].font.name = '宋体'
    heading1.runs[0]._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    
    doc.add_paragraph(f'项目名称：{project["name"]}')
    doc.add_paragraph(f'项目预算：¥{project["budget"]:,.2f}')
    doc.add_paragraph(f'截止日期：{project["deadline"]}')
    doc.add_paragraph(f'项目类别：{project["category"]}')
    doc.add_paragraph(f'项目地点：{project["location"]}')
    doc.add_paragraph(f'项目描述：{project["description"]}')
    
    # 投标公司信息
    heading2 = doc.add_heading('二、投标公司信息', level=1)
    heading2.runs[0].font.name = '宋体'
    heading2.runs[0]._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    
    doc.add_paragraph(f'公司名称：{request.company_name}')
    doc.add_paragraph(f'联系人：{request.contact_person}')
    doc.add_paragraph(f'联系电话：{request.contact_phone}')
    
    # 报价信息
    heading3 = doc.add_heading('三、投标报价', level=1)
    heading3.runs[0].font.name = '宋体'
    heading3.runs[0]._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    
    doc.add_paragraph(f'投标金额：¥{request.bid_amount:,.2f}')
    
    # 自定义字段（根据模板类型）
    if template and request.custom_fields:
        heading4 = doc.add_heading('四、自定义字段', level=1)
        heading4.runs[0].font.name = '宋体'
        heading4.runs[0]._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
        
        for key, value in request.custom_fields.items():
            doc.add_paragraph(f'{key}：{value}')
    elif template:
        # 使用模板默认字段
        heading4 = doc.add_heading('四、技术规格', level=1)
        heading4.runs[0].font.name = '宋体'
        heading4.runs[0]._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
        
        if template.get('template_id') == 'iot-sim-card':
            doc.add_paragraph(f'卡类型：{request.custom_fields.get("card_type", "SIM卡") if request.custom_fields else "SIM卡"}')
            doc.add_paragraph(f'频段支持：{request.custom_fields.get("frequency_band", "全频段") if request.custom_fields else "全频段"}')
            doc.add_paragraph(f'流量套餐：{request.custom_fields.get("data_plan", "月流量1GB") if request.custom_fields else "月流量1GB"}')
            doc.add_paragraph(f'运营商：{request.custom_fields.get("operator", "中国移动") if request.custom_fields else "中国移动"}')
        elif template.get('template_id') == 'surveillance-ball':
            doc.add_paragraph(f'视频分辨率：{request.custom_fields.get("video_resolution", "4K") if request.custom_fields else "4K"}')
            doc.add_paragraph(f'帧率：{request.custom_fields.get("frame_rate", "30fps") if request.custom_fields else "30fps"}')
            doc.add_paragraph(f'存储方式：{request.custom_fields.get("storage", "云存储") if request.custom_fields else "云存储"}')
            doc.add_paragraph(f'供电方式：{request.custom_fields.get("power", "太阳能") if request.custom_fields else "太阳能"}')
    
    # 生成时间
    heading5 = doc.add_heading('五、生成时间', level=1)
    heading5.runs[0].font.name = '宋体'
    heading5.runs[0]._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    
    doc.add_paragraph(f'文件生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    
    # 保存到内存
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    
    # URL 编码文件名（避免中文在 HTTP 头部中出错）
    import urllib.parse
    filename = f"{template_type}_bid_{project['id']}_{request.company_name}.docx"
    encoded_filename = urllib.parse.quote(filename, safe='')
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
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


@app.post("/api/reload-data")
def reload_initial_data():
    """手动重新加载初始数据（用于 Railway 重置后恢复数据）"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 清空现有数据
        cursor.execute("DELETE FROM bid_notices")
        conn.commit()
        logger.info("已清空现有数据...")
        
        # 加载初始数据
        initial_data_path = Path(__file__).parent / 'initial_data.json'
        
        if not initial_data_path.exists():
            raise HTTPException(status_code=500, detail="初始数据文件不存在")
        
        with open(initial_data_path, 'r', encoding='utf-8') as f:
            initial_data = json.load(f)
        
        for item in initial_data:
            cursor.execute('''
                INSERT INTO bid_notices 
                (title, region, budget, deadline, description, source_url, source_site, source, category, publish_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['title'],
                item['region'],
                item['budget'],
                item['deadline'],
                item['description'],
                item['source_url'],
                item['source_site'],
                item.get('source', ''),
                item['category'],
                item['publish_date']
            ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"已重新加载 {len(initial_data)} 条初始数据")
        
        return {
            "status": "success",
            "message": f"已重新加载 {len(initial_data)} 条初始数据",
            "count": len(initial_data)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新加载数据失败：{e}")
        raise HTTPException(status_code=500, detail=f"重新加载失败：{str(e)}")


@app.post("/api/projects/bulk-import")
def bulk_import_projects(data: List[Dict[str, Any]]):
    """批量导入项目数据（用于从本地同步数据到线上）"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 确保表有 project_code 和 status 列
        cursor.execute("PRAGMA table_info(bid_notices)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'project_code' not in columns:
            cursor.execute("ALTER TABLE bid_notices ADD COLUMN project_code TEXT")
        if 'status' not in columns:
            cursor.execute("ALTER TABLE bid_notices ADD COLUMN status TEXT")
        if 'source' not in columns:
            cursor.execute("ALTER TABLE bid_notices ADD COLUMN source TEXT")
        
        imported = 0
        skipped = 0
        
        for item in data:
            # 按 project_code 或 title+publish_date 去重
            code = item.get('project_code', '')
            if code:
                cursor.execute("SELECT id FROM bid_notices WHERE project_code = ?", (code,))
                if cursor.fetchone():
                    skipped += 1
                    continue
            
            title = item.get('title', '')
            publish_date = item.get('publish_date', '')
            cursor.execute("SELECT id FROM bid_notices WHERE title = ? AND publish_date = ?", (title, publish_date))
            if cursor.fetchone():
                skipped += 1
                continue
            
            cursor.execute('''
                INSERT INTO bid_notices
                (title, region, budget, deadline, description, source_url, source_site, source, category, publish_date, project_code, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                title,
                item.get('region', ''),
                item.get('budget', 0),
                item.get('deadline', ''),
                item.get('description', ''),
                item.get('source_url', ''),
                item.get('source_site', ''),
                item.get('source', ''),
                item.get('category', ''),
                publish_date,
                code,
                item.get('status', '')
            ))
            imported += 1
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "imported": imported,
            "skipped": skipped,
            "message": f"导入 {imported} 条，跳过 {skipped} 条（已存在）"
        }
    except Exception as e:
        logger.error(f"批量导入失败：{e}")
        raise HTTPException(status_code=500, detail=f"导入失败：{str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
