# -*- coding: utf-8 -*-
"""
feishu_kit — 飞书工具包

提供对飞书 Drive、Wiki（知识库）、Bitable（多维表格）、Sheets（电子表格）
的 Python API 封装，支持命令行和脚本两种使用方式。

快速开始::

    from feishu_kit import FeishuClient

    client = FeishuClient()                    # 自动加载项目根目录的 .env

    # 通过书签跳转到 Wiki 节点
    node = client.goto("@bot")

    # 路径解析：@书签/子节点名
    table = client.resolve("@bot/实验记录")

    # 直接操作多维表格
    bitable = client.bitable("BrVPb...")
    records = bitable.query(table_name="results")
    bitable.append_rows([{"实验": "exp_001", "Acc": 0.95}])
"""

from feishu_kit.client import FeishuClient
from feishu_kit.config import load_config
from feishu_kit.nodes import BitableNode, SheetNode, WikiNode

# 底层 API 类（供进阶使用）
from feishu_kit.drive_api import FeishuDriveAPI
from feishu_kit.wiki_api import FeishuWikiAPI
from feishu_kit.bitable_builder import FeishuBitableBuilder
from feishu_kit.sheet_builder import FeishuSheetBuilder

__version__ = "0.1.0"
__author__ = "feishu-kit"

__all__ = [
    # 主入口
    "FeishuClient",
    # 节点对象
    "WikiNode",
    "BitableNode",
    "SheetNode",
    # 底层 API
    "FeishuDriveAPI",
    "FeishuWikiAPI",
    "FeishuBitableBuilder",
    "FeishuSheetBuilder",
    # 配置工具
    "load_config",
]
