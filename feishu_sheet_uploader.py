# -*- coding: utf-8 -*-
"""
飞书电子表格上传小组件
可集成到实验脚本中，将数据自动写入飞书表格。
依赖：requests
"""

import os
import time
import requests
from typing import List, Optional, Any


# 飞书 API 基础 URL
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
TOKEN_URL = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"


class FeishuSheetUploader:
    """
    飞书电子表格上传器。
    支持：获取 token、向指定范围写入、在表头后追加行。
    """

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        spreadsheet_token: Optional[str] = None,
        sheet_id: Optional[str] = None,
    ):
        """
        Args:
            app_id: 飞书应用 App ID，也可通过环境变量 FEISHU_APP_ID 设置
            app_secret: 飞书应用 App Secret，也可通过环境变量 FEISHU_APP_SECRET 设置
            spreadsheet_token: 表格 token（URL 中 sheets/ 后面、? 前面的部分），也可用 FEISHU_SPREADSHEET_TOKEN
            sheet_id: 工作表 ID（URL 中 sheet= 后面的值），也可用 FEISHU_SHEET_ID
        """
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "")
        self.spreadsheet_token = spreadsheet_token or os.environ.get(
            "FEISHU_SPREADSHEET_TOKEN", ""
        )
        self.sheet_id = sheet_id or os.environ.get("FEISHU_SHEET_ID", "")
        self._token: Optional[str] = None
        self._token_expire_at: float = 0

    def _get_token(self) -> str:
        """获取并缓存 tenant_access_token，过期前自动复用。"""
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

    def write_range(self, range_spec: str, values: List[List[Any]]) -> dict:
        """
        向指定范围写入数据（会覆盖该范围内原有数据）。

        Args:
            range_spec: 范围，格式为 "{sheet_id}!A1:C10"，例如 "0b12!A1:B5"
            values: 二维数组，如 [["列1","列2"], ["v1","v2"]]

        Returns:
            API 响应 JSON
        """
        url = f"{FEISHU_API_BASE}/sheets/v2/spreadsheets/{self.spreadsheet_token}/values"
        body = {"valueRange": {"range": range_spec, "values": values}}
        resp = requests.put(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    def append_rows(
        self,
        rows: List[List[Any]],
        range_spec: Optional[str] = None,
    ) -> dict:
        """
        在指定范围之前插入行（用于在表头后追加数据）。
        若未传 range_spec，则使用初始化时的 sheet_id，从 A1 开始作为插入参考位置。

        Args:
            rows: 要追加的行，二维数组
            range_spec: 可选，如 "0b12!A1" 表示在该范围前插入；不传则用 sheet_id!A1

        Returns:
            API 响应 JSON
        """
        if not range_spec:
            if not self.sheet_id:
                raise ValueError("未设置 sheet_id，请传入 range_spec 或在初始化时设置 sheet_id")
            range_spec = f"{self.sheet_id}!A1"
        url = f"{FEISHU_API_BASE}/sheets/v2/spreadsheets/{self.spreadsheet_token}/values_prepend"
        body = {"valueRange": {"range": range_spec, "values": rows}}
        resp = requests.post(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    def upload(
        self,
        rows: List[List[Any]],
        append: bool = True,
        range_spec: Optional[str] = None,
    ) -> dict:
        """
        上传数据：默认追加行；若 append=False 则写入指定范围（需提供 range_spec）。

        Args:
            rows: 二维数组，每行一条记录
            append: True 表示追加，False 表示覆盖写入
            range_spec: 范围，如 "0b12!A1:D100"；append 时可选，覆盖时必填

        Returns:
            API 响应 JSON
        """
        if append:
            return self.append_rows(rows, range_spec=range_spec)
        if not range_spec:
            raise ValueError("覆盖写入时必须提供 range_spec")
        return self.write_range(range_spec, rows)
