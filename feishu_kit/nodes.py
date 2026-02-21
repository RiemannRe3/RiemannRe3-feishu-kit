# -*- coding: utf-8 -*-
"""
飞书节点对象层

提供对飞书各类资源的面向对象封装，支持链式导航和读写操作：

  - WikiNode      ：知识库节点（可 ls / cd / get / 读文档内容）
  - BitableNode   ：多维表格（可 query / append_rows / create_table 等）
  - SheetNode     ：电子表格（可 write / append / get_sheets 等）

典型用法::

    from feishu_kit.config import load_config
    from feishu_kit.nodes import WikiNode

    load_config()  # 加载 .env
    root = WikiNode(space_id="xxx", node_token="yyy")
    children = root.ls()               # 列出子节点
    target = root.get("实验记录")       # 按名称查找
    bitable = target.to_bitable()      # 若节点是多维表格，转换为 BitableNode
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    pass


class WikiNode:
    """
    飞书知识库节点。

    Attributes:
        space_id:    所属知识库空间 ID
        node_token:  节点 token
        title:       节点标题
        obj_type:    节点对象类型（docx / sheet / bitable / folder 等）
        obj_token:   底层资源 token（用于访问 bitable / sheet 等）
        has_child:   是否有子节点
        parent_node_token: 父节点 token
    """

    def __init__(
        self,
        space_id: str,
        node_token: str,
        title: str = "",
        obj_type: str = "docx",
        obj_token: str = "",
        has_child: bool = False,
        parent_node_token: str = "",
        _wiki_api: Any = None,
    ):
        self.space_id = space_id
        self.node_token = node_token
        self.title = title
        self.obj_type = obj_type
        self.obj_token = obj_token
        self.has_child = has_child
        self.parent_node_token = parent_node_token
        self._api = _wiki_api  # FeishuWikiAPI 实例（懒注入）

    # ──────────────────────────────────────────
    # 内部：API 懒加载
    # ──────────────────────────────────────────

    def _get_api(self):
        """懒加载 FeishuWikiAPI，避免循环导入。"""
        if self._api is None:
            from feishu_kit.wiki_api import FeishuWikiAPI
            self._api = FeishuWikiAPI()
        return self._api

    @classmethod
    def _from_raw(cls, raw: Dict[str, Any], api: Any = None) -> "WikiNode":
        """从 API 返回的原始节点字典构建 WikiNode 实例。"""
        return cls(
            space_id=raw.get("space_id", ""),
            node_token=raw.get("node_token", ""),
            title=raw.get("title", ""),
            obj_type=raw.get("obj_type", "docx"),
            obj_token=raw.get("obj_token", ""),
            has_child=raw.get("has_child", False),
            parent_node_token=raw.get("parent_node_token", ""),
            _wiki_api=api,
        )

    # ──────────────────────────────────────────
    # 导航操作
    # ──────────────────────────────────────────

    def ls(self) -> List[Union["WikiNode", "BitableNode", "SheetNode"]]:
        """
        列出当前节点的所有直接子节点。

        Returns:
            子节点列表，根据 obj_type 自动返回对应节点类型。
        """
        api = self._get_api()
        raws = api.list_nodes(self.space_id, parent_node_token=self.node_token)
        return [_make_node(r, api) for r in raws]

    def get(self, name: str) -> Union["WikiNode", "BitableNode", "SheetNode"]:
        """
        在当前节点的直接子节点中按名称（模糊匹配）查找。

        Args:
            name: 节点标题（精确或包含匹配）

        Returns:
            匹配的节点对象

        Raises:
            KeyError: 未找到名称匹配的子节点
        """
        children = self.ls()
        # 先精确匹配，再模糊匹配
        for child in children:
            if hasattr(child, "title") and child.title == name:
                return child
        for child in children:
            if hasattr(child, "title") and name in child.title:
                return child
        raise KeyError(f"在节点 '{self.title}' 下未找到名称包含 '{name}' 的子节点")

    def cd(self, name: str) -> "WikiNode":
        """
        进入指定名称的子节点（仅返回 WikiNode 类型）。

        Args:
            name: 子节点标题

        Returns:
            子 WikiNode

        Raises:
            KeyError: 未找到
            TypeError: 找到的节点不是 WikiNode 类型
        """
        child = self.get(name)
        if not isinstance(child, WikiNode):
            raise TypeError(f"节点 '{name}' 类型为 {type(child).__name__}，不是 WikiNode")
        return child

    # ──────────────────────────────────────────
    # 节点内容
    # ──────────────────────────────────────────

    def read_content(self) -> str:
        """
        读取 docx 类型节点的纯文本内容。

        Returns:
            文档纯文本字符串

        Raises:
            TypeError: 节点不是 docx 类型时
        """
        if self.obj_type not in ("doc", "docx"):
            raise TypeError(f"read_content 仅支持 docx 节点，当前类型: {self.obj_type}")
        api = self._get_api()
        return api.get_doc_content(self.obj_token)

    # ──────────────────────────────────────────
    # 类型转换
    # ──────────────────────────────────────────

    def to_bitable(self) -> "BitableNode":
        """将节点转换为 BitableNode（仅 obj_type == 'bitable' 时有效）。"""
        if self.obj_type != "bitable":
            raise TypeError(f"节点类型为 {self.obj_type}，无法转换为 BitableNode")
        return BitableNode(app_token=self.obj_token)

    def to_sheet(self) -> "SheetNode":
        """将节点转换为 SheetNode（仅 obj_type == 'sheet' 时有效）。"""
        if self.obj_type != "sheet":
            raise TypeError(f"节点类型为 {self.obj_type}，无法转换为 SheetNode")
        return SheetNode(spreadsheet_token=self.obj_token)

    # ──────────────────────────────────────────
    # 写操作
    # ──────────────────────────────────────────

    def create_child(
        self,
        title: str,
        obj_type: str = "docx",
    ) -> "WikiNode":
        """
        在当前节点下创建子节点。

        Args:
            title:    子节点标题
            obj_type: 类型（docx / sheet / bitable）

        Returns:
            新创建的 WikiNode
        """
        api = self._get_api()
        raw = api.create_node(
            space_id=self.space_id,
            title=title,
            obj_type=obj_type,
            parent_node_token=self.node_token,
        )
        return WikiNode._from_raw(raw, api)

    def delete(self) -> None:
        """删除当前节点（含所有子节点，不可恢复）。"""
        api = self._get_api()
        api.delete_node(self.space_id, self.node_token)

    # ──────────────────────────────────────────
    # 属性与显示
    # ──────────────────────────────────────────

    @property
    def url(self) -> str:
        """返回节点飞书网页链接。"""
        api = self._get_api()
        return api.node_url(self.node_token)

    def __repr__(self) -> str:
        return f"WikiNode(title={self.title!r}, type={self.obj_type}, token={self.node_token})"


# ──────────────────────────────────────────────────────────────
# BitableNode
# ──────────────────────────────────────────────────────────────

class BitableNode:
    """
    飞书多维表格节点。

    Attributes:
        app_token: 多维表格的 app_token
    """

    def __init__(self, app_token: str, _builder: Any = None):
        self.app_token = app_token
        self._builder = _builder  # FeishuBitableBuilder 实例（懒注入）

    def _get_builder(self):
        """懒加载 FeishuBitableBuilder。"""
        if self._builder is None:
            from feishu_kit.bitable_builder import FeishuBitableBuilder
            self._builder = FeishuBitableBuilder()
        return self._builder

    # ──────────────────────────────────────────
    # 数据表管理
    # ──────────────────────────────────────────

    def list_tables(self) -> List[Dict[str, Any]]:
        """
        列出多维表格中的所有数据表。

        Returns:
            数据表列表，每项含 table_id、name 等
        """
        import requests
        builder = self._get_builder()
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables"
        resp = requests.get(url, headers=builder._headers(), timeout=15)
        resp.raise_for_status()
        data = builder._check_resp(resp.json(), "列出数据表")
        return data.get("data", {}).get("items", [])

    def get_table_id(self, table_name: str) -> str:
        """
        按名称查找数据表 ID。

        Args:
            table_name: 数据表名称（精确匹配）

        Returns:
            table_id 字符串

        Raises:
            KeyError: 未找到对应名称的数据表
        """
        tables = self.list_tables()
        for t in tables:
            if t.get("name") == table_name:
                return t["table_id"]
        # 若 table_name 为空，返回第一个
        if not table_name and tables:
            return tables[0]["table_id"]
        raise KeyError(f"多维表格 {self.app_token} 中未找到数据表 '{table_name}'")

    # ──────────────────────────────────────────
    # 记录读写
    # ──────────────────────────────────────────

    def query(
        self,
        table_name: str = "",
        filter_formula: str = "",
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        查询数据表中的记录。

        Args:
            table_name:     数据表名称，留空使用第一个数据表
            filter_formula: 过滤公式（飞书 formula 语法）
            page_size:      每页数量，最大 500

        Returns:
            记录列表，每项为 {字段名: 值} 的字典
        """
        import requests
        builder = self._get_builder()
        table_id = self.get_table_id(table_name)
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"

        all_records: List[Dict] = []
        page_token: Optional[str] = None

        while True:
            params: Dict[str, Any] = {"page_size": min(page_size, 500)}
            if page_token:
                params["page_token"] = page_token
            if filter_formula:
                params["filter"] = filter_formula

            resp = requests.get(url, params=params, headers=builder._headers(), timeout=15)
            resp.raise_for_status()
            data = builder._check_resp(resp.json(), "查询记录")
            items = data.get("data", {}).get("items", [])
            all_records.extend(item.get("fields", {}) for item in items)

            if not data.get("data", {}).get("has_more"):
                break
            page_token = data.get("data", {}).get("page_token")

        return all_records

    def append_rows(
        self,
        rows: List[Dict[str, Any]],
        table_name: str = "",
    ) -> dict:
        """
        向数据表追加多条记录。

        Args:
            rows:       记录列表，每项为 {字段名: 值} 的字典
            table_name: 数据表名称，留空使用第一个数据表

        Returns:
            API 响应字典
        """
        builder = self._get_builder()
        table_id = self.get_table_id(table_name)
        return builder.add_records(self.app_token, table_id, rows)

    def create_table(
        self,
        table_name: str,
        fields_config: Optional[List[Dict]] = None,
    ) -> str:
        """
        在多维表格中新建数据表并配置字段。

        Args:
            table_name:    数据表名称
            fields_config: 字段配置列表（同 FeishuBitableBuilder.setup_fields）

        Returns:
            新建数据表的 table_id
        """
        builder = self._get_builder()
        table_id = builder.create_table(self.app_token, table_name)
        if fields_config:
            import time
            time.sleep(0.5)
            builder.setup_fields(self.app_token, table_id, fields_config)
        return table_id

    # ──────────────────────────────────────────
    # 属性
    # ──────────────────────────────────────────

    @property
    def url(self) -> str:
        """返回多维表格飞书网页链接（需 FEISHU_DOMAIN 已设置）。"""
        import os
        domain = os.environ.get("FEISHU_DOMAIN", "open")
        return f"https://{domain}.feishu.cn/base/{self.app_token}"

    def __repr__(self) -> str:
        return f"BitableNode(app_token={self.app_token!r})"


