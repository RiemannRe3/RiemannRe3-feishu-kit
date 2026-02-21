# -*- coding: utf-8 -*-
"""
飞书知识库（Wiki）API 封装
支持：列出知识库空间、列出/获取节点、生成 wiki 链接。

API 参考：
  - 列出知识库空间:  GET /wiki/v2/spaces
  - 列出空间节点:    GET /wiki/v2/spaces/{space_id}/nodes
  - 获取节点信息:    GET /wiki/v2/spaces/get_node
  - 读取文档内容:    GET /docx/v1/documents/{document_id}/raw_content

前置条件：
  1. 飞书开放平台 → 权限管理 → 开通 wiki:wiki:readonly
  2. 知识库设置 → 成员 → 将应用添加为协作者（或设置全员可见）
"""

import os
import time
import requests
from typing import List, Dict, Optional, Any

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
TOKEN_URL = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"

# 节点类型 → 显示图标
NODE_TYPE_ICONS: Dict[str, str] = {
    "doc":     "📝",
    "docx":    "📝",
    "sheet":   "📊",
    "bitable": "🗃 ",
    "mindnote": "🧠",
    "file":    "📄",
    "wiki":    "📖",
    "folder":  "📁",
}


class FeishuWikiAPI:
    """
    飞书知识库操作封装。

    典型用法::

        api = FeishuWikiAPI()
        spaces = api.list_spaces()          # 列出所有可访问的知识库空间
        nodes = api.list_nodes(space_id)    # 列出空间根节点
        node  = api.get_node(node_token)    # 获取单个节点信息
    """

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        domain: Optional[str] = None,
    ):
        self.app_id     = app_id     or os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "")
        self.domain     = domain     or os.environ.get("FEISHU_DOMAIN", "")
        self._token: Optional[str] = None
        self._token_expire_at: float = 0

    # ──────────────────────────────────────────
    # 内部：Token 与请求
    # ──────────────────────────────────────────

    def _get_token(self) -> str:
        """获取并缓存 tenant_access_token（提前 60 秒刷新）。"""
        if self._token and time.time() < self._token_expire_at - 60:
            return self._token
        resp = requests.post(
            TOKEN_URL,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 token 失败: {data}")
        self._token = data["tenant_access_token"]
        self._token_expire_at = time.time() + data.get("expire", 7200)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def _check_resp(self, data: dict, action: str) -> dict:
        if data.get("code") != 0:
            raise RuntimeError(
                f"{action} 失败 (code={data.get('code')}): {data.get('msg')}"
            )
        return data

    # ──────────────────────────────────────────
    # 知识库空间
    # ──────────────────────────────────────────

    def list_spaces(self) -> List[Dict[str, Any]]:
        """
        列出应用可访问的所有知识库空间。

        Returns:
            每项包含 space_id, name, description 等
        """
        url = f"{FEISHU_API_BASE}/wiki/v2/spaces"
        all_spaces: List[Dict] = []
        page_token: Optional[str] = None

        while True:
            params: Dict[str, Any] = {"page_size": 50}
            if page_token:
                params["page_token"] = page_token

            resp = requests.get(url, params=params, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            data = self._check_resp(resp.json(), "列出知识库空间")

            items = data.get("data", {}).get("items", [])
            all_spaces.extend(items)

            if not data.get("data", {}).get("has_more"):
                break
            page_token = data.get("data", {}).get("page_token")

        return all_spaces

    # ──────────────────────────────────────────
    # 节点操作
    # ──────────────────────────────────────────

    def list_nodes(
        self,
        space_id: str,
        parent_node_token: str = "",
    ) -> List[Dict[str, Any]]:
        """
        列出指定空间（或节点）下的子节点。

        Args:
            space_id:          知识库空间 ID
            parent_node_token: 父节点 token，空字符串表示根目录

        Returns:
            节点列表，每项包含 node_token, title, obj_type, has_child 等
        """
        url = f"{FEISHU_API_BASE}/wiki/v2/spaces/{space_id}/nodes"
        all_nodes: List[Dict] = []
        page_token: Optional[str] = None

        while True:
            params: Dict[str, Any] = {"page_size": 50}
            if parent_node_token:
                params["parent_node_token"] = parent_node_token
            if page_token:
                params["page_token"] = page_token

            resp = requests.get(url, params=params, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            data = self._check_resp(resp.json(), "列出节点")

            items = data.get("data", {}).get("items", [])
            all_nodes.extend(items)

            if not data.get("data", {}).get("has_more"):
                break
            page_token = data.get("data", {}).get("page_token")

        return all_nodes

    def get_ancestor_chain(self, node_token: str) -> List[Dict[str, Any]]:
        """
        从给定节点出发，向上回溯父节点，返回从根到当前节点的完整链。

        Returns:
            List[{node_token, title, space_id}]，index 0 为最顶层祖先，最后一项为当前节点。
        """
        chain: List[Dict[str, Any]] = []
        token = node_token
        visited = set()
        while token and token not in visited:
            visited.add(token)
            try:
                node = self.get_node(token)
            except Exception:
                break
            chain.append(node)
            token = node.get("parent_node_token", "")
        chain.reverse()
        return chain

    def get_node(self, node_token: str) -> Dict[str, Any]:
        """
        通过 node_token 获取单个节点的详细信息（无需知道 space_id）。

        Returns:
            节点信息字典，包含 space_id, title, obj_type, obj_token,
            parent_node_token, has_child 等
        """
        url = f"{FEISHU_API_BASE}/wiki/v2/spaces/get_node"
        resp = requests.get(
            url,
            params={"token": node_token, "obj_type": "wiki"},
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = self._check_resp(resp.json(), "获取节点信息")
        return data.get("data", {}).get("node", {})

    # ──────────────────────────────────────────
    # 节点写操作（需要 wiki:wiki 权限 + 应用为知识库编辑成员）
    # ──────────────────────────────────────────

    def create_node(
        self,
        space_id: str,
        title: str,
        obj_type: str = "docx",
        parent_node_token: str = "",
    ) -> Dict[str, Any]:
        """
        在知识库中创建新节点。

        Args:
            space_id:           知识库空间 ID
            title:              节点标题
            obj_type:           节点类型：docx / sheet / bitable
            parent_node_token:  父节点 token，空字符串表示根目录

        Returns:
            节点信息字典（含 node_token, obj_token, obj_type 等）
        """
        url = f"{FEISHU_API_BASE}/wiki/v2/spaces/{space_id}/nodes"
        body: Dict[str, Any] = {
            "obj_type":   obj_type,
            "node_type":  "origin",
            "title":      title,
        }
        if parent_node_token:
            body["parent_node_token"] = parent_node_token

        resp = requests.post(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = self._check_resp(resp.json(), f"创建节点「{title}」")
        return data.get("data", {}).get("node", {})

    def delete_node(self, space_id: str, node_token: str) -> None:
        """
        删除指定节点（含其所有子节点，不可恢复）。

        Args:
            space_id:    知识库空间 ID
            node_token:  要删除的节点 token
        """
        url = f"{FEISHU_API_BASE}/wiki/v2/spaces/{space_id}/nodes/{node_token}"
        resp = requests.delete(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        self._check_resp(resp.json(), f"删除节点 {node_token}")

    def move_node(
        self,
        space_id: str,
        node_token: str,
        target_parent_token: str,
    ) -> None:
        """
        将节点移动到同一知识库内的另一父节点下。

        Args:
            space_id:            知识库空间 ID
            node_token:          要移动的节点 token
            target_parent_token: 目标父节点 token，空字符串表示移到根目录
        """
        url = f"{FEISHU_API_BASE}/wiki/v2/spaces/{space_id}/nodes/move"
        body: Dict[str, Any] = {"node_token": node_token}
        if target_parent_token:
            body["target_parent_token"] = target_parent_token
        resp = requests.post(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        self._check_resp(resp.json(), f"移动节点 {node_token}")

    # ──────────────────────────────────────────
    # 文档内容
    # ──────────────────────────────────────────

    def get_doc_content(self, obj_token: str) -> str:
        """
        读取 docx 类型节点的纯文本内容。

        Args:
            obj_token: 节点的 obj_token（非 node_token）

        Returns:
            文档纯文本字符串
        """
        url = f"{FEISHU_API_BASE}/docx/v1/documents/{obj_token}/raw_content"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = self._check_resp(resp.json(), "读取文档内容")
        return data.get("data", {}).get("content", "")

    # ──────────────────────────────────────────
    # URL 与显示工具
    # ──────────────────────────────────────────

    def node_url(self, node_token: str) -> str:
        """生成 wiki 节点的飞书网页链接。"""
        domain = self.domain or "open"
        return f"https://{domain}.feishu.cn/wiki/{node_token}"

    def icon(self, obj_type: str) -> str:
        return NODE_TYPE_ICONS.get(obj_type, "📄")
