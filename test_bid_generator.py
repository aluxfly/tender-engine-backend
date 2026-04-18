"""
测试用例：物联网卡 & 布控球标书生成
测试时间：2026-04-18
测试人员：qa-tester
"""

import json
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import generate_bid_document
from pydantic import BaseModel

class TestRequest(BaseModel):
    project_id: int
    company_name: str
    contact_person: str
    contact_phone: str
    bid_amount: float
    project_type: str = "物联网卡"
    custom_fields: dict = None

# 测试数据
test_cases = [
    {
        "name": "物联网卡标书测试1 - 基础信息",
        "request": {
            "project_id": 1,
            "company_name": "测试科技有限公司",
            "contact_person": "张三",
            "contact_phone": "13800138001",
            "bid_amount": 500000,
            "project_type": "物联网卡",
            "custom_fields": {
                "card_type": "SIM卡",
                "frequency_band": "FDD-LTE",
                "data_plan": "月流量1GB",
                "operator": "中国移动",
                "apn": "cmiot"
            }
        }
    },
    {
        "name": "物联网卡标书测试2 - 全频段支持",
        "request": {
            "project_id": 2,
            "company_name": "联通物联网公司",
            "contact_person": "李四",
            "contact_phone": "13800138002",
            "bid_amount": 800000,
            "project_type": "物联网卡",
            "custom_fields": {
                "card_type": "eSIM",
                "frequency_band": "全频段",
                "data_plan": "月流量5GB",
                "operator": "中国联通",
                "apn": "uniot"
            }
        }
    },
    {
        "name": "物联网卡标书测试3 - NB-IoT 特殊需求",
        "request": {
            "project_id": 3,
            "company_name": "智能传感科技",
            "contact_person": "王五",
            "contact_phone": "13800138003",
            "bid_amount": 300000,
            "project_type": "物联网卡",
            "custom_fields": {
                "card_type": "M2M卡",
                "frequency_band": "NB-IoT",
                "data_plan": "月流量100MB",
                "operator": "中国电信",
                "apn": "ctiot"
            }
        }
    },
    {
        "name": "布控球标书测试1 - 1080P 基础版",
        "request": {
            "project_id": 4,
            "company_name": "安防科技有限公司",
            "contact_person": "赵六",
            "contact_phone": "13800138004",
            "bid_amount": 1200000,
            "project_type": "布控球",
            "custom_fields": {
                "video_resolution": "1080P",
                "frame_rate": "25fps",
                "bit_rate": "2Mbps",
                "storage": "本地存储",
                "power": "太阳能",
                "installation": "立杆安装",
                "wireless": "4G",
                "protocol": "ONVIF"
            }
        }
    },
    {
        "name": "布控球标书测试2 - 4K 高清版",
        "request": {
            "project_id": 5,
            "company_name": "高清监控科技",
            "contact_person": "钱七",
            "contact_phone": "13800138005",
            "bid_amount": 2500000,
            "project_type": "布控球",
            "custom_fields": {
                "video_resolution": "4K",
                "frame_rate": "30fps",
                "bit_rate": "8Mbps",
                "storage": "云存储",
                "power": "市电",
                "installation": "墙面安装",
                "wireless": "5G",
                "protocol": "GB/T28181"
            }
        }
    },
    {
        "name": "布控球标书测试3 - 智能分析版",
        "request": {
            "project_id": 6,
            "company_name": "智能安防科技",
            "contact_person": "孙八",
            "contact_phone": "13800138006",
            "bid_amount": 3800000,
            "project_type": "布控球",
            "custom_fields": {
                "video_resolution": "8K",
                "frame_rate": "60fps",
                "bit_rate": "10Mbps",
                "storage": "本地+云存储",
                "power": "太阳能+电池",
                "installation": "车载安装",
                "wireless": "5G",
                "protocol": "多协议支持",
                "smart_analysis": "人脸识别、车牌识别、行为分析",
                "ai_algorithm": "深度学习算法"
            }
        }
    }
]

def run_tests():
    """运行测试用例"""
    results = {
        "total": len(test_cases),
        "passed": 0,
        "failed": 0,
        "details": []
    }
    
    print("=" * 80)
    print("标书 AI 生成测试报告")
    print("测试时间：2026-04-18")
    print("测试人员：qa-tester")
    print("=" * 80)
    print()
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"【测试 {i}/{len(test_cases)}】{test_case['name']}")
        print("-" * 60)
        
        try:
            request = TestRequest(**test_case['request'])
            
            # 模拟 API 调用
            result = generate_bid_document(request)
            
            # 检查响应
            if result.status_code == 200:
                results["passed"] += 1
                print(f"✅ 通过 - 状态码: {result.status_code}")
                print(f"   响应类型: {result.media_type}")
                print(f"   文件名: {test_case['request']['project_type']}_bid_{request.project_id}_{request.company_name}.docx")
            else:
                results["failed"] += 1
                print(f"❌ 失败 - 状态码: {result.status_code}")
                print(f"   错误信息: {result.detail}")
            
        except Exception as e:
            results["failed"] += 1
            print(f"❌ 异常 - {str(e)}")
        
        print()
    
    # 汇总报告
    print("=" * 80)
    print("测试汇总")
    print("=" * 80)
    print(f"总测试数: {results['total']}")
    print(f"通过: {results['passed']} ({results['passed']/results['total']*100:.1f}%)")
    print(f"失败: {results['failed']} ({results['failed']/results['total']*100:.1f}%)")
    print()
    
    if results['failed'] == 0:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查")
        return 1

if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
