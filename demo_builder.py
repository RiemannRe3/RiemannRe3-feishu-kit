# -*- coding: utf-8 -*-
"""
飞书多维表格构建器 Demo
演示：在指定文件夹下创建多维表格、配置字段、写入实验记录。

目标文件夹: https://n3kyhtp7sz.feishu.cn/drive/folder/Defhfgi6ulrigHdvFuYc86lbnE5
运行前准备：
  1. 确保 .env 中配置了 FEISHU_APP_ID 和 FEISHU_APP_SECRET
  2. 在飞书中把目标文件夹共享给你的自建应用（可管理权限）
  3. 自建应用需开启权限：bitable:app（查看、编辑和管理多维表格）
"""

import os
from feishu_bitable_builder import (
    FeishuBitableBuilder,
    FIELD_TYPE_TEXT,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_SELECT,
    FIELD_TYPE_CHECKBOX,
    FIELD_TYPE_DATE,
)

try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(_env_path)
except ImportError:
    pass


# ────────────────────────────────────────────
# 配置区：从环境变量或直接在此处填写
# ────────────────────────────────────────────

APP_ID     = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")

# 目标文件夹 token（从 URL 末段提取）
# URL: https://n3kyhtp7sz.feishu.cn/drive/folder/Defhfgi6ulrigHdvFuYc86lbnE5
FOLDER_TOKEN = os.environ.get("FEISHU_FOLDER_TOKEN", "Defhfgi6ulrigHdvFuYc86lbnE5")


def demo_quick_build():
    """
    Demo A：一键完成——创建表格 + 配置字段 + 写入数据（推荐入口）。
    """
    builder = FeishuBitableBuilder(app_id=APP_ID, app_secret=APP_SECRET)

    # 字段配置：第一项为主字段（改名），后续为新增字段
    fields_config = [
        {
            "field_name": "实验名称",
            "type": FIELD_TYPE_TEXT,
        },
        {
            "field_name": "Accuracy",
            "type": FIELD_TYPE_NUMBER,
            "property": {"formatter": "0.0000"},  # 显示 4 位小数
        },
        {
            "field_name": "Loss",
            "type": FIELD_TYPE_NUMBER,
            "property": {"formatter": "0.0000"},
        },
        {
            "field_name": "Epochs",
            "type": FIELD_TYPE_NUMBER,
            "property": {"formatter": "0"},
        },
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
        {
            "field_name": "备注",
            "type": FIELD_TYPE_TEXT,
        },
    ]

    # 模拟实验数据
    records = [
        {"实验名称": "exp_baseline",  "Accuracy": 0.9210, "Loss": 0.312400, "Epochs": 10, "状态": "已完成", "备注": "基线模型"},
        {"实验名称": "exp_lr_0.01",   "Accuracy": 0.9380, "Loss": 0.274100, "Epochs": 20, "状态": "已完成", "备注": "调小学习率"},
        {"实验名称": "exp_dropout",   "Accuracy": 0.9451, "Loss": 0.251300, "Epochs": 20, "状态": "已完成", "备注": "加 dropout=0.3"},
        {"实验名称": "exp_aug",       "Accuracy": 0.9523, "Loss": 0.228700, "Epochs": 30, "状态": "已完成", "备注": "数据增强"},
        {"实验名称": "exp_lr_warmup", "Accuracy": 0.9601, "Loss": 0.198500, "Epochs": 30, "状态": "进行中", "备注": "lr warmup + cosine"},
        {"实验名称": "exp_large",     "Accuracy": 0.0000, "Loss": 0.000000, "Epochs":  0, "状态": "失败",   "备注": "OOM，待优化"},
    ]

    result = builder.build(
        bitable_name="实验结果追踪",
        table_name="训练记录",
        fields_config=fields_config,
        records=records,
        folder_token=FOLDER_TOKEN,
    )

    return result


def demo_step_by_step():
    """
    Demo B：分步演示——逐步调用每个接口（适合理解每步细节）。
    """
    builder = FeishuBitableBuilder(app_id=APP_ID, app_secret=APP_SECRET)

    print("\n【步骤 1】在指定文件夹下创建多维表格")
    app_token = builder.create_bitable(
        name="分步示例_多维表格",
        folder_token=FOLDER_TOKEN,
    )

    import time
    time.sleep(0.5)

    print("\n【步骤 2】在多维表格内新建数据表")
    table_id = builder.create_table(app_token, table_name="指标汇总")

    time.sleep(0.5)

    print("\n【步骤 3】查看默认字段（了解主字段 field_id）")
    fields = builder.get_fields(app_token, table_id)
    print(f"  默认字段列表（共 {len(fields)} 个）:")
    for f in fields:
        print(f"    [{f['field_id']}] {f['field_name']!r}  type={f.get('type')}")

    time.sleep(0.2)

    print("\n【步骤 4】配置字段（改主字段名 + 新增字段）")
    builder.setup_fields(app_token, table_id, [
        {"field_name": "模型名",  "type": FIELD_TYPE_TEXT},
        {"field_name": "Top1_Acc", "type": FIELD_TYPE_NUMBER, "property": {"formatter": "0.00%"}},
        {"field_name": "参数量(M)", "type": FIELD_TYPE_NUMBER, "property": {"formatter": "0.0"}},
        {"field_name": "已部署",   "type": FIELD_TYPE_CHECKBOX},
    ])

    time.sleep(0.3)

    print("\n【步骤 5】写入记录")
    builder.add_records(app_token, table_id, [
        {"模型名": "ResNet-50",    "Top1_Acc": 0.7613, "参数量(M)": 25.6,  "已部署": True},
        {"模型名": "EfficientB0",  "Top1_Acc": 0.7732, "参数量(M)": 5.3,   "已部署": True},
        {"模型名": "ViT-B/16",     "Top1_Acc": 0.8145, "参数量(M)": 86.6,  "已部署": False},
        {"模型名": "ConvNeXt-T",   "Top1_Acc": 0.8228, "参数量(M)": 28.6,  "已部署": False},
    ])

    print(f"\n分步 Demo 完成！app_token={app_token}  table_id={table_id}")
    return {"app_token": app_token, "table_id": table_id}


# ────────────────────────────────────────────
# 入口
# ────────────────────────────────────────────

if __name__ == "__main__":
    if not APP_ID or not APP_SECRET:
        print("错误：请先在 .env 中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        exit(1)

    print("请选择要运行的 Demo：")
    print("  A - 一键构建（推荐）")
    print("  B - 分步演示")
    choice = input("输入 A 或 B（直接回车默认 A）: ").strip().upper() or "A"

    if choice == "A":
        demo_quick_build()
    elif choice == "B":
        demo_step_by_step()
    else:
        print(f"未知选项 '{choice}'，运行默认 Demo A")
        demo_quick_build()
