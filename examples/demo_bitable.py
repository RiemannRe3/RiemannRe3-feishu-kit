# -*- coding: utf-8 -*-
"""
飞书多维表格构建器 Demo
演示：在指定文件夹下创建多维表格、配置字段、写入实验记录。

运行前准备：
  1. 确保项目根目录 .env 中配置了 FEISHU_APP_ID 和 FEISHU_APP_SECRET
  2. 在飞书中把目标文件夹共享给自建应用（可管理权限）
  3. 自建应用需开启权限：bitable:app

运行方式：
  python examples/demo_bitable.py
"""

import os
from feishu_kit.config import load_config
from feishu_kit.bitable_builder import (
    FeishuBitableBuilder,
    FIELD_TYPE_TEXT,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_SELECT,
    FIELD_TYPE_CHECKBOX,
)

# 加载 .env
load_config()

APP_ID       = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET   = os.environ.get("FEISHU_APP_SECRET", "")
FOLDER_TOKEN = os.environ.get("FEISHU_FOLDER_TOKEN", "")


def demo_quick_build():
    """Demo A：一键完成——创建表格 + 配置字段 + 写入数据（推荐入口）。"""
    builder = FeishuBitableBuilder(app_id=APP_ID, app_secret=APP_SECRET)

    fields_config = [
        {"field_name": "实验名称", "type": FIELD_TYPE_TEXT},
        {"field_name": "Accuracy", "type": FIELD_TYPE_NUMBER, "property": {"formatter": "0.0000"}},
        {"field_name": "Loss",     "type": FIELD_TYPE_NUMBER, "property": {"formatter": "0.0000"}},
        {"field_name": "Epochs",   "type": FIELD_TYPE_NUMBER, "property": {"formatter": "0"}},
        {
            "field_name": "状态",
            "type": FIELD_TYPE_SELECT,
            "property": {
                "options": [
                    {"name": "进行中", "color": 0},
                    {"name": "已完成", "color": 1},
                    {"name": "失败",   "color": 2},
                ]
            },
        },
        {"field_name": "备注", "type": FIELD_TYPE_TEXT},
    ]

    records = [
        {"实验名称": "exp_baseline",  "Accuracy": 0.9210, "Loss": 0.3124, "Epochs": 10, "状态": "已完成", "备注": "基线模型"},
        {"实验名称": "exp_lr_0.01",   "Accuracy": 0.9380, "Loss": 0.2741, "Epochs": 20, "状态": "已完成", "备注": "调小学习率"},
        {"实验名称": "exp_dropout",   "Accuracy": 0.9451, "Loss": 0.2513, "Epochs": 20, "状态": "已完成", "备注": "加 dropout=0.3"},
        {"实验名称": "exp_aug",       "Accuracy": 0.9523, "Loss": 0.2287, "Epochs": 30, "状态": "已完成", "备注": "数据增强"},
        {"实验名称": "exp_lr_warmup", "Accuracy": 0.9601, "Loss": 0.1985, "Epochs": 30, "状态": "进行中", "备注": "lr warmup + cosine"},
        {"实验名称": "exp_large",     "Accuracy": 0.0000, "Loss": 0.0000, "Epochs":  0, "状态": "失败",   "备注": "OOM，待优化"},
    ]

    return builder.build(
        bitable_name="实验结果追踪",
        table_name="训练记录",
        fields_config=fields_config,
        records=records,
        folder_token=FOLDER_TOKEN,
    )


def demo_step_by_step():
    """Demo B：分步演示——逐步调用每个接口（适合理解每步细节）。"""
    import time
    builder = FeishuBitableBuilder(app_id=APP_ID, app_secret=APP_SECRET)

    print("\n【步骤 1】在指定文件夹下创建多维表格")
    app_token = builder.create_bitable(name="分步示例_多维表格", folder_token=FOLDER_TOKEN)
    time.sleep(0.5)

    print("\n【步骤 2】在多维表格内新建数据表")
    table_id = builder.create_table(app_token, table_name="指标汇总")
    time.sleep(0.5)

    print("\n【步骤 3】配置字段")
    builder.setup_fields(app_token, table_id, [
        {"field_name": "模型名",     "type": FIELD_TYPE_TEXT},
        {"field_name": "Top1_Acc",   "type": FIELD_TYPE_NUMBER, "property": {"formatter": "0.00%"}},
        {"field_name": "参数量(M)",  "type": FIELD_TYPE_NUMBER, "property": {"formatter": "0.0"}},
        {"field_name": "已部署",     "type": FIELD_TYPE_CHECKBOX},
    ])

    time.sleep(0.3)
    print("\n【步骤 4】写入记录")
    builder.add_records(app_token, table_id, [
        {"模型名": "ResNet-50",   "Top1_Acc": 0.7613, "参数量(M)": 25.6, "已部署": True},
        {"模型名": "EfficientB0", "Top1_Acc": 0.7732, "参数量(M)":  5.3, "已部署": True},
        {"模型名": "ViT-B/16",    "Top1_Acc": 0.8145, "参数量(M)": 86.6, "已部署": False},
    ])

    print(f"\n分步 Demo 完成！app_token={app_token}  table_id={table_id}")
    return {"app_token": app_token, "table_id": table_id}


if __name__ == "__main__":
    if not APP_ID or not APP_SECRET:
        print("错误：请先在 .env 中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        exit(1)

    choice = input("选择 Demo（A=一键构建, B=分步演示, 回车默认 A）: ").strip().upper() or "A"
    if choice == "A":
        demo_quick_build()
    else:
        demo_step_by_step()
