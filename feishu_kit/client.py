# -*- coding: utf-8 -*-
"""
FeishuClient — 飞书工具包统一门面层

通过一个入口对象访问所有功能：知识库导航、书签跳转、路径解析、
多维表格/电子表格构建等。

典型用法::

    from feishu_kit import FeishuClient

    client = FeishuClient()                   # 自动加载 .env

    # 按书签别名跳转到 Wiki 节点
    bot_node = client.goto("@bot")            # 返回 WikiNode

    # 路径解析：先跳转 @bot，再深入子节点
    table = client.resolve("@bot/实验记录")   # 返回 WikiNode / BitableNode / SheetNode

    # 直接用 token 构造 BitableNode / SheetNode
    bitable = client.bitable("BrVPb...")
    sheet   = client.sheet("shtcn...")

    # 修改书签
    client.save_bookmark("@report", node_token="wikcnXXX", space_id="7xxx")
    client.list_bookmarks()
    client.delete_bookmark("@report")
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from feishu_kit.config import load_config
from feishu_kit.nodes import BitableNode, SheetNode, WikiNode, _make_node


# 书签文件路径（与项目根目录的 .feishu_bookmarks.json 保持一致）
def _bookmark_path() -> Path:
    return Path(__file__).parent.parent / ".feishu_bookmarks.json"


class FeishuClient:
    """
    飞书工具包统一入口。

    所有功能均通过此类的方法访问，无需直接操作底层 API 类。

    Args:
        env_path: 指定 .env 文件路径；留空则自动查找项目根目录的 .env
        auto_load_env: 是否自动加载 .env（默认 True）
    """

    def __init__(
        self,
        env_path: str = "",
        auto_load_env: bool = True,
    ):
        if auto_load_env:
            self._cfg = load_config(env_path)
        else:
            self._cfg = {
                "app_id":       os.environ.get("FEISHU_APP_ID", ""),
                "app_secret":   os.environ.get("FEISHU_APP_SECRET", ""),
                "domain":       os.environ.get("FEISHU_DOMAIN", ""),
                "folder_token": os.environ.get("FEISHU_FOLDER_TOKEN", ""),
                "default_mode": os.environ.get("FEISHU_DEFAULT_MODE", "auto"),
            }

        self._wiki_api: Any = None
        self._drive_api: Any = None
        self._bitable_builder: Any = None
        self._sheet_builder: Any = None

    # ──────────────────────────────────────────
    # 内部：懒加载 API 实例
    # ──────────────────────────────────────────

    def _get_wiki_api(self):
        if self._wiki_api is None:
            from feishu_kit.wiki_api import FeishuWikiAPI
            self._wiki_api = FeishuWikiAPI(
                app_id=self._cfg["app_id"],
                app_secret=self._cfg["app_secret"],
                domain=self._cfg["domain"],
            )
        return self._wiki_api

    def _get_drive_api(self):
        if self._drive_api is None:
            from feishu_kit.drive_api import FeishuDriveAPI
            self._drive_api = FeishuDriveAPI(
                app_id=self._cfg["app_id"],
                app_secret=self._cfg["app_secret"],
                domain=self._cfg["domain"],
            )
        return self._drive_api

    def _get_bitable_builder(self):
        if self._bitable_builder is None:
            from feishu_kit.bitable_builder import FeishuBitableBuilder
            self._bitable_builder = FeishuBitableBuilder(
                app_id=self._cfg["app_id"],
                app_secret=self._cfg["app_secret"],
            )
        return self._bitable_builder

    def _get_sheet_builder(self):
        if self._sheet_builder is None:
            from feishu_kit.sheet_builder import FeishuSheetBuilder
            self._sheet_builder = FeishuSheetBuilder(
                app_id=self._cfg["app_id"],
                app_secret=self._cfg["app_secret"],
            )
        return self._sheet_builder

    # ──────────────────────────────────────────
    # 书签管理
    # ──────────────────────────────────────────

    def _load_bookmarks(self) -> Dict[str, Dict[str, str]]:
        """加载 .feishu_bookmarks.json，返回 {alias: {node_token, space_id, title}} 字典。"""
        path = _bookmark_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_bookmarks(self, bm: Dict[str, Dict[str, str]]) -> None:
        """将书签字典写回 .feishu_bookmarks.json。"""
        path = _bookmark_path()
        path.write_text(json.dumps(bm, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_bookmarks(self) -> Dict[str, Dict[str, str]]:
        """
        返回所有书签。

        Returns:
            {alias: {"node_token": ..., "space_id": ..., "title": ...}} 字典
        """
        return self._load_bookmarks()

    def save_bookmark(
        self,
        alias: str,
        node_token: str,
        space_id: str,
        title: str = "",
    ) -> None:
        """
        保存书签。

        Args:
            alias:       书签别名（建议加 @ 前缀，如 "@bot"）
            node_token:  Wiki 节点 token
            space_id:    知识库空间 ID
            title:       节点标题（可选，用于显示）
        """
        key = alias if alias.startswith("@") else f"@{alias}"
        bm = self._load_bookmarks()
        bm[key] = {"node_token": node_token, "space_id": space_id, "title": title}
        self._save_bookmarks(bm)

    def delete_bookmark(self, alias: str) -> bool:
        """
        删除书签。

        Returns:
            True 表示删除成功，False 表示别名不存在
        """
        key = alias if alias.startswith("@") else f"@{alias}"
        bm = self._load_bookmarks()
        if key in bm:
            del bm[key]
            self._save_bookmarks(bm)
            return True
        return False

    # ──────────────────────────────────────────
    # 导航与路径解析
    # ──────────────────────────────────────────

    def goto(self, alias: str) -> WikiNode:
        """
        通过书签别名跳转到 Wiki 节点。

        Args:
            alias: 书签别名（如 "@bot" 或 "bot"）

        Returns:
            WikiNode 对象

        Raises:
            KeyError: 别名不存在
        """
        key = alias if alias.startswith("@") else f"@{alias}"
        bm = self._load_bookmarks()
        if key not in bm:
            raise KeyError(f"书签 '{key}' 不存在，请先用 save_bookmark 保存")
        info = bm[key]
        api = self._get_wiki_api()
        # 通过 get_node 获取最新节点信息
        try:
            raw = api.get_node(info["node_token"])
        except Exception:
            # 降级：用书签中保存的信息构造
            raw = {
                "node_token": info["node_token"],
                "space_id": info["space_id"],
                "title": info.get("title", key),
                "obj_type": "docx",
                "obj_token": "",
            }
        return WikiNode._from_raw(raw, api)

    def resolve(
        self,
        path: str,
    ) -> Union[WikiNode, BitableNode, SheetNode]:
        """
        解析路径并返回对应节点。

        支持格式：
          - "@alias"         ：直接返回书签对应节点
          - "@alias/子节点"   ：从书签节点向下按名称导航
          - "@alias/a/b/c"   ：多级导航

        Args:
            path: 路径字符串

        Returns:
            节点对象

        Raises:
            ValueError: 路径格式错误（不以 @ 开头）
        """
        parts = [p.strip() for p in path.split("/") if p.strip()]
        if not parts or not parts[0].startswith("@"):
            raise ValueError(f"路径必须以 @alias 开头，当前: '{path}'")

        node: Union[WikiNode, BitableNode, SheetNode] = self.goto(parts[0])

        for name in parts[1:]:
            if not isinstance(node, WikiNode):
                raise TypeError(
                    f"在路径 '{path}' 中，节点 '{node}' 不是 WikiNode，无法继续向下导航"
                )
            node = node.get(name)

        return node

    # ──────────────────────────────────────────
    # 知识库
    # ──────────────────────────────────────────

    def list_spaces(self) -> List[Dict[str, Any]]:
        """列出所有可访问的知识库空间。"""
        return self._get_wiki_api().list_spaces()

    def get_space_root(self, space_id: str) -> List[WikiNode]:
        """
        列出指定知识库空间的根节点。

        Returns:
            根节点列表（WikiNode）
        """
        api = self._get_wiki_api()
        raws = api.list_nodes(space_id)
        return [WikiNode._from_raw(r, api) for r in raws]

    # ──────────────────────────────────────────
    # 直接构造节点
    # ──────────────────────────────────────────

    def bitable(self, app_token: str) -> BitableNode:
        """
        用已知 app_token 构造 BitableNode。

        Args:
            app_token: 多维表格 token

        Returns:
            BitableNode 对象
        """
        return BitableNode(app_token=app_token, _builder=self._get_bitable_builder())

    def sheet(self, spreadsheet_token: str) -> SheetNode:
        """
        用已知 spreadsheet_token 构造 SheetNode。

        Args:
            spreadsheet_token: 电子表格 token

        Returns:
            SheetNode 对象
        """
        return SheetNode(spreadsheet_token=spreadsheet_token, _builder=self._get_sheet_builder())

    # ──────────────────────────────────────────
    # 云盘操作（Drive）
    # ──────────────────────────────────────────

    def list_drive_files(self, folder_token: str = "") -> List[Dict[str, Any]]:
        """
        列出云盘指定文件夹中的文件。

        Args:
            folder_token: 文件夹 token；留空使用 FEISHU_FOLDER_TOKEN

        Returns:
            文件列表
        """
        api = self._get_drive_api()
        token = folder_token or self._cfg.get("folder_token", "")
        return api.list_files(token)

    def create_bitable_in_drive(
        self,
        name: str,
        folder_token: str = "",
    ) -> BitableNode:
        """
        在云盘指定文件夹下创建多维表格。

        Args:
            name:         多维表格名称
            folder_token: 目标文件夹 token；留空使用 FEISHU_FOLDER_TOKEN

        Returns:
            新建的 BitableNode
        """
        builder = self._get_bitable_builder()
        ftoken = folder_token or self._cfg.get("folder_token", "")
        app_token = builder.create_bitable(name, folder_token=ftoken)
        return self.bitable(app_token)

    def create_sheet_in_drive(
        self,
        title: str,
        folder_token: str = "",
    ) -> SheetNode:
        """
        在云盘指定文件夹下创建电子表格。

        Args:
            title:        表格标题
            folder_token: 目标文件夹 token；留空使用 FEISHU_FOLDER_TOKEN

        Returns:
            新建的 SheetNode
        """
        builder = self._get_sheet_builder()
        ftoken = folder_token or self._cfg.get("folder_token", "")
        ss_token = builder.create_spreadsheet(title, folder_token=ftoken)
        return self.sheet(ss_token)

    # ──────────────────────────────────────────
    # 配置信息
    # ──────────────────────────────────────────

    @property
    def config(self) -> Dict[str, Any]:
        """返回当前配置（隐藏 app_secret）。"""
        safe = dict(self._cfg)
        if safe.get("app_secret"):
            safe["app_secret"] = "***"
        return safe

    def __repr__(self) -> str:
        return f"FeishuClient(domain={self._cfg.get('domain')!r}, mode={self._cfg.get('default_mode')!r})"
