# -*- coding: utf-8 -*-
"""
飞书电子表格构建器 Demo
演示：在指定文件夹下创建电子表格、配置工作表名、写入实验数据。

运行方式：
  python examples/demo_sheet.py
"""

import os
from feishu_kit.config import load_config
from feishu_kit.sheet_builder import FeishuSheetBuilder

load_config()

APP_ID       = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET   = os.environ.get("FEISHU_APP_SECRET", "")
FOLDER_TOKEN = os.environ.get("FEISHU_FOLDER_TOKEN", "")


def demo_quick_build():
    """Demo A：一键完成——创建表格 + 重命名工作表 + 写入数据（推荐入口）。"""
    builder = FeishuSheetBuilder(app_id=APP_ID, app_secret=APP_SECRET)

    headers = ["实验名称", "Accuracy", "Loss", "Epochs", "学习率", "状态", "备注"]
    rows = [
        ["exp_baseline",  0.9210, 0.3124, 10, 0.001,  "已完成", "基线模型"],
        ["exp_lr_0.01",   0.9380, 0.2741, 20, 0.01,   "已完成", "调大学习率"],
        ["exp_dropout",   0.9451, 0.2513, 20, 0.001,  "已完成", "加 dropout=0.3"],
        ["exp_aug",       0.9523, 0.2287, 30, 0.001,  "已完成", "数据增强"],
        ["exp_lr_warmup", 0.9601, 0.1985, 30, 0.0005, "进行中", "lr warmup + cosine"],
        ["exp_large",     "",     "",      0, 0.001,  "失败",   "OOM，待优化"],
    ]

    return builder.build(
        title="实验结果_电子表格",
        sheet_title="训练记录",
        headers=headers,
        rows=rows,
        folder_token=FOLDER_TOKEN,
    )


def demo_step_by_step():
    """Demo B：分步演示——逐步调用每个接口。"""
    import time
    builder = FeishuSheetBuilder(app_id=APP_ID, app_secret=APP_SECRET)

    print("\n【步骤 1】创建电子表格")
    ss_token = builder.create_spreadsheet(title="分步示例_电子表格", folder_token=FOLDER_TOKEN)
    time.sleep(0.5)

    print("\n【步骤 2】获取默认工作表 ID")
    sheets = builder.get_sheets(ss_token)
    sheet_id = sheets[0]["sheetId"]
    print(f"  sheet_id={sheet_id}")
    time.sleep(0.3)

    print("\n【步骤 3】重命名工作表")
    builder.rename_sheet(ss_token, sheet_id, "模型对比")
    time.sleep(0.3)

    print("\n【步骤 4】写入表头 + 数据")
    headers = ["模型名", "Top1_Acc", "参数量(M)", "推理速度(ms)", "是否部署"]
    data = [
        headers,
        ["ResNet-50",   0.7613, 25.6,  12.3, "是"],
        ["EfficientB0", 0.7732,  5.3,   8.1, "是"],
        ["ViT-B/16",    0.8145, 86.6,  45.2, "否"],
    ]
    builder.write_data(ss_token, sheet_id, data)
    time.sleep(0.3)

    print("\n【步骤 5】追加行")
    builder.append_rows(ss_token, sheet_id, [["Swin-T", 0.8135, 28.3, 18.4, "否"]])

    print(f"\n分步 Demo 完成！spreadsheet_token={ss_token}  sheet_id={sheet_id}")
    return {"spreadsheet_token": ss_token, "sheet_id": sheet_id}


if __name__ == "__main__":
    if not APP_ID or not APP_SECRET:
        print("错误：请先在 .env 中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        exit(1)

    choice = input("选择 Demo（A=一键构建, B=分步演示, 回车默认 A）: ").strip().upper() or "A"
    if choice == "A":
        demo_quick_build()
    else:
        demo_step_by_step()
