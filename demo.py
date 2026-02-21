# -*- coding: utf-8 -*-
"""
飞书多维表格上传 Demo
运行前请设置环境变量或修改下方配置，并在多维表格中为自建应用开通「可管理」权限。
多维表格 URL 格式：https://xxx.feishu.cn/base/{app_token}?table={table_id}
"""

import os
from feishu_bitable_uploader import FeishuBitableUploader

# 从 demo.py 所在目录加载 .env，这样无论从哪执行都能读到配置
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(_env_path)
except ImportError:
    pass


def main():
    # 方式一：从环境变量或 .env 读取（推荐）
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    app_token = os.environ.get("FEISHU_APP_TOKEN", "")
    table_id = os.environ.get("FEISHU_TABLE_ID", "")

    # 方式二：直接写在这里（仅用于本地 demo）
    if not app_id:
        app_id = "your_app_id"
    if not app_secret:
        app_secret = "your_app_secret"
    if not app_token:
        app_token = "bascnxxxxxxxxxxxxxxxx"  # 从多维表格 URL 的 /base/ 后、?table= 前复制
    if not table_id:
        table_id = "tblxxxxxxxxxxxxxxxx"  # 从 URL 的 table= 后面复制

    if app_id == "your_app_id" or app_token.startswith("bascn") or not app_token:
        print("请先配置飞书凭证与多维表格信息：")
        print("  1. 设置环境变量 FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_APP_TOKEN, FEISHU_TABLE_ID")
        print("  2. 多维表格 URL 示例: https://xxx.feishu.cn/base/{app_token}?table={table_id}")
        print("  3. 在目标多维表格中为自建应用开通「可管理」权限")
        return

    uploader = FeishuBitableUploader(
        app_id=app_id,
        app_secret=app_secret,
        app_token=app_token,
        table_id=table_id,
    )

    # 先查询表格里真实的字段名，对照后再填 demo_records
    print("正在查询表格字段...")
    try:
        uploader.print_fields()
    except Exception as e:
        print("查询字段失败:", e)
        return

    # 文本类型（type=1）字段的值必须是字符串，数字需用 str() 转换
    demo_records = [
        {"实验名称": "exp_001", "指标A": "0.95", "指标B": "0.88", "备注": "baseline"},
        {"实验名称": "exp_002", "指标A": "0.96", "指标B": "0.90", "备注": "tuned"},
    ]
    print("\n正在向飞书多维表格添加记录...")
    try:
        result = uploader.add_records(demo_records)
        print("添加成功:", result)
    except Exception as e:
        print("添加失败:", e)
        return

    print("\n在实验脚本中集成示例：")
    print("  from feishu_bitable_uploader import FeishuBitableUploader")
    print("  u = FeishuBitableUploader()  # 使用环境变量")
    print("  u.add_records([{'实验名称': 'exp_003', '指标A': 0.97, '指标B': 0.91, '备注': 'final'}])")


if __name__ == "__main__":
    main()
