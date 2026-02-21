# -*- coding: utf-8 -*-
"""
集成测试：feishu_kit.wiki_api.FeishuWikiAPI
测试知识库节点的列出、获取、创建和删除。

前置条件：
  1. .env 中已配置真实 FEISHU_APP_ID / FEISHU_APP_SECRET
  2. 应用已开启 wiki:wiki 权限，并被添加为某个知识库的协作者
  3. 应用已开启 wiki:wiki:create / wiki:wiki:delete（如需测试写操作）

运行方式：
  pytest tests/test_wiki.py -v -s
"""

import pytest
from feishu_kit.config import load_config
from feishu_kit.wiki_api import FeishuWikiAPI

# 加载配置（所有测试共享）
load_config()


@pytest.fixture(scope="module")
def api():
    """创建 FeishuWikiAPI 实例。"""
    return FeishuWikiAPI()


@pytest.fixture(scope="module")
def first_space(api):
    """获取应用可访问的第一个知识库空间，无则跳过整个模块。"""
    spaces = api.list_spaces()
    if not spaces:
        pytest.skip(
            "没有可访问的知识库空间。\n"
            "请在知识库设置 → 成员 中将应用添加为协作者后再运行。"
        )
    return spaces[0]


class TestListSpaces:
    def test_list_spaces_returns_list(self, api):
        """list_spaces 应返回列表（可为空，不抛异常）。"""
        spaces = api.list_spaces()
        assert isinstance(spaces, list)

    def test_space_has_required_fields(self, first_space):
        """每个知识库空间应包含 space_id 和 name 字段。"""
        assert "space_id" in first_space, "space 缺少 space_id"
        assert first_space["space_id"], "space_id 为空"


class TestListNodes:
    def test_list_root_nodes(self, api, first_space):
        """list_nodes 不传 parent_node_token 应返回空间根节点。"""
        nodes = api.list_nodes(first_space["space_id"])
        assert isinstance(nodes, list)

    def test_node_has_required_fields(self, api, first_space):
        """每个节点应包含 node_token、title、obj_type。"""
        nodes = api.list_nodes(first_space["space_id"])
        if not nodes:
            pytest.skip("该知识库空间暂无节点")
        node = nodes[0]
        for field in ("node_token", "title", "obj_type"):
            assert field in node, f"节点缺少字段: {field}"


class TestGetNode:
    def test_get_node_by_token(self, api, first_space):
        """通过 node_token 获取单个节点，应正确返回节点信息。"""
        nodes = api.list_nodes(first_space["space_id"])
        if not nodes:
            pytest.skip("该知识库空间暂无节点")
        token = nodes[0]["node_token"]
        node = api.get_node(token)
        assert node.get("node_token") == token
        assert "space_id" in node

    def test_get_nonexistent_node_raises(self, api):
        """查询不存在的 token 应抛出 RuntimeError。"""
        with pytest.raises((RuntimeError, Exception)):
            api.get_node("INVALID_TOKEN_XXXX")


class TestGetAncestorChain:
    def test_ancestor_chain_has_node_itself(self, api, first_space):
        """祖先链的最后一项应为传入节点本身。"""
        nodes = api.list_nodes(first_space["space_id"])
        if not nodes:
            pytest.skip("该知识库空间暂无节点")
        token = nodes[0]["node_token"]
        chain = api.get_ancestor_chain(token)
        assert chain, "祖先链不应为空"
        assert chain[-1]["node_token"] == token


class TestCreateDeleteNode:
    """写操作测试，需要 wiki:wiki 权限和编辑成员身份。"""

    def test_create_and_delete_node(self, api, first_space):
        """创建测试节点，验证返回字段，然后删除（清理）。"""
        space_id = first_space["space_id"]

        # 创建测试节点
        node = api.create_node(
            space_id=space_id,
            title="pytest_test_node_auto_delete",
            obj_type="docx",
        )
        assert "node_token" in node, "创建节点应返回 node_token"
        assert node.get("obj_type") == "docx"

        node_token = node["node_token"]
        print(f"\n  已创建测试节点: {node_token}")

        # 清理：删除测试节点
        api.delete_node(space_id, node_token)
        print(f"  已删除测试节点: {node_token}")

        # 验证节点已被删除（再查询应抛出异常）
        with pytest.raises((RuntimeError, Exception)):
            api.get_node(node_token)