# ──────────────────────────────────────────────────────────────
# SheetNode
# ──────────────────────────────────────────────────────────────

class SheetNode:
    """
    飞书电子表格节点。

    Attributes:
        spreadsheet_token: 电子表格的 token
    """

    def __init__(self, spreadsheet_token: str, _builder: Any = None):
        self.spreadsheet_token = spreadsheet_token
        self._builder = _builder  # FeishuSheetBuilder 实例（懒注入）

    def _get_builder(self):
        """懒加载 FeishuSheetBuilder。"""
        if self._builder is None:
            from feishu_kit.sheet_builder import FeishuSheetBuilder
            self._builder = FeishuSheetBuilder()
        return self._builder

    # ──────────────────────────────────────────
    # 工作表管理
    # ──────────────────────────────────────────

    def get_sheets(self) -> List[Dict[str, Any]]:
        """
        列出所有工作表。

        Returns:
            工作表列表，每项含 sheetId、title、index 等
        """
        builder = self._get_builder()
        return builder.get_sheets(self.spreadsheet_token)

    def get_sheet_id(self, sheet_name: str = "") -> str:
        """
        按名称查找工作表 ID（留空返回第一个）。

        Returns:
            sheetId 字符串
        """
        sheets = self.get_sheets()
        if not sheets:
            raise RuntimeError(f"表格 {self.spreadsheet_token} 没有工作表")
        if not sheet_name:
            return sheets[0]["sheetId"]
        for s in sheets:
            if s.get("title") == sheet_name:
                return s["sheetId"]
        raise KeyError(f"未找到工作表 '{sheet_name}'")

    # ──────────────────────────────────────────
    # 数据读写
    # ──────────────────────────────────────────

    def write(
        self,
        data: List[List[Any]],
        sheet_name: str = "",
        start_row: int = 1,
        start_col: str = "A",
    ) -> dict:
        """
        覆盖写入二维数据到指定工作表。

        Args:
            data:       二维数组（第一行通常为表头）
            sheet_name: 工作表名称，留空使用第一个
            start_row:  起始行（1-indexed）
            start_col:  起始列字母

        Returns:
            API 响应字典
        """
        builder = self._get_builder()
        sheet_id = self.get_sheet_id(sheet_name)
        return builder.write_data(self.spreadsheet_token, sheet_id, data, start_row, start_col)

    def append(
        self,
        rows: List[List[Any]],
        sheet_name: str = "",
    ) -> dict:
        """
        在工作表末尾追加行。

        Args:
            rows:       要追加的行（二维数组）
            sheet_name: 工作表名称，留空使用第一个

        Returns:
            API 响应字典
        """
        builder = self._get_builder()
        sheet_id = self.get_sheet_id(sheet_name)
        return builder.append_rows(self.spreadsheet_token, sheet_id, rows)

    # ──────────────────────────────────────────
    # 属性
    # ──────────────────────────────────────────

    @property
    def url(self) -> str:
        """返回电子表格飞书网页链接（需 FEISHU_DOMAIN 已设置）。"""
        import os
        domain = os.environ.get("FEISHU_DOMAIN", "open")
        return f"https://{domain}.feishu.cn/sheets/{self.spreadsheet_token}"

    def __repr__(self) -> str:
        return f"SheetNode(spreadsheet_token={self.spreadsheet_token!r})"


# ──────────────────────────────────────────────────────────────
# 工厂函数
# ──────────────────────────────────────────────────────────────

def _make_node(
    raw: Dict[str, Any],
    api: Any = None,
) -> Union[WikiNode, BitableNode, SheetNode]:
    """
    根据节点的 obj_type 返回对应的节点对象。
    bitable / sheet 类型直接构造对应节点；其余类型构造 WikiNode。
    """
    obj_type = raw.get("obj_type", "docx")
    obj_token = raw.get("obj_token", "")

    if obj_type == "bitable" and obj_token:
        return BitableNode(app_token=obj_token)
    if obj_type == "sheet" and obj_token:
        return SheetNode(spreadsheet_token=obj_token)
    return WikiNode._from_raw(raw, api)
