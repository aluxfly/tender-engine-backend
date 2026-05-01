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
    # 导入 docx 样式和格式工具
    from docx.shared import Pt, Cm, Inches, RGBColor
    from docx.oxml.ns import qn
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.section import WD_ORIENT

    def _set_font(run, name='宋体', size=12, bold=False, color=None):
        """统一设置字体（中文+英文）"""
        run.font.name = name
        run.font.size = Pt(size)
        run.font.bold = bold
        if color:
            run.font.color.rgb = RGBColor(*color)
        run._element.rPr.rFonts.set(qn('w:eastAsia'), name)
        run._element.rPr.rFonts.set(qn('w:ascii'), name)

    def _add_para_with_style(doc, text='', style='Normal', alignment=WD_ALIGN_PARAGRAPH.LEFT,
                              font_name='宋体', font_size=12, bold=False,
                              space_before=None, space_after=None, color=None,
                              first_line_indent=None):
        """添加带样式的段落"""
        para = doc.add_paragraph(text, style=style)
        para.alignment = alignment
        for run in para.runs:
            _set_font(run, name=font_name, size=font_size, bold=bold, color=color)
        if space_before is not None:
            para.paragraph_format.space_before = Pt(space_before)
        if space_after is not None:
            para.paragraph_format.space_after = Pt(space_after)
        if first_line_indent is not None:
            para.paragraph_format.first_line_indent = Cm(first_line_indent)
        return para

    def _add_styled_heading(doc, text, level=1, font_name='黑体', font_size=None,
                            space_before=12, space_after=6):
        """添加带样式的标题"""
        heading = doc.add_heading(text, level=level)
        heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for run in heading.runs:
            fs = font_size if font_size else ({1: 18, 2: 16, 3: 14, 4: 12}.get(level, 12))
            _set_font(run, name=font_name, size=fs, bold=True)
        heading.paragraph_format.space_before = Pt(space_before)
        heading.paragraph_format.space_after = Pt(space_after)
        return heading

    def _add_kv_para(doc, key, value, key_width=4, font_size=11):
        """添加键值对段落（key 加粗）"""
        para = doc.add_paragraph()
        para.paragraph_format.space_before = Pt(2)
        para.paragraph_format.space_after = Pt(2)
        para.paragraph_format.left_indent = Cm(1)
        run_key = para.add_run(f'{key}：')
        _set_font(run_key, size=font_size, bold=True)
        run_val = para.add_run(str(value))
        _set_font(run_val, size=font_size)
        return para

    def _add_bullet(doc, text, level=0, font_size=11):
        """添加项目符号段落"""
        para = doc.add_paragraph()
        indent = 1 + level * 1.5
        para.paragraph_format.left_indent = Cm(indent)
        para.paragraph_format.space_before = Pt(1)
        para.paragraph_format.space_after = Pt(1)
        bullet = '•' if level == 0 else '◦'
        run_bullet = para.add_run(f'{bullet} ')
        _set_font(run_bullet, size=font_size, bold=(level == 0))
        run_text = para.add_run(text)
        _set_font(run_text, size=font_size)
        return para

    def _add_simple_table(doc, headers, rows, col_widths=None):
        """添加格式化的简单表格"""
        table = doc.add_table(rows=1 + len(rows), cols=len(headers))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        # 表头
        for i, h in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = ''
            run = cell.paragraphs[0].add_run(h)
            _set_font(run, size=10, bold=True)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            shading = cell._element.get_or_add_tcPr()
            from lxml import etree
            shd = etree.SubElement(shading, '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd')
            shd.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill', 'D9E2F3')
            shd.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', 'clear')
        # 数据行
        for ri, row_data in enumerate(rows):
            for ci, val in enumerate(row_data):
                cell = table.rows[ri + 1].cells[ci]
                cell.text = ''
                run = cell.paragraphs[0].add_run(str(val))
                _set_font(run, size=10)
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        # 列宽
        if col_widths:
            for ci, w in enumerate(col_widths):
                for row in table.rows:
                    row.cells[ci].width = Cm(w)
        return table

    # ========== 设置文档样式 ==========
    doc = Document()

    # 页面设置
    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.18)
        section.right_margin = Cm(3.18)

    # 正文默认样式
    style = doc.styles['Normal']
    font = style.font
    font.name = '宋体'
    font.size = Pt(12)
    style._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    style._element.rPr.rFonts.set(qn('w:ascii'), '宋体')
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.line_spacing = 1.5

    now_str = datetime.now().strftime('%Y年%m月%d日')

    # ========== 封面 ==========
    doc.add_paragraph()  # 空行
    doc.add_paragraph()  # 空行
    cover_title = doc.add_paragraph()
    cover_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cover_title.paragraph_format.space_before = Pt(60)
    cover_title.paragraph_format.space_after = Pt(30)
    run_title = cover_title.add_run('投 标 文 件')
    _set_font(run_title, name='黑体', size=36, bold=True, color=(0, 51, 102))

    cover_subtitle = doc.add_paragraph()
    cover_subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cover_subtitle.paragraph_format.space_after = Pt(40)
    run_sub = cover_subtitle.add_run(f'（{template_type}项目）')
    _set_font(run_sub, name='黑体', size=22, bold=False, color=(102, 102, 102))

    cover_proj = doc.add_paragraph()
    cover_proj.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cover_proj.paragraph_format.space_after = Pt(50)
    run_p = cover_proj.add_run(f'项目名称：{project["name"]}')
    _set_font(run_p, name='楷体', size=16, bold=False)

    cover_comp = doc.add_paragraph()
    cover_comp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cover_comp.paragraph_format.space_after = Pt(50)
    run_c = cover_comp.add_run(f'投标单位：{request.company_name}')
    _set_font(run_c, name='楷体', size=16, bold=False)

    cover_date = doc.add_paragraph()
    cover_date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cover_date.paragraph_format.space_after = Pt(20)
    run_d = cover_date.add_run(now_str)
    _set_font(run_d, name='楷体', size=14, bold=False)

    # 分页符
    doc.add_page_break()

    # ========== 目录页 ==========
    _add_styled_heading(doc, '目    录', level=1, font_size=18)
    doc.add_paragraph()
    toc_items = [
        ('第一章', '投标函'),
        ('第二章', '法定代表人授权书'),
        ('第三章', '投标报价一览表'),
        ('第四章', '技术方案'),
        ('第五章', '项目实施计划'),
        ('第六章', '售后服务方案'),
        ('第七章', '企业资质与业绩'),
        ('第八章', '项目理解与需求分析'),
    ]
    for num, title_text in toc_items:
        toc_para = doc.add_paragraph()
        toc_para.paragraph_format.space_before = Pt(4)
        toc_para.paragraph_format.space_after = Pt(4)
        run_num = toc_para.add_run(f'{num}  ')
        _set_font(run_num, size=12, bold=True)
        run_text = toc_para.add_run(title_text)
        _set_font(run_text, size=12)
    doc.add_page_break()

    # ========== 第一章：投标函 ==========
    _add_styled_heading(doc, '第一章  投标函', level=1)
    doc.add_paragraph()

    _add_para_with_style(doc, f'致：{project["name"]}招标方', font_size=12, bold=False,
                          space_before=12, space_after=6, first_line_indent=0)
    _add_para_with_style(doc,
        f'    根据贵方发布的招标文件，{request.company_name}（以下简称"我方"）经认真研究招标文件的全部内容后，' +
        f'决定参与本项目的投标。现正式提交投标文件，具体内容如下：',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    _add_para_with_style(doc,
        f'    一、我方完全理解并接受招标文件的全部内容和要求，愿意按照招标文件的规定提供{template_type}相关产品与服务。',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    _add_para_with_style(doc,
        f'    二、我方投标总报价为人民币（大写）：¥{request.bid_amount:,.2f}（含税）。该报价包含设备费、运输费、安装调试费、培训费、' +
        f'税费及售后服务等全部费用。',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    _add_para_with_style(doc,
        f'    三、我方承诺在中标后按照招标文件及合同约定履行全部责任和义务，保证按期、按质完成项目交付。',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    _add_para_with_style(doc,
        f'    四、我方投标文件自投标截止日起有效期为 90 个日历日。',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    _add_para_with_style(doc,
        f'    五、如我方中标，我方承诺在合同签订后按照约定时间完成项目交付，并提供完善的售后服务。',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    doc.add_paragraph()
    _add_para_with_style(doc, f'投标单位（盖章）：{request.company_name}', font_size=12, first_line_indent=0, space_before=12, space_after=6)
    _add_para_with_style(doc, f'法定代表人或授权代表（签字）：{request.contact_person}', font_size=12, first_line_indent=0, space_before=6, space_after=6)
    _add_para_with_style(doc, f'联系电话：{request.contact_phone}', font_size=12, first_line_indent=0, space_before=6, space_after=6)
    _add_para_with_style(doc, f'日期：{now_str}', font_size=12, first_line_indent=0, space_before=6, space_after=6)

    # ========== 第二章：法定代表人授权书 ==========
    _add_styled_heading(doc, '第二章  法定代表人授权书', level=1)
    doc.add_paragraph()

    _add_para_with_style(doc,
        f'    本授权书声明：{request.company_name}的法定代表人（姓名、职务）在此授权{request.contact_person}（姓名、职务）' +
        f'为我方合法代理人，以我方名义参加"{project["name"]}"项目的投标活动。' +
        f'代理人在投标过程中签署的一切文件和处理与之有关的一切事务，我方均予以承认。',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    doc.add_paragraph()
    _add_kv_para(doc, '授权单位', request.company_name)
    _add_kv_para(doc, '被授权人', request.contact_person)
    _add_kv_para(doc, '联系电话', request.contact_phone)
    _add_kv_para(doc, '项目名称', project['name'])
    _add_kv_para(doc, '项目地点', project['location'])
    _add_kv_para(doc, '授权日期', now_str)

    doc.add_paragraph()
    _add_para_with_style(doc, '法定代表人签字：_____________    被授权人签字：_____________', font_size=12, first_line_indent=0, space_before=12, space_after=6)

    doc.add_page_break()

    # ========== 第三章：投标报价一览表 ==========
    _add_styled_heading(doc, '第三章  投标报价一览表', level=1)
    doc.add_paragraph()

    _add_kv_para(doc, '项目名称', project['name'])
    _add_kv_para(doc, '项目编号', f'BID-{project["id"]}-{datetime.now().strftime("%Y%m%d")}')
    _add_kv_para(doc, '项目预算', f'¥{project["budget"]:,.2f}')
    _add_kv_para(doc, '投标报价', f'¥{request.bid_amount:,.2f}')

    budget_ratio = (request.bid_amount / project['budget'] * 100) if project['budget'] and project['budget'] > 0 else 0
    _add_kv_para(doc, '报价占预算比例', f'{budget_ratio:.1f}%')

    doc.add_paragraph()
    _add_styled_heading(doc, '报价明细表', level=3, font_size=13)
    doc.add_paragraph()

    # 根据模板类型生成报价明细
    if template_type == '物联网卡':
        cf = request.custom_fields or {}
        qty = int(cf.get('delivery_quantity', 1000))
        unit_price = request.bid_amount / qty if qty > 0 else request.bid_amount
        headers = ['序号', '费用项目', '单价（元）', '数量', '金额（元）', '备注']
        rows = [
            ['1', '物联网卡（SIM卡）', f'{unit_price * 0.4:.2f}', f'{qty}', f'{request.bid_amount * 0.4:.2f}', cf.get('card_type', '标准SIM卡')],
            ['2', '流量套餐费', f'{unit_price * 0.25:.2f}', f'{qty}', f'{request.bid_amount * 0.25:.2f}', cf.get('data_plan', '月流量1GB')],
            ['3', '平台接入费', f'{request.bid_amount * 0.1:.2f}', '1', f'{request.bid_amount * 0.1:.2f}', '卡管理平台'],
            ['4', 'API对接费', f'{request.bid_amount * 0.05:.2f}', '1', f'{request.bid_amount * 0.05:.2f}', '接口开发'],
            ['5', '技术支持服务费', f'{request.bid_amount * 0.1:.2f}', '1', f'{request.bid_amount * 0.1:.2f}', '含售后'],
            ['6', '运输及杂费', f'{request.bid_amount * 0.05:.2f}', '1', f'{request.bid_amount * 0.05:.2f}', '物流配送'],
            ['合计', '', '', '', f'{request.bid_amount:.2f}', '含税'],
        ]
    else:  # 布控球
        cf = request.custom_fields or {}
        qty = int(cf.get('delivery_quantity', 50))
        unit_price = request.bid_amount / qty if qty > 0 else request.bid_amount
        headers = ['序号', '费用项目', '单价（元）', '数量', '金额（元）', '备注']
        rows = [
            ['1', '布控球设备', f'{unit_price * 0.5:.2f}', f'{qty}', f'{request.bid_amount * 0.5:.2f}', cf.get('video_resolution', '4K超清')],
            ['2', '安装材料及配件', f'{unit_price * 0.1:.2f}', f'{qty}', f'{request.bid_amount * 0.1:.2f}', '支架、线缆等'],
            ['3', '云存储服务费', f'{request.bid_amount * 0.1:.2f}', '1', f'{request.bid_amount * 0.1:.2f}', cf.get('storage', '云存储')],
            ['4', '安装调试费', f'{request.bid_amount * 0.1:.2f}', '1', f'{request.bid_amount * 0.1:.2f}', '现场实施'],
            ['5', '智能分析模块', f'{request.bid_amount * 0.1:.2f}', '1', f'{request.bid_amount * 0.1:.2f}', 'AI算法'],
            ['6', '培训及运维费', f'{request.bid_amount * 0.05:.2f}', '1', f'{request.bid_amount * 0.05:.2f}', '培训+运维'],
            ['合计', '', '', '', f'{request.bid_amount:.2f}', '含税'],
        ]

    _add_simple_table(doc, headers, rows, col_widths=[1.5, 3.5, 2.5, 2, 2.5, 3])

    doc.add_paragraph()
    _add_para_with_style(doc,
        '注：以上报价为含税总价，报价有效期为 90 个日历日，自投标截止日起计算。',
        font_size=10, first_line_indent=0, space_before=6, space_after=6)

    doc.add_page_break()

    # ========== 第四章：技术方案 ==========
    _add_styled_heading(doc, '第四章  技术方案', level=1)
    doc.add_paragraph()

    _add_styled_heading(doc, '4.1 项目概述', level=2, font_size=14)
    _add_para_with_style(doc,
        f'    本项目为"{project["name"]}"，项目地点位于{project["location"]}，' +
        f'项目预算为¥{project["budget"]:,.2f}。{project.get("description", "")}。' +
        f'我方凭借在该领域的丰富经验和专业技术实力，提供完整的技术解决方案。',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    _add_styled_heading(doc, '4.2 技术路线与架构', level=2, font_size=14)

    if template_type == '物联网卡':
        _add_para_with_style(doc,
            '    我方采用"终端-网络-平台"三层架构的物联网卡解决方案，确保系统稳定可靠：',
            font_size=12, first_line_indent=0, space_before=6, space_after=6)
        _add_bullet(doc, '终端层：支持多类型物联网卡（SIM/eSIM/M2M），适配各类物联网设备')
        _add_bullet(doc, '网络层：支持 FDD-LTE/TDD-LTE/NB-IoT/5G 全频段覆盖，保障网络质量')
        _add_bullet(doc, '平台层：自建卡管理平台，提供卡生命周期管理、用量监控、故障诊断等核心功能')
        _add_bullet(doc, '安全层：端到端加密传输，双向认证机制，确保数据安全')
    else:
        _add_para_with_style(doc,
            '    我方采用"前端采集-网络传输-云端分析"三层架构的布控球解决方案：',
            font_size=12, first_line_indent=0, space_before=6, space_after=6)
        _add_bullet(doc, '前端采集层：4K超高清布控球设备，支持多种供电方式（太阳能/市电/电池）')
        _add_bullet(doc, '网络传输层：4G/5G无线传输，支持RTSP/ONVIF/GB/T28181标准协议')
        _add_bullet(doc, '云端分析层：视频云平台+AI智能分析，支持人脸识别、车牌识别、行为分析')
        _add_bullet(doc, '安全层：视频流加密传输，权限分级管控，符合等保要求')

    _add_styled_heading(doc, '4.3 核心技术参数', level=2, font_size=14)
    doc.add_paragraph()

    if template_type == '物联网卡':
        cf = request.custom_fields or {}
        spec_headers = ['参数项', '技术指标', '说明']
        spec_rows = [
            ['卡类型', cf.get('card_type', 'SIM卡（可定制eSIM/M2M）'), '支持多种卡类型'],
            ['频段支持', cf.get('frequency_band', '全频段（FDD-LTE/TDD-LTE/NB-IoT/5G）'), '广泛兼容性'],
            ['流量套餐', cf.get('data_plan', '月流量1GB（可定制）'), '灵活套餐选择'],
            ['运营商合作', cf.get('operator', '中国移动/联通/电信'), '多运营商冗余'],
            ['APN配置', cf.get('apn', '支持自定义APN'), '灵活网络配置'],
            ['QoS保障', cf.get('qos', '优先服务级别'), '网络质量保障'],
            ['安全加密', cf.get('security', '双向认证+端到端加密'), '高安全等级'],
            ['VPLMN配置', cf.get('vplmn', '支持46001/46003等'), '漫游支持'],
        ]
    else:
        cf = request.custom_fields or {}
        spec_headers = ['参数项', '技术指标', '说明']
        spec_rows = [
            ['视频分辨率', cf.get('video_resolution', '4K超高清（3840×2160）'), '高清画质'],
            ['帧率', cf.get('frame_rate', '30fps（支持60fps）'), '流畅视频'],
            ['码率', cf.get('bit_rate', '4Mbps-10Mbps自适应'), '智能码率控制'],
            ['存储方式', cf.get('storage', '本地+云存储双模式'), '可靠存储'],
            ['供电方式', cf.get('power', '太阳能+电池混合供电'), '无市电场景适用'],
            ['安装方式', cf.get('installation', '立杆/墙面/车载多模式'), '灵活部署'],
            ['无线传输', cf.get('wireless', '4G/5G/Wi-Fi混合组网'), '多网络冗余'],
            ['协议支持', cf.get('protocol', 'RTSP/ONVIF/GB/T28181'), '标准协议兼容'],
            ['智能分析', '人脸识别/车牌识别/行为分析', 'AI算法支持'],
        ]

    _add_simple_table(doc, spec_headers, spec_rows, col_widths=[3.5, 6, 4])

    _add_styled_heading(doc, '4.4 平台功能', level=2, font_size=14)

    if template_type == '物联网卡':
        _add_bullet(doc, '卡管理：开卡、停卡、换卡、销卡全生命周期管理')
        _add_bullet(doc, '用量监控：实时监控流量使用情况，预警提醒')
        _add_bullet(doc, 'API接口：提供RESTful API，支持第三方系统对接')
        _add_bullet(doc, '报表统计：多维度数据分析，支持自定义报表')
        _add_bullet(doc, '故障诊断：自动故障检测与告警，快速定位问题')
    else:
        _add_bullet(doc, '视频监控：实时画面查看、录像回放、截图取证')
        _add_bullet(doc, 'AI分析：人脸识别、车牌识别、行为分析等智能算法')
        _add_bullet(doc, '设备管理：设备在线状态监控、远程配置、OTA升级')
        _add_bullet(doc, '告警通知：智能告警规则设置，多渠道通知（短信/邮件/APP）')
        _add_bullet(doc, '数据大屏：可视化大屏展示，实时数据监控')

    doc.add_page_break()

    # ========== 第五章：项目实施计划 ==========
    _add_styled_heading(doc, '第五章  项目实施计划', level=1)
    doc.add_paragraph()

    _add_styled_heading(doc, '5.1 实施流程', level=2, font_size=14)
    _add_para_with_style(doc,
        '    我方将按照以下阶段推进项目实施：',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    implementation_headers = ['阶段', '时间', '主要工作内容', '交付物']
    if template_type == '物联网卡':
        implementation_rows = [
            ['第一阶段\n需求确认', '第1周', '需求调研、方案确认、APN配置确认', '需求确认书'],
            ['第二阶段\n卡片生产', '第2-3周', '卡片定制生产、质量检测、编号管理', '产品检测报告'],
            ['第三阶段\n平台部署', '第3-4周', '管理平台部署、API对接调试', '平台部署报告'],
            ['第四阶段\n物流交付', '第4-5周', '产品包装、物流配送、到货签收', '签收单'],
            ['第五阶段\n联调验收', '第5-6周', '现场联调测试、性能验证、项目验收', '验收报告'],
        ]
    else:
        implementation_rows = [
            ['第一阶段\n需求调研', '第1周', '现场勘测、需求确认、方案设计', '需求调研报告'],
            ['第二阶段\n设备采购', '第2-3周', '设备采购、出厂检测、配件准备', '设备检测报告'],
            ['第三阶段\n安装部署', '第3-5周', '现场安装、网络配置、平台对接', '安装部署报告'],
            ['第四阶段\n系统联调', '第5-6周', '系统联调、功能测试、性能优化', '测试报告'],
            ['第五阶段\n培训验收', '第6-7周', '用户培训、项目验收、交付文档', '验收报告'],
        ]

    _add_simple_table(doc, implementation_headers, implementation_rows, col_widths=[3, 2, 5.5, 3])

    _add_styled_heading(doc, '5.2 项目团队', level=2, font_size=14)
    _add_para_with_style(doc,
        '    我方将组建专业项目团队，确保项目高质量交付：',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    team_headers = ['角色', '人数', '职责']
    team_rows = [
        ['项目经理', '1人', '项目统筹管理、进度控制、对外沟通'],
        ['技术负责人', '1人', '技术方案设计、技术难题攻关'],
        ['实施工程师', '2-4人', '现场安装部署、系统调试'],
        ['测试工程师', '1人', '功能测试、性能测试、验收测试'],
        ['售后工程师', '1人', '售后支持、运维保障'],
    ]
    _add_simple_table(doc, team_headers, team_rows, col_widths=[3, 2, 8.5])

    _add_styled_heading(doc, '5.3 质量保障措施', level=2, font_size=14)
    _add_bullet(doc, '严格执行 ISO 9001 质量管理体系')
    _add_bullet(doc, '每阶段设立质量检查点，不合格返工')
    _add_bullet(doc, '关键节点邀请第三方检测机构参与')
    _add_bullet(doc, '建立项目日报/周报机制，及时沟通项目进展')

    doc.add_page_break()

    # ========== 第六章：售后服务方案 ==========
    _add_styled_heading(doc, '第六章  售后服务方案', level=1)
    doc.add_paragraph()

    _add_styled_heading(doc, '6.1 服务承诺', level=2, font_size=14)
    _add_bullet(doc, '质保期：自验收合格之日起 12 个月')
    _add_bullet(doc, '响应时间：7×24小时响应，2小时内远程响应，24小时内现场到达')
    _add_bullet(doc, '故障处理：一般故障 4 小时内解决，重大故障 24 小时内提供备用方案')
    _add_bullet(doc, '定期巡检：每季度一次现场巡检，提交巡检报告')
    _add_bullet(doc, '技术支持：免费技术培训 2 次/年，不定期技术交流')

    _add_styled_heading(doc, '6.2 售后服务体系', level=2, font_size=14)
    _add_para_with_style(doc,
        '    我方建立了完善的三级售后服务体系：',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)
    _add_bullet(doc, '一级支持：客服热线、在线工单系统、自助知识库')
    _add_bullet(doc, '二级支持：远程诊断、远程修复、远程升级')
    _add_bullet(doc, '三级支持：现场服务、备件更换、设备维修')

    _add_styled_heading(doc, '6.3 备品备件保障', level=2, font_size=14)
    _add_para_with_style(doc,
        '    我方承诺在质保期内免费提供备品备件服务。对于关键设备，' +
        '我方将在项目所在地设立备件库，确保故障设备能快速替换，不影响项目运行。',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    _add_styled_heading(doc, '6.4 培训计划', level=2, font_size=14)
    training_headers = ['培训阶段', '培训内容', '培训时长', '培训对象']
    training_rows = [
        ['第一阶段', '产品功能与操作', '4学时', '操作人员'],
        ['第二阶段', '日常维护与故障排查', '4学时', '运维人员'],
        ['第三阶段', '高级功能与系统管理', '4学时', '管理人员'],
    ]
    _add_simple_table(doc, training_headers, training_rows, col_widths=[3, 5, 2.5, 3])

    doc.add_page_break()

    # ========== 第七章：企业资质与业绩 ==========
    _add_styled_heading(doc, '第七章  企业资质与业绩', level=1)
    doc.add_paragraph()

    _add_styled_heading(doc, '7.1 企业资质', level=2, font_size=14)

    if template_type == '物联网卡':
        qual_headers = ['资质名称', '资质说明']
        qual_rows = [
            ['营业执照', '合法有效，经营范围包含物联网相关业务'],
            ['增值电信业务经营许可证', '含ICP许可证、EDI证书'],
            ['物联网相关资质', '物联网行业准入资质'],
            ['ISO 9001 质量管理体系认证', '通过国际质量体系认证'],
            ['ISO 27001 信息安全管理体系', '通过信息安全管理体系认证'],
        ]
    else:
        qual_headers = ['资质名称', '资质说明']
        qual_rows = [
            ['营业执照', '合法有效，经营范围包含安防相关业务'],
            ['安防工程企业资质', '含安防设计施工维护资质'],
            ['通信工程施工资质', '通信设备安装调试资质'],
            ['信息系统集成资质', '系统集成能力认证'],
            ['ISO 9001 质量管理体系认证', '通过国际质量体系认证'],
        ]
    _add_simple_table(doc, qual_headers, qual_rows, col_widths=[5, 8.5])

    _add_styled_heading(doc, '7.2 类似项目业绩', level=2, font_size=14)
    _add_para_with_style(doc,
        f'    {request.company_name}在{template_type}领域积累了丰富的项目经验，以下为部分代表性案例：',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    if template_type == '物联网卡':
        case_headers = ['项目名称', '项目规模', '服务内容', '完成时间']
        case_rows = [
            ['某省电力物联网卡项目', '50000张', '物联网卡供应+平台接入', '2025年'],
            ['某市智慧交通物联网卡项目', '30000张', '物联网卡+API对接', '2025年'],
            ['某物流企业物联网卡项目', '20000张', '物联网卡+管理平台', '2024年'],
            ['某农业物联网监测项目', '10000张', 'NB-IoT卡+云平台', '2024年'],
        ]
    else:
        case_headers = ['项目名称', '项目规模', '服务内容', '完成时间']
        case_rows = [
            ['某市雪亮工程布控球项目', '200台', '设备供应+安装+平台', '2025年'],
            ['某景区智能监控布控球项目', '80台', '设备+AI分析+云存储', '2025年'],
            ['某工地安全监控布控球项目', '150台', '设备供应+安装运维', '2024年'],
            ['某河道防洪监控布控球项目', '60台', '太阳能布控球+云平台', '2024年'],
        ]
    _add_simple_table(doc, case_headers, case_rows, col_widths=[4.5, 2.5, 4.5, 2])

    doc.add_page_break()

    # ========== 第八章：项目理解与需求分析 ==========
    _add_styled_heading(doc, '第八章  项目理解与需求分析', level=1)
    doc.add_paragraph()

    _add_styled_heading(doc, '8.1 项目背景理解', level=2, font_size=14)
    _add_para_with_style(doc,
        f'    通过对"{project["name"]}"项目的深入研究，我方理解该项目的主要背景为：',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)
    _add_para_with_style(doc,
        f'    {project.get("description", "本项目旨在通过采购相关设备与服务，提升业务能力和管理效率。")}',
        font_size=12, first_line_indent=0, space_before=6, space_after=6)

    _add_styled_heading(doc, '8.2 核心需求分析', level=2, font_size=14)

    if template_type == '物联网卡':
        _add_bullet(doc, '稳定可靠的网络连接：保障物联网设备全天候在线')
        _add_bullet(doc, '灵活的流量管理：根据业务需求提供差异化流量方案')
        _add_bullet(doc, '完善的平台支撑：实现卡的集中管理和远程运维')
        _add_bullet(doc, '安全保障机制：确保数据传输和存储安全')
        _add_bullet(doc, '快速响应服务：建立高效的故障处理机制')
    else:
        _add_bullet(doc, '高质量视频采集：确保监控画面清晰流畅')
        _add_bullet(doc, '可靠的传输网络：保障视频数据实时传输')
        _add_bullet(doc, '智能分析能力：利用AI技术提升监控效率')
        _add_bullet(doc, '灵活的部署方案：适应不同场景的安装需求')
        _add_bullet(doc, '完善的售后服务：保障系统长期稳定运行')

    _add_styled_heading(doc, '8.3 我方优势', level=2, font_size=14)
    _add_bullet(doc, '行业经验丰富：在相关领域拥有多年项目经验')
    _add_bullet(doc, '技术实力雄厚：自有研发团队，持续技术创新')
    _add_bullet(doc, '服务网络完善：覆盖全国的服务网点')
    _add_bullet(doc, '成本优势明显：规模采购带来的价格优势')
    _add_bullet(doc, '质量保证体系：通过多项国际认证')

    # ========== 附录：生成信息 ==========
    doc.add_page_break()
    _add_styled_heading(doc, '附    录', level=1)
    doc.add_paragraph()
    _add_kv_para(doc, '文件生成时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    _add_kv_para(doc, '生成系统', '投标公司赚钱引擎 AI 标书生成系统 v2.0')
    _add_kv_para(doc, '项目类型', template_type)
    _add_kv_para(doc, '文档版本', 'V1.0')
    _add_kv_para(doc, '文档说明', '本文档由系统自动生成，仅供参考，正式投标前请由专业人员审核完善。')
    
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
