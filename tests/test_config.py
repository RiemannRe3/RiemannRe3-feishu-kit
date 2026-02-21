# -*- coding: utf-8 -*-
"""
测试：feishu_kit.config 配置加载
验证：.env 文件正确加载，关键凭证不为空。
"""

import os
import pytest
from feishu_kit.config import load_config, get_env_path


def test_env_file_exists():
    """项目根目录应存在 .env 文件。"""
    env_path = get_env_path()
    assert env_path.exists(), (
        f".env 文件不存在: {env_path}\n"
        "请复制 .env.example 为 .env 并填写真实凭证。"
    )


def test_load_config_returns_dict():
    """load_config() 应返回包含全部预期键的字典。"""
    cfg = load_config()
    required_keys = ["app_id", "app_secret", "domain", "folder_token", "default_mode"]
    for key in required_keys:
        assert key in cfg, f"配置缺少键: {key}"


def test_app_id_not_empty():
    """FEISHU_APP_ID 必须已配置（非空、非占位符）。"""
    cfg = load_config()
    assert cfg["app_id"], "FEISHU_APP_ID 未配置"
    assert cfg["app_id"] != "your_app_id", (
        "FEISHU_APP_ID 仍为占位符 'your_app_id'，请填写真实 App ID"
    )


def test_app_secret_not_empty():
    """FEISHU_APP_SECRET 必须已配置。"""
    cfg = load_config()
    assert cfg["app_secret"], "FEISHU_APP_SECRET 未配置"
    assert cfg["app_secret"] != "your_app_secret", (
        "FEISHU_APP_SECRET 仍为占位符，请填写真实 App Secret"
    )


def test_default_mode_valid():
    """FEISHU_DEFAULT_MODE 应为 wiki / drive / auto 之一。"""
    cfg = load_config()
    valid_modes = ("wiki", "drive", "auto")
    assert cfg["default_mode"] in valid_modes, (
        f"FEISHU_DEFAULT_MODE={cfg['default_mode']!r} 不在合法值 {valid_modes} 中"
    )


def test_env_override():
    """override=True 应使 .env 值覆盖 Shell 环境变量。"""
    old_val = os.environ.get("FEISHU_APP_ID")
    os.environ["FEISHU_APP_ID"] = "FAKE_VALUE_FROM_SHELL"
    try:
        cfg = load_config()
        # 加载后，来自 .env 的真实值应覆盖 FAKE_VALUE_FROM_SHELL
        assert cfg["app_id"] != "FAKE_VALUE_FROM_SHELL", (
            "load_config 未正确使用 override=True，Shell 变量覆盖了 .env 值"
        )
    finally:
        if old_val is None:
            os.environ.pop("FEISHU_APP_ID", None)
        else:
            os.environ["FEISHU_APP_ID"] = old_val
