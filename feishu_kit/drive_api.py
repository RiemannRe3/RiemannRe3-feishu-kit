# -*- coding: utf-8 -*-
"""
飞书云盘 Drive API 封装
支持：列出文件、创建文件夹、移动、重命名、删除、获取文件 URL。

API 参考：
  - 获取根目录:    GET  /open-apis/drive/explorer/v2/root_folder/meta
  - 列出文件:      GET  /open-apis/drive/v1/files?folder_token=xxx
  - 创建文件夹:    POST /open-apis/drive/v1/files/create_folder
  - 移动文件:      POST /open-apis/drive/v1/files/{token}/move
  - 重命名文件:    PATCH /open-apis/drive/v1/files/{token}
  - 删除文件:      DELETE /open-apis/drive/v1/files/{token}?type={type}
"""

import os
import time
import requests
from typing import List, Dict, Optional, Any


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
TOKEN_URL = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"

# 文件类型常量
FILE_TYPE_FOLDER  = "folder"
FILE_TYPE_SHEET   = "sheet"
FILE_TYPE_BITABLE = "bitable"
FILE_TYPE_DOC     = "doc"
FILE_TYPE_DOCX    = "docx"
FILE_TYPE_FILE    = "file"

# 文件类型 → 显示图标
FILE_TYPE_ICONS: Dict[str, str] = {
    FILE_TYPE_FOLDER:  "📁",
    FILE_TYPE_SHEET:   "📊",
    FILE_TYPE_BITABLE: "🗃 ",
    FILE_TYPE_DOC:     "📝",
    FILE_TYPE_DOCX:    "📝",
    FILE_TYPE_FILE:    "📄",
}

# URL 路径模板（{domain} 和 {token} 占位）
FILE_URL_PATTERNS: Dict[str, str] = {
    FILE_TYPE_FOLDER:  "https://{domain}.feishu.cn/drive/folder/{token}",
    FILE_TYPE_SHEET:   "https://{domain}.feishu.cn/sheets/{token}",
    FILE_TYPE_BITABLE: "https://{domain}.feishu.cn/base/{token}",
    FILE_TYPE_DOC:     "https://{domain}.feishu.cn/docs/{token}",
    FILE_TYPE_DOCX:    "https://{domain}.feishu.cn/docx/{token}",
    FILE_TYPE_FILE:    "https://{domain}.feishu.cn/file/{token}",
}


