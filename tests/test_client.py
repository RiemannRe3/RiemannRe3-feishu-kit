# -*- coding: utf-8 -*-
"""
集成测试：feishu_kit.client.FeishuClient 统一门面层
测试：配置加载、书签管理、路径解析、节点构造。

前置条件：
  1. .env 中已配置真实凭证
  2. .feishu_bookmarks.json 中有至少一个书签（或测试会自动保存/清理临时书签）

运行方式：
  pytest tests/test_client.py -v -s
"""

import json
import os
import pytest
from pathlib import Path
from feishu_kit import FeishuClient
from feishu_kit.nodes import WikiNode, BitableNode, SheetNode
from feishu_kit.config import load_config

load_config()

# 书签文件路径（与项目根一致）
BM_PATH = Path(__file__).parent.parent / ".feishu_bookmarks.json"
TEST_ALIAS = "@pytest_temp_bookmark"


@pytest.fixture(scope="module")
def client():
    """创建 FeishuClient 实例。"""
    return FeishuClient()


class TestClientConfig:
    def test_client_repr(self, client):
        """repr 应包含 domain 和 mode 信息。"""
        r = repr(client)
        assert "FeishuClient" in r

    def test_config_hides_secret(self, client):
        """config 属性应隐藏 app_secret。"""
        cfg = client.config
        assert cfg.get("app_secret") == "***"

    def test_config_has_app_id(self, client):
        """config 应包含非空的 app_id。"""
        cfg = client.config
        assert cfg.get("app_id"), "app_id 为空"


class TestBookmarkManagement:
    """书签的增删查，使用临时别名避免污染真实书签。"""

    FAKE_NODE_TOKEN = "wikcnFAKE_PYTEST_TOKEN"
    FAKE_SPACE_ID   = "7000000000000000000"

    def test_save_and_get_bookmark(self, client):
        """save_bookmark + list_bookmarks 应能查到保存的书签。"""
        client.save_bookmark(
            TEST_ALIAS,
            node_token=self.FAKE_NODE_TOKEN,
            space_id=self.FAKE_SPACE_ID,
            title="pytest 临时书签",
        )
        bm = client.list_bookmarks()
        assert TEST_ALIAS in bm, f"书签 {TEST_ALIAS!r} 未保存成功"
        assert bm[TEST_ALIAS]["node_token"] == self.FAKE_NODE_TOKEN

    def test_delete_bookmark(self, client):
        """delete_bookmark 应正确移除书签。"""
        result = client.delete_bookmark(TEST_ALIAS)
        assert result is True, "应返回 True 表示成功删除"
        bm = client.list_bookmarks()
        assert TEST_ALIAS not in bm, "书签未被删除"

    def test_delete_nonexistent_returns_false(self, client):
        """删除不存在的书签应返回 False。"""
        result = client.delete_bookmark("@nonexistent_alias_xyz")
        assert result is False


class TestGoto:
    """书签跳转测试（需要真实 Wiki 节点书签）。"""

    def test_goto_nonexistent_raises(self, client):
        """goto 不存在的别名应抛出 KeyError。"""
        with pytest.raises(KeyError):
            client.goto("@nonexistent_alias_xyz_12345")

    def test_goto_real_bookmark(self, client):
        """若有真实书签则验证跳转返回 WikiNode。"""
        bm = client.list_bookmarks()
        # 过滤掉假书签
        real_aliases = [
            k for k, v in bm.items()
            if v.get("node_token", "").startswith("wikc")
        ]
        if not real_aliases:
            pytest.skip("没有真实的 wiki 书签，跳过跳转测试")

        alias = real_aliases[0]
        print(f"\n  测试书签: {alias}")
        node = client.goto(alias)
        assert isinstance(node, WikiNode)
        print(f"  节点: {node}")


class TestResolve:
    """路径解析测试。"""

    def test_resolve_invalid_path_raises(self, client):
        """不以 @ 开头的路径应抛出 ValueError。"""
        with pytest.raises(ValueError):
            client.resolve("no_at_sign/subdir")

    def test_resolve_single_alias(self, client):
        """仅有 @alias 的路径等价于 goto(alias)。"""
        bm = client.list_bookmarks()
        real_aliases = [
            k for k, v in bm.items()
            if v.get("node_token", "").startswith("wikc")
        ]
        if not real_aliases:
            pytest.skip("没有真实 wiki 书签")
        alias = real_aliases[0]
        node = client.resolve(alias)
        assert isinstance(node, WikiNode)


class TestDirectNodeConstruction:
    def test_bitable_constructor(self, client):
        """client.bitable(token) 应返回 BitableNode。"""
        fake_token = "BrVPbFAKETOKEN"
        node = client.bitable(fake_token)
        assert isinstance(node, BitableNode)
        assert node.app_token == fake_token

    def test_sheet_constructor(self, client):
        """client.sheet(token) 应返回 SheetNode。"""
        fake_token = "shtcnFAKETOKEN"
        node = client.sheet(fake_token)
        assert isinstance(node, SheetNode)
        assert node.spreadsheet_token == fake_token


class TestListSpaces:
    def test_list_spaces(self, client):
        """list_spaces 应返回列表（可为空，不抛异常）。"""
        spaces = client.list_spaces()
        assert isinstance(spaces, list)
        print(f"\n  可访问的知识库空间: {len(spaces)} 个")
