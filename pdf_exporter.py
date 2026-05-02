"""
PDF 导出功能 — Day 4/5 优化版
============================
功能:
  1. .docx → .pdf 转换
  2. 优先使用 LibreOffice（如已安装）
  3. 备选方案：pandoc、weasyprint、docx2pdf
  4. 输出 PDF 文件路径

优化项:
  - LibreOffice 转换流程稳定性增强（临时 profile + 锁文件清理）
  - 可配置转换超时
  - 转换进度查询（通过转换状态文件）
"""

import os
import subprocess
import logging
import shutil
import tempfile
import time
from typing import Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# PDF 输出目录（与合并标书共用）
PDF_OUTPUT_DIR = Path("/tmp/bid-outputs")
PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 转换状态存储
_conversion_status: dict = {}

# 默认超时（秒）
DEFAULT_TIMEOUT = 120


def _check_libreoffice() -> Optional[str]:
    """检查 LibreOffice 是否已安装，返回路径或 None"""
    lo_path = shutil.which("libreoffice") or shutil.which("soffice")
    if lo_path:
        logger.info(f"[PDF导出] LibreOffice 可用: {lo_path}")
    return lo_path


def _check_pandoc() -> Optional[str]:
    """检查 pandoc 是否已安装"""
    pd_path = shutil.which("pandoc")
    if pd_path:
        logger.info(f"[PDF导出] pandoc 可用: {pd_path}")
    return pd_path


# ==================== 转换进度追踪 ====================

def _update_conversion_status(key: str, status: str, progress: float = 0.0, detail: str = ""):
    """更新转换进度状态"""
    _conversion_status[key] = {
        "status": status,  # queued | running | done | error | timeout
        "progress": progress,  # 0.0 ~ 1.0
        "detail": detail,
        "updated_at": datetime.now().isoformat(),
    }


def _get_conversion_status(key: str) -> Optional[dict]:
    """获取转换进度"""
    return _conversion_status.get(key)


def _cleanup_conversion_status(key: str, delay: int = 300):
    """延迟清理转换状态"""
    import threading
    def _cleanup():
        time.sleep(delay)
        _conversion_status.pop(key, None)
    threading.Thread(target=_cleanup, daemon=True).start()


# ==================== LibreOffice 转换（稳定版）====================

