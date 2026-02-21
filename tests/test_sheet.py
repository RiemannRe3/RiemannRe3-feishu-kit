# -*- coding: utf-8 -*-
"""
集成测试：feishu_kit.sheet_builder.FeishuSheetBuilder + SheetNode
测试电子表格的创建、工作表管理、数据读写。

前置条件：
  1. .env 中已配置真实凭证
  2. 应用已开启 sheets:spreadsheet 权限
  3. FEISHU_FOLDER_TOKEN 指向应用有写权限的文件夹

运行方式：
  pytest tests/test_sheet.py -v -s
"""

import time
import pytest
from feishu_kit.config import load_config
from feishu_kit.sheet_builder import FeishuSheetBuilder
from feishu_kit.nodes import SheetNode

load_config()

import os
FOLDER_TOKEN = os.environ.get("FEISHU_FOLDER_TOKEN", "")


@pytest.fixture(scope="module")
def builder():
    return FeishuSheetBuilder()


@pytest.fixture(scope="module")
def test_sheet(builder):
    """创建测试电子表格，测试完毕后删除。"""
    if not FOLDER_TOKEN:
        pytest.skip("FEISHU_FOLDER_TOKEN 未配置，跳过 sheet 写操作测试")

    ss_token = builder.create_spreadsheet(
        title="pytest_test_sheet_auto_delete",
        folder_token=FOLDER_TOKEN,
    )
    yield ss_token

    # 清理
    try:
        from feishu_kit.drive_api import FeishuDriveAPI
        drive = FeishuDriveAPI()
        drive.delete_file(ss_token, "sheet")
        print(f"\n  [清理] 已删除测试电子表格: {ss_token}")
    except Exception as e:
        print(f"\n  [清理失败] {e}，请手动删除电子表格: {ss_token}")


class TestCreateSpreadsheet:
    def test_create_returns_token(self, test_sheet):
        """create_spreadsheet 应返回非空 spreadsheet_token。"""
        assert test_sheet
        assert isinstance(test_sheet, str)
        print(f"\n  spreadsheet_token: {test_sheet}")


class TestGetSheets:
    def test_get_sheets_returns_list(self, builder, test_sheet):
        """新建表格默认有 1 个工作表。"""
        sheets = builder.get_sheets(test_sheet)
        assert isinstance(sheets, list)
        assert len(sheets) >= 1
        assert "sheetId" in sheets[0]
        print(f"\n  默认工作表: {sheets[0]}")


class TestRenameSheet:
    def test_rename_sheet(self, builder, test_sheet):
        """rename_sheet 应不报错，工作表名称更新。"""
        sheets = builder.get_sheets(test_sheet)
        sheet_id = sheets[0]["sheetId"]
        builder.rename_sheet(test_sheet, sheet_id, "测试工作表")
        time.sleep(0.3)
        # 重新获取验证
        sheets_after = builder.get_sheets(test_sheet)
        titles = [s.get("title") for s in sheets_after]
        assert "测试工作表" in titles, f"重命名后工作表名称未更新，当前: {titles}"


class TestWriteAndAppend:
    def test_write_data(self, builder, test_sheet):
        """write_data 应正确写入数据。"""
        sheets = builder.get_sheets(test_sheet)
        sheet_id = sheets[0]["sheetId"]
        data = [
            ["Name", "Value", "Status"],
            ["exp_001", 0.95, "done"],
            ["exp_002", 0.98, "running"],
        ]
        result = builder.write_data(test_sheet, sheet_id, data)
        assert result, "write_data 应返回非空响应"

    def test_append_rows(self, builder, test_sheet):
        """append_rows 应在现有数据末尾追加行。"""
        sheets = builder.get_sheets(test_sheet)
        sheet_id = sheets[0]["sheetId"]
        rows = [["exp_003", 0.99, "done"]]
        result = builder.append_rows(test_sheet, sheet_id, rows)
        assert result, "append_rows 应返回非空响应"
        print(f"\n  追加完成")


class TestSheetNodeApi:
    def test_sheet_node_write_and_append(self, test_sheet):
        """SheetNode.write + append 端到端验证。"""
        node = SheetNode(spreadsheet_token=test_sheet)
        result = node.write([["A", "B"], [1, 2], [3, 4]])
        assert result

        result2 = node.append([[5, 6]])
        assert result2

    def test_sheet_node_url(self, test_sheet):
        """SheetNode.url 应包含 spreadsheet_token。"""
        node = SheetNode(spreadsheet_token=test_sheet)
        url = node.url
        assert test_sheet in url
        assert "feishu.cn" in url
        print(f"\n  url: {url}")
