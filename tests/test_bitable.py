# -*- coding: utf-8 -*-
"""
集成测试：feishu_kit.bitable_builder.FeishuBitableBuilder + BitableNode
测试多维表格的创建、数据表管理、记录读写。

前置条件：
  1. .env 中已配置真实凭证
  2. 应用已开启 bitable:app 权限
  3. FEISHU_FOLDER_TOKEN 指向一个应用有写权限的文件夹

运行方式：
  pytest tests/test_bitable.py -v -s
"""

import time
import pytest
from feishu_kit.config import load_config
from feishu_kit.bitable_builder import FeishuBitableBuilder, FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER
from feishu_kit.nodes import BitableNode

load_config()

import os
FOLDER_TOKEN = os.environ.get("FEISHU_FOLDER_TOKEN", "")


@pytest.fixture(scope="module")
def builder():
    return FeishuBitableBuilder()


@pytest.fixture(scope="module")
def test_bitable(builder):
    """创建一个测试用的多维表格，测试完毕后通过 Drive API 删除。"""
    if not FOLDER_TOKEN:
        pytest.skip("FEISHU_FOLDER_TOKEN 未配置，跳过 bitable 写操作测试")

    app_token = builder.create_bitable(
        name="pytest_test_bitable_auto_delete",
        folder_token=FOLDER_TOKEN,
    )
    yield app_token

    # 清理：通过 Drive API 删除
    try:
        from feishu_kit.drive_api import FeishuDriveAPI
        drive = FeishuDriveAPI()
        drive.delete_file(app_token, "bitable")
        print(f"\n  [清理] 已删除测试多维表格: {app_token}")
    except Exception as e:
        print(f"\n  [清理失败] {e}，请手动删除多维表格: {app_token}")


class TestCreateBitable:
    def test_create_returns_token(self, test_bitable):
        """create_bitable 应返回非空的 app_token。"""
        assert test_bitable
        assert isinstance(test_bitable, str)
        print(f"\n  app_token: {test_bitable}")


class TestCreateTable:
    def test_create_table(self, builder, test_bitable):
        """create_table 应返回非空的 table_id。"""
        time.sleep(0.5)
        table_id = builder.create_table(test_bitable, "测试数据表")
        assert table_id
        print(f"\n  table_id: {table_id}")


class TestGetFields:
    def test_get_fields_returns_list(self, builder, test_bitable):
        """新建表格默认应有至少一个字段。"""
        # 获取第一个数据表
        node = BitableNode(app_token=test_bitable, _builder=builder)
        tables = node.list_tables()
        assert tables, "应有至少一个数据表"
        table_id = tables[0]["table_id"]
        fields = builder.get_fields(test_bitable, table_id)
        assert isinstance(fields, list)
        assert len(fields) >= 1


class TestAddRecords:
    def test_add_and_query_records(self, builder, test_bitable):
        """add_records + query 端到端验证。"""
        node = BitableNode(app_token=test_bitable, _builder=builder)
        tables = node.list_tables()
        table_name = tables[0].get("name", "")

        records = [
            {"标题": "test_record_1"},
            {"标题": "test_record_2"},
        ]
        result = builder.add_records(test_bitable, tables[0]["table_id"], records)
        assert result, "add_records 应返回非空响应"

        time.sleep(0.5)
        queried = node.query(table_name=table_name)
        assert len(queried) >= 2, f"查询结果应 >= 2 条，实际: {len(queried)}"
        print(f"\n  查询到 {len(queried)} 条记录")


class TestBitableNodeDirectApi:
    def test_bitable_node_url(self, test_bitable):
        """BitableNode.url 应包含 app_token。"""
        node = BitableNode(app_token=test_bitable)
        url = node.url
        assert test_bitable in url
        assert "feishu.cn" in url
        print(f"\n  url: {url}")

    def test_bitable_node_repr(self, test_bitable):
        """repr 应包含 app_token。"""
        node = BitableNode(app_token=test_bitable)
        assert test_bitable in repr(node)
