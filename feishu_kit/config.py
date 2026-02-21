# -*- coding: utf-8 -*-
"""
feishu_kit 配置加载模块

优先级：
  1. 先查找项目根目录的 .env 文件（override=True，覆盖 shell 环境变量中的旧值）
  2. 再读取系统环境变量（作为兜底）

调用方式::

    from feishu_kit.config import load_config, get_env_path

    cfg = load_config()
    print(cfg["app_id"], cfg["domain"])
"""

import os
from pathlib import Path
from typing import Dict, Any


def get_env_path() -> Path:
    """
    返回项目根目录下的 .env 文件路径（feishu_kit/ 的上两级目录）。
    若文件不存在则返回路径对象（不报错）。
    """
    # 本文件位于 feishu_kit/config.py，上一级即项目根
    pkg_dir = Path(__file__).parent
    return pkg_dir.parent / ".env"


def load_config(env_path: str = "") -> Dict[str, Any]:
    """
    加载飞书应用配置，自动读取 .env 文件。

    Args:
        env_path: 指定 .env 文件路径；留空则自动查找项目根目录的 .env。

    Returns:
        配置字典，包含以下键：
          - app_id:        FEISHU_APP_ID
          - app_secret:    FEISHU_APP_SECRET
          - domain:        FEISHU_DOMAIN（企业域前缀，如 "n3kyhtp7sz"）
          - folder_token:  FEISHU_FOLDER_TOKEN（云盘根文件夹 token）
          - default_mode:  FEISHU_DEFAULT_MODE（wiki / drive / auto）

    Raises:
        RuntimeError: 若 app_id 或 app_secret 为空，说明配置未正确设置
    """
    # 动态导入 dotenv，避免将其列为强制依赖（但实际已在 requirements.txt 中）
    try:
        from dotenv import load_dotenv
        target = env_path or str(get_env_path())
        if os.path.exists(target):
            load_dotenv(target, override=True)
    except ImportError:
        pass  # python-dotenv 未安装时直接使用环境变量

    cfg: Dict[str, Any] = {
        "app_id":       os.environ.get("FEISHU_APP_ID", ""),
        "app_secret":   os.environ.get("FEISHU_APP_SECRET", ""),
        "domain":       os.environ.get("FEISHU_DOMAIN", ""),
        "folder_token": os.environ.get("FEISHU_FOLDER_TOKEN", ""),
        "default_mode": os.environ.get("FEISHU_DEFAULT_MODE", "auto"),
    }
    return cfg
