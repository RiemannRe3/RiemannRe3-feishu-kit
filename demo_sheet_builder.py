# -*- coding: utf-8 -*-
"""
飞书电子表格构建器 Demo
演示：在指定文件夹下创建电子表格、配置工作表名、写入实验数据。

目标文件夹: https://n3kyhtp7sz.feishu.cn/drive/folder/Defhfgi6ulrigHdvFuYc86lbnE5
运行前准备：
  1. 确保 .env 中配置了 FEISHU_APP_ID 和 FEISHU_APP_SECRET
  2. 在飞书中把目标文件夹共享给你的自建应用（可编辑权限）
  3. 自建应用需开启权限：sheets:spreadsheet（查看、编辑和管理电子表格）
                         drive:drive 或 drive:file（云盘文件访问）
"""

import os
from feishu_sheet_builder import FeishuSheetBuilder

try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(_env_path)
except ImportError:
    pass


# ────────────────────────────────────────────
# 配置
# ────────────────────────────────────────────

APP_ID       = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET   = os.environ.get("FEISHU_APP_SECRET", "")
FOLDER_TOKEN = os.environ.get("FEISHU_FOLDER_TOKEN", "Defhfgi6ulrigHdvFuYc86lbnE5")


def demo_quick_build():
    """
    Demo A：一键完成——创建表格 + 重命名工作表 + 写入数据（推荐入口）。
    """
    builder = FeishuSheetBuilder(app_id=APP_ID, app_secret=APP_SECRET)

    headers = ["实验名称", "Accuracy", "Loss", "Epochs", "学习率", "状态", "备注"]

    rows = [
        ["exp_baseline",  0.9210, 0.3124, 10, 0.001,  "已完成", "基线模型，无任何优化"],
        ["exp_lr_0.01",   0.9380, 0.2741, 20, 0.01,   "已完成", "调大学习率"],
        ["exp_dropout",   0.9451, 0.2513, 20, 0.001,  "已完成", "加 dropout=0.3"],
        ["exp_aug",       0.9523, 0.2287, 30, 0.001,  "已完成", "数据增强"],
        ["exp_lr_warmup", 0.9601, 0.1985, 30, 0.0005, "进行中", "lr warmup + cosine"],
        ["exp_large",     "",     "",      0, 0.001,  "失败",   "OOM，待优化"],
    ]

    result = builder.build(
        title="实验结果_电子表格",
        sheet_title="训练记录",
        headers=headers,
        rows=rows,
        folder_token=FOLDER_TOKEN,
    )

    return result


def demo_step_by_step():
    """
    Demo B：分步演示——逐步调用每个接口，理解流程。
    """
    import time
    builder = FeishuSheetBuilder(app_id=APP_ID, app_secret=APP_SECRET)

    print("\n【步骤 1】在指定文件夹下创建电子表格")
    spreadsheet_token = builder.create_spreadsheet(
        title="分步示例_电子表格",
        folder_token=FOLDER_TOKEN,
    )

    time.sleep(0.5)

    print("\n【步骤 2】列出工作表（获取默认工作表的 sheet_id）")
    sheets = builder.get_sheets(spreadsheet_token)
    print(f"  共 {len(sheets)} 个工作表：")
    for s in sheets:
        print(f"    [{s['sheetId']}] {s.get('title')!r}  index={s.get('index')}")

    sheet_id = sheets[0]["sheetId"]
    time.sleep(0.3)

    print("\n【步骤 3】重命名默认工作表")
    builder.rename_sheet(spreadsheet_token, sheet_id, "模型对比")

    time.sleep(0.3)

    print("\n【步骤 4】写入表头 + 数据")
    headers = ["模型名", "Top1_Acc", "参数量(M)", "推理速度(ms)", "是否部署"]
    data_rows = [
        ["ResNet-50",   0.7613, 25.6,  12.3, "是"],
        ["EfficientB0", 0.7732,  5.3,   8.1, "是"],
        ["ViT-B/16",    0.8145, 86.6,  45.2, "否"],
        ["ConvNeXt-T",  0.8228, 28.6,  15.6, "否"],
    ]
    builder.write_data(spreadsheet_token, sheet_id, [headers] + data_rows)

    time.sleep(0.3)

    print("\n【步骤 5】追加更多行")
    extra_rows = [
        ["Swin-T", 0.8135, 28.3, 18.4, "否"],
    ]
    builder.append_rows(spreadsheet_token, sheet_id, extra_rows)

    print(f"\n分步 Demo 完成！spreadsheet_token={spreadsheet_token}  sheet_id={sheet_id}")
    return {"spreadsheet_token": spreadsheet_token, "sheet_id": sheet_id}


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