def _convert_with_libreoffice(
    docx_path: str,
    output_path: str,
    timeout: int = DEFAULT_TIMEOUT,
    status_key: Optional[str] = None,
) -> str:
    """
    使用 LibreOffice 转换 docx → pdf（稳定增强版）。

    改进:
      - 使用独立的临时 profile 避免并发冲突
      - 清理残留锁文件
      - 可配置超时
      - 输出路径精确定位
    """
    lo_path = _check_libreoffice()
    if not lo_path:
        raise RuntimeError("LibreOffice 未安装")

    if status_key:
        _update_conversion_status(status_key, "running", 0.1, "启动 LibreOffice...")

    # 使用独立的临时 profile 避免并发转换冲突
    temp_profile = tempfile.mkdtemp(prefix="lo-profile-")

    try:
        output_dir = str(Path(output_path).parent)

        # 清理可能的残留锁文件
        lock_file = Path(temp_profile) / ".libreoffice.lock"
        lock_file.unlink(missing_ok=True)

        cmd = [
            lo_path,
            "--headless",
            "--norestore",
            "--nologo",
            "--nofirststartwizard",
            "-env:UserInstallation=file://" + temp_profile,
            "--convert-to", "pdf",
            "--outdir", output_dir,
            docx_path,
        ]

        logger.info(f"[PDF导出] 执行 LibreOffice 转换: {' '.join(cmd[:6])} ...")
        if status_key:
            _update_conversion_status(status_key, "running", 0.3, "执行转换...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if status_key:
            _update_conversion_status(status_key, "running", 0.7, "处理输出...")

        if result.returncode != 0:
            stderr = result.stderr.strip()
            # LibreOffice 有时会返回非零但实际成功了
            # 先检查输出文件是否存在
            expected_pdf = Path(output_dir) / f"{Path(docx_path).stem}.pdf"
            if expected_pdf.exists() and expected_pdf.stat().st_size > 0:
                logger.warning(f"[PDF导出] LibreOffice 返回非零码 {result.returncode}，但输出文件已生成")
            else:
                raise RuntimeError(
                    f"LibreOffice 转换失败 (exit {result.returncode}): "
                    f"{stderr or '未知错误'}"
                )

        # 定位生成的 PDF
        expected_pdf = Path(output_dir) / f"{Path(docx_path).stem}.pdf"

        if expected_pdf.exists():
            if str(expected_pdf.resolve()) != str(Path(output_path).resolve()):
                shutil.copy2(str(expected_pdf), output_path)
                expected_pdf.unlink(missing_ok=True)
            if status_key:
                _update_conversion_status(status_key, "done", 1.0, "转换完成")
            return output_path

        # 备选：扫描输出目录
        for f in Path(output_dir).glob("*.pdf"):
            if str(f.resolve()) != str(Path(output_path).resolve()):
                shutil.copy2(str(f), output_path)
                f.unlink(missing_ok=True)
                if status_key:
                    _update_conversion_status(status_key, "done", 1.0, "转换完成")
                return output_path

        raise RuntimeError(
            f"LibreOffice 转换完成但未找到输出文件 "
            f"(输出目录: {output_dir}, 期望: {expected_pdf.name})"
        )

    except subprocess.TimeoutExpired:
        if status_key:
            _update_conversion_status(status_key, "timeout", 0.0, f"转换超时 ({timeout}s)")
        raise TimeoutError(
            f"LibreOffice 转换超时 ({timeout}秒)，文件可能过大或格式复杂"
        )
    finally:
        # 清理临时 profile
        try:
            shutil.rmtree(temp_profile, ignore_errors=True)
        except Exception:
            pass


def _convert_with_pandoc(
    docx_path: str,
    output_path: str,
    timeout: int = DEFAULT_TIMEOUT,
    status_key: Optional[str] = None,
) -> str:
    """使用 pandoc 转换 docx → pdf"""
    pd_path = _check_pandoc()
    if not pd_path:
        raise RuntimeError("pandoc 未安装")

    if status_key:
        _update_conversion_status(status_key, "running", 0.1, "启动 pandoc...")

    cmd = [
        pd_path,
        docx_path,
        "-o", output_path,
        "--pdf-engine=xelatex",
    ]

    logger.info(f"[PDF导出] 执行 pandoc 转换: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        if status_key:
            _update_conversion_status(status_key, "timeout", 0.0, f"转换超时 ({timeout}s)")
        raise TimeoutError(f"pandoc 转换超时 ({timeout}秒)")

    if result.returncode != 0:
        raise RuntimeError(f"pandoc 转换失败: {result.stderr}")

    if not Path(output_path).exists():
        raise RuntimeError("pandoc 转换完成但未找到输出文件")

    if status_key:
        _update_conversion_status(status_key, "done", 1.0, "转换完成")
    return output_path


def _convert_with_weasyprint(docx_path: str, output_path: str) -> str:
    """使用 weasyprint 转换（需要先将 docx 转为 HTML）"""
    try:
        import weasyprint
    except ImportError:
        raise RuntimeError("weasyprint 未安装 (pip install weasyprint)")

    try:
        import mammoth
    except ImportError:
        raise RuntimeError("mammoth 未安装 (pip install python-mammoth)")

    with open(docx_path, "rb") as f:
        result = mammoth.convert_to_html(f)
        html_content = result.value

    styled_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        @page {{ size: A4; margin: 2.5cm; }}
        body {{ font-family: 'SimSun', 'Songti SC', serif; font-size: 12pt; line-height: 1.5; }}
        h1 {{ font-size: 18pt; font-family: 'SimHei', sans-serif; }}
        h2 {{ font-size: 16pt; font-family: 'SimHei', sans-serif; }}
        h3 {{ font-size: 14pt; font-family: 'SimHei', sans-serif; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ccc; padding: 6px; text-align: center; }}
        th {{ background-color: #D9E2F3; }}
    </style>
    </head>
    <body>
    {html_content}
    </body>
    </html>
    """

    weasyprint.HTML(string=styled_html).write_pdf(output_path)
    return output_path


def _convert_with_docx2pdf(docx_path: str, output_path: str) -> str:
    """使用 docx2pdf 转换（依赖 LibreOffice 或 MS Word）"""
    try:
        from docx2pdf import convert
    except ImportError:
        raise RuntimeError("docx2pdf 未安装 (pip install docx2pdf)")

    logger.info(f"[PDF导出] 执行 docx2pdf 转换: {docx_path} → {output_path}")
    convert(docx_path, output_path)

    if not Path(output_path).exists():
        raise RuntimeError("docx2pdf 转换完成但未找到输出文件")

    return output_path


def export_to_pdf(
    docx_path: str,
    output_path: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    status_key: Optional[str] = None,
) -> str:
    """
    将 docx 转换为 PDF，返回 PDF 路径。

    转换策略（按优先级）:
      1. LibreOffice (headless) — 推荐，效果最好
      2. pandoc + xelatex — 需要 LaTeX 环境
      3. weasyprint — 需要 mammoth + weasyprint
      4. docx2pdf — 需要 LibreOffice 或 MS Word

    Args:
        docx_path: 输入的 .docx 文件路径
        output_path: 输出的 .pdf 文件路径（可选，默认与 docx 同目录）
        timeout: 转换超时（秒），默认 120
        status_key: 转换状态查询 key（可选）

    Returns:
        PDF 文件路径

    Raises:
        FileNotFoundError: docx 文件不存在
        TimeoutError: 转换超时
        RuntimeError: 所有转换方法均失败
    """
    if not Path(docx_path).exists():
        raise FileNotFoundError(f"docx 文件不存在: {docx_path}")

    if output_path is None:
        output_path = str(Path(docx_path).with_suffix('.pdf'))

    output_path = str(Path(output_path))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if status_key:
        _update_conversion_status(status_key, "queued", 0.0, "等待转换...")

    logger.info(f"[PDF导出] 开始转换: {docx_path} → {output_path}")

    # 策略 1: LibreOffice
    if _check_libreoffice():
        try:
            logger.info("[PDF导出] 使用策略 1: LibreOffice")
            return _convert_with_libreoffice(docx_path, output_path, timeout, status_key)
        except (TimeoutError, RuntimeError) as e:
            logger.warning(f"[PDF导出] LibreOffice 转换失败: {e}")
        except Exception as e:
            logger.warning(f"[PDF导出] LibreOffice 异常: {e}")

    # 策略 2: pandoc
    if _check_pandoc():
        try:
            logger.info("[PDF导出] 使用策略 2: pandoc")
            return _convert_with_pandoc(docx_path, output_path, timeout, status_key)
        except (TimeoutError, RuntimeError) as e:
            logger.warning(f"[PDF导出] pandoc 转换失败: {e}")
        except Exception as e:
            logger.warning(f"[PDF导出] pandoc 异常: {e}")

    # 策略 3: weasyprint
    try:
        import weasyprint
        import mammoth
        logger.info("[PDF导出] 使用策略 3: weasyprint")
        return _convert_with_weasyprint(docx_path, output_path)
    except ImportError:
        logger.warning("[PDF导出] weasyprint/mammoth 不可用，跳过策略 3")
    except Exception as e:
        logger.warning(f"[PDF导出] weasyprint 转换失败: {e}")

    # 策略 4: docx2pdf
    try:
        import docx2pdf
        logger.info("[PDF导出] 使用策略 4: docx2pdf")
        return _convert_with_docx2pdf(docx_path, output_path)
    except ImportError:
        logger.warning("[PDF导出] docx2pdf 不可用，跳过策略 4")
    except Exception as e:
        logger.warning(f"[PDF导出] docx2pdf 转换失败: {e}")

    if status_key:
        _update_conversion_status(status_key, "error", 0.0, "所有转换方法均失败")

    raise RuntimeError(
        "PDF 导出失败：所有转换方法均不可用。"
        "请安装以下任意一种：LibreOffice (推荐)、pandoc、weasyprint+mammoth、docx2pdf"
    )


def export_project_pdf(
    project_id: int,
    docx_path: str,
    output_path: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    为指定项目导出 PDF。

    Args:
        project_id: 项目 ID
        docx_path: 输入的 docx 路径
        output_path: 输出路径（可选）
        timeout: 转换超时（秒）

    Returns:
        {
            "status": "success",
            "pdf_path": "/path/to/output.pdf",
            "file_size_bytes": 12345,
            "project_id": 1,
            "generated_at": "...",
            "converter": "LibreOffice",
            "timeout_seconds": 120,
        }
    """
    if output_path is None:
        output_dir = PDF_OUTPUT_DIR / str(project_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"完整标书_{project_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        output_path = str(output_dir / filename)

    status_key = f"pdf_export_{project_id}"
    pdf_path = export_to_pdf(docx_path, output_path, timeout, status_key)

    result = {
        "status": "success",
        "pdf_path": pdf_path,
        "file_size_bytes": Path(pdf_path).stat().st_size,
        "project_id": project_id,
        "generated_at": datetime.now().isoformat(),
        "timeout_seconds": timeout,
    }

    _cleanup_conversion_status(status_key)
    return result


def get_conversion_status(key: str) -> Optional[dict]:
    """查询转换进度"""
    return _get_conversion_status(key)


def get_available_converters() -> list:
    """列出当前可用的 PDF 转换工具"""
    converters = []

    if _check_libreoffice():
        converters.append({"name": "LibreOffice", "priority": 1, "status": "available"})
    else:
        converters.append({"name": "LibreOffice", "priority": 1, "status": "not installed"})

    if _check_pandoc():
        converters.append({"name": "pandoc", "priority": 2, "status": "available"})
    else:
        converters.append({"name": "pandoc", "priority": 2, "status": "not installed"})

    try:
        import weasyprint
        import mammoth
        converters.append({"name": "weasyprint+mammoth", "priority": 3, "status": "available"})
    except ImportError:
        converters.append({"name": "weasyprint+mammoth", "priority": 3, "status": "not installed"})

    try:
        import docx2pdf
        converters.append({"name": "docx2pdf", "priority": 4, "status": "available"})
    except ImportError:
        converters.append({"name": "docx2pdf", "priority": 4, "status": "not installed"})

    return converters
