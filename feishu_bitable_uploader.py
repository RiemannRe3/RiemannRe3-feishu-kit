# -*- coding: utf-8 -*-
"""
飞书多维表格（Bitable）上传小组件
可集成到实验脚本中，将数据自动追加到飞书多维表格。
依赖：requests
参考：https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/batch_create
"""

import os
import time
import requests
from typing import List, Dict, Optional, Any


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
TOKEN_URL = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
# 单次批量新增最多 500 条，接口 10 QPS
BATCH_CREATE_LIMIT = 500


class FeishuBitableUploader:
    """
    飞书多维表格上传器。
    支持：获取 token、批量新增记录（单次最多 500 条）。
    多维表格 URL 格式：https://xxx.feishu.cn/base/{app_token}?table={table_id}
    """

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
    ):
        """
        Args:
            app_id: 飞书应用 App ID，也可通过环境变量 FEISHU_APP_ID 设置
            app_secret: 飞书应用 App Secret，也可通过环境变量 FEISHU_APP_SECRET 设置
            app_token: 多维表格唯一标识（URL 中 /base/ 后面、?table= 前面的部分），也可用 FEISHU_APP_TOKEN
            table_id: 数据表 ID（URL 中 table= 后面的值），也可用 FEISHU_TABLE_ID
        """
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "")
        self.app_token = app_token or os.environ.get("FEISHU_APP_TOKEN", "")
        self.table_id = table_id or os.environ.get("FEISHU_TABLE_ID", "")
        self._token: Optional[str] = None
        self._token_expire_at: float = 0

    def _get_token(self) -> str:
        """获取并缓存 tenant_access_token。"""
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

    def add_records(self, records: List[Dict[str, Any]]) -> dict:
        """
        向多维表格批量新增记录（单次最多 500 条，超出会自动分批）。

        Args:
            records: 记录列表，每条为字段名到值的映射，例如
                     [{"实验名称": "exp_001", "指标A": 0.95, "指标B": 0.88},
                      {"实验名称": "exp_002", "指标A": 0.96, "指标B": 0.90}]
                     字段名需与多维表格中的列名一致。

        Returns:
            最后一次 batch_create 的 API 响应 JSON（含 records 等）
        """
        if not self.app_token or not self.table_id:
            raise ValueError("未设置 app_token 或 table_id，请通过参数或环境变量 FEISHU_APP_TOKEN、FEISHU_TABLE_ID 设置")

        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/batch_create"
        result = None
        for i in range(0, len(records), BATCH_CREATE_LIMIT):
            chunk = records[i : i + BATCH_CREATE_LIMIT]
            # 将每条记录中的数值自动转为字符串，兼容飞书文本类型字段
            safe_chunk = [
                {"fields": {k: str(v) if isinstance(v, (int, float)) else v for k, v in r.items()}}
                for r in chunk
            ]
            body = {"records": safe_chunk}
            resp = requests.post(url, json=body, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") != 0:
                raise RuntimeError(f"批量新增记录失败: {result}")
            if i + BATCH_CREATE_LIMIT < len(records):
                time.sleep(0.15)  # 简单限速，避免超过 10 QPS
        return result or {}

    def add_record(self, fields: Dict[str, Any]) -> dict:
        """
        新增单条记录。

        Args:
            fields: 字段名到值的映射，如 {"实验名称": "exp_001", "指标A": 0.95}

        Returns:
            API 响应 JSON
        """
        return self.add_records([fields])

    def get_fields(self) -> List[Dict]:
        """
        查询当前数据表的所有字段（列名）信息，用于确认实际字段名。
        返回字段列表，每项包含 field_id、field_name、type 等。
        """
        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"查询字段失败: {data}")
        return data.get("data", {}).get("items", [])

    def print_fields(self) -> None:
        """打印当前数据表所有字段名，方便对照填写 records。"""
        fields = self.get_fields()
        print(f"表格共 {len(fields)} 个字段：")
        for f in fields:
            print(f"  字段名: {f['field_name']!r:30s}  类型: {f.get('type')}")

    def upload(self, records: List[Dict[str, Any]]) -> dict:
        """
        上传多条记录到多维表格（即 add_records 的别名）。

        Args:
            records: 同 add_records

        Returns:
            同 add_records
        """
        return self.add_records(records)
