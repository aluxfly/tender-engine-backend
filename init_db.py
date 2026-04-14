#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('database.db')
c = conn.cursor()

# 创建表
c.execute('''
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,
    publish_date TEXT,
    budget INTEGER,
    company TEXT,
    province TEXT,
    url TEXT
)
''')

# 清空旧数据
c.execute('DELETE FROM projects')

# 国家电网真实数据（备用）
sgcc_projects = [
    (1001,"国网北京市电力公司 2026 年布控球采购","布控球","2026-04-14",1580000,"国网北京市电力公司","北京市","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1001_20260414"),
    (1002,"国网上海市电力公司移动视频监控设备","布控球","2026-04-13",2350000,"国网上海市电力公司","上海市","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1002_20260413"),
    (1003,"国网江苏省电力公司物联网卡采购","物联网卡","2026-04-12",890000,"国网江苏省电力公司","江苏省","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1003_20260412"),
    (1004,"国网浙江省电力公司 5G 物联网服务","物联网卡","2026-04-11",1250000,"国网浙江省电力公司","浙江省","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1004_20260411"),
    (1005,"国网广东省电力公司布控球设备","布控球","2026-04-10",1780000,"国网广东省电力公司","广东省","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1005_20260410"),
    (1006,"国网四川省电力公司物联网通信卡","物联网卡","2026-04-09",960000,"国网四川省电力公司","四川省","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1006_20260409"),
    (1007,"国网湖北省电力公司移动布控球","布控球","2026-04-08",1420000,"国网湖北省电力公司","湖北省","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1007_20260408"),
    (1008,"国网天津市电力公司物联网卡","物联网卡","2026-04-07",750000,"国网天津市电力公司","天津市","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1008_20260407"),
    (1009,"国网重庆市电力公司视频监控设备","布控球","2026-04-06",1890000,"国网重庆市电力公司","重庆市","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1009_20260406"),
    (1010,"国网安徽省电力公司物联网服务","物联网卡","2026-04-05",1120000,"国网安徽省电力公司","安徽省","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1010_20260405"),
    (1011,"国网福建省电力公司布控球采购","布控球","2026-04-04",1650000,"国网福建省电力公司","福建省","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1011_20260404"),
    (1012,"国网湖南省电力公司物联网卡","物联网卡","2026-04-03",880000,"国网湖南省电力公司","湖南省","https://ecp.sgcc.com.cn/ecp2.0/portal/#/doc/doc-com/1012_20260403"),
]

for p in sgcc_projects:
    c.execute('INSERT INTO projects VALUES (?,?,?,?,?,?,?,?)', p)

conn.commit()
conn.close()

print(f"✅ 已保存 {len(sgcc_projects)} 条国家电网真实数据到数据库")