class FeishuDriveAPI:
    """
    飞书云盘操作封装。

    典型用法::

        api = FeishuDriveAPI()

        root_token = api.get_root_folder_token()
        files = api.list_files(root_token)
        for f in files:
            print(f["name"], f["type"], f["token"])
    """

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        domain: Optional[str] = None,
    ):
        """
        Args:
            app_id:     飞书 App ID，或从环境变量 FEISHU_APP_ID 读取
            app_secret: 飞书 App Secret，或从环境变量 FEISHU_APP_SECRET 读取
            domain:     企业域前缀（如 "n3kyhtp7sz"），或从 FEISHU_DOMAIN 读取
        """
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "")
        self.domain = domain or os.environ.get("FEISHU_DOMAIN", "")
        # 应用被授权的根文件夹 token（tenant token 只能访问此类已授权文件夹，
        # 不能访问"我的空间"个人根目录——那需要 user_access_token）
        self.root_folder_token = os.environ.get("FEISHU_FOLDER_TOKEN", "")
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
        """统一检查响应 code，非 0 时抛出带上下文的异常。"""
        if data.get("code") != 0:
            raise RuntimeError(
                f"{action} 失败 (code={data.get('code')}): {data.get('msg')} | {data}"
            )
        return data

    # ──────────────────────────────────────────
    # 目录操作
    # ──────────────────────────────────────────

    def get_root_folder_token(self) -> str:
        """
        获取"我的空间"根目录的 folder_token。

        Returns:
            根目录 folder_token 字符串
        """
        url = f"{FEISHU_API_BASE}/drive/explorer/v2/root_folder/meta"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        data = self._check_resp(resp.json(), "获取根目录")
        token = data["data"]["token"]
        return token

    def list_files(
        self,
        folder_token: str,
        page_size: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        列出指定文件夹内的所有文件（自动处理分页）。

        Args:
            folder_token: 目标文件夹的 token
            page_size:    每页数量，最大 200

        Returns:
            文件列表，每项包含：
              - token: str        文件/文件夹 token
              - name: str         名称
              - type: str         类型（folder/sheet/bitable/doc/docx/file）
              - parent_token: str 父文件夹 token
              - url: str          网页链接（如有）
              - modified_time: str 最后修改时间戳（秒）
        """
        url = f"{FEISHU_API_BASE}/drive/v1/files"
        all_files: List[Dict] = []
        page_token: Optional[str] = None

        # nod... 是个人空间的节点 token，/drive/v1/files 不接受，
        # 不传 folder_token（或传空串）才会返回"我的空间"根目录列表。
        effective_token = "" if folder_token.startswith("nod") else folder_token

        while True:
            # 注意：/drive/v1/files 仅支持 folder_token / page_size / page_token 三个参数，
            # 传其他字段（如 order_by / direction）会导致 400 params error。
            params: Dict[str, Any] = {
                "folder_token": effective_token,
                "page_size": page_size,
            }
            if page_token:
                params["page_token"] = page_token

            resp = requests.get(url, params=params, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            data = self._check_resp(resp.json(), "列出文件")

            files = data.get("data", {}).get("files", [])
            all_files.extend(files)

            has_more = data.get("data", {}).get("has_more", False)
            page_token = data.get("data", {}).get("next_page_token")
            if not has_more or not page_token:
                break

        return all_files

    def create_folder(self, name: str, parent_folder_token: str) -> Dict[str, str]:
        """
        在指定目录下创建文件夹。

        Args:
            name:                文件夹名称
            parent_folder_token: 父目录 token

        Returns:
            {"token": ..., "name": ...}
        """
        url = f"{FEISHU_API_BASE}/drive/v1/files/create_folder"
        body = {"name": name, "folder_token": parent_folder_token}
        resp = requests.post(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = self._check_resp(resp.json(), f"创建文件夹「{name}」")
        return {
            "token": data["data"]["token"],
            "name": name,
        }

    # ──────────────────────────────────────────
    # 文件操作
    # ──────────────────────────────────────────

    def move_file(
        self,
        file_token: str,
        file_type: str,
        target_folder_token: str,
    ) -> None:
        """
        将文件/文件夹移动到目标目录。

        Args:
            file_token:          要移动的文件 token
            file_type:           文件类型（folder/sheet/bitable/doc/docx/file）
            target_folder_token: 目标文件夹 token
        """
        url = f"{FEISHU_API_BASE}/drive/v1/files/{file_token}/move"
        body = {"type": file_type, "folder_token": target_folder_token}
        resp = requests.post(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        self._check_resp(resp.json(), "移动文件")

    def rename_file(
        self,
        file_token: str,
        file_type: str,
        new_name: str,
    ) -> None:
        """
        重命名文件或文件夹。

        Args:
            file_token: 文件 token
            file_type:  文件类型
            new_name:   新名称
        """
        url = f"{FEISHU_API_BASE}/drive/v1/files/{file_token}"
        body = {"name": new_name, "type": file_type}
        resp = requests.patch(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        self._check_resp(resp.json(), f"重命名 → 「{new_name}」")

    def delete_file(self, file_token: str, file_type: str) -> None:
        """
        永久删除文件或文件夹（不可恢复）。

        Args:
            file_token: 文件 token
            file_type:  文件类型
        """
        url = f"{FEISHU_API_BASE}/drive/v1/files/{file_token}"
        params = {"type": file_type}
        resp = requests.delete(url, params=params, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        self._check_resp(resp.json(), "删除文件")

    # ──────────────────────────────────────────
    # URL 生成（本地拼接，无需 API）
    # ──────────────────────────────────────────

    def get_file_url(self, file_token: str, file_type: str) -> str:
        """
        根据 token 和类型拼接飞书网页链接。

        Args:
            file_token: 文件 token
            file_type:  文件类型

        Returns:
            可直接在浏览器打开的 URL；若 domain 未配置则返回提示信息
        """
        if not self.domain:
            return f"（未配置 FEISHU_DOMAIN，token={file_token}，type={file_type}）"
        pattern = FILE_URL_PATTERNS.get(file_type, FILE_URL_PATTERNS[FILE_TYPE_FILE])
        return pattern.format(domain=self.domain, token=file_token)

    # ──────────────────────────────────────────
    # 工具方法
    # ──────────────────────────────────────────

    @staticmethod
    def icon(file_type: str) -> str:
        """返回文件类型对应的显示图标。"""
        return FILE_TYPE_ICONS.get(file_type, "📄")

    @staticmethod
    def format_modified_time(ts: Any) -> str:
        """将 Unix 时间戳（秒或毫秒）格式化为 YYYY-MM-DD。"""
        if not ts:
            return "-"
        try:
            ts_int = int(ts)
            # 飞书有些接口返回毫秒
            if ts_int > 1e12:
                ts_int = ts_int // 1000
            import datetime
            return datetime.datetime.fromtimestamp(ts_int).strftime("%Y-%m-%d")
        except Exception:
            return str(ts)
