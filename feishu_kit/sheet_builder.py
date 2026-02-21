# -*- coding: utf-8 -*-
"""
飞书电子表格构建器
支持：在指定文件夹创建电子表格、列出/重命名工作表、写入数据。

API 参考：
  - 创建表格:      POST /open-apis/sheets/v3/spreadsheets
  - 列出工作表:    GET  /open-apis/sheets/v3/spreadsheets/{token}/sheets
  - 重命名工作表:  PUT  /open-apis/sheets/v3/spreadsheets/{token}/sheets/batch_update
  - 写入数据:      PUT  /open-apis/sheets/v2/spreadsheets/{token}/values
  - 追加行:        POST /open-apis/sheets/v2/spreadsheets/{token}/values_append
"""

import os
import time
import requests
from typing import List, Dict, Optional, Any


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
TOKEN_URL = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"

# 单次写入最多 5000 行
WRITE_ROW_LIMIT = 5000


class FeishuSheetBuilder:
    """
    飞书电子表格构建器：从零开始在指定文件夹创建电子表格并写入数据。

    典型用法::

        builder = FeishuSheetBuilder()  # 从环境变量读取 app_id / app_secret

        # 一键完成：创建 → 重命名工作表 → 写入表头+数据
        result = builder.build(
            title="实验结果_2026",
            sheet_title="训练记录",
            headers=["实验名称", "Accuracy", "Loss", "状态"],
            rows=[
                ["exp_001", 0.956, 0.231, "完成"],
                ["exp_002", 0.961, 0.218, "进行中"],
            ],
            folder_token="Defhfgi6ulrigHdvFuYc86lbnE5",
        )
        # result = {"spreadsheet_token": "...", "sheet_id": "...", "url": "..."}
    """

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
    ):
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "")
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
                f"{action} 失败 (code={data.get('code')}): {data.get('msg')} | 详情: {data}"
            )
        return data

    # ──────────────────────────────────────────
    # 电子表格
    # ──────────────────────────────────────────

    def create_spreadsheet(self, title: str, folder_token: str = "") -> str:
        """
        在指定文件夹下创建一个电子表格。

        Args:
            title:        表格标题（文件名）
            folder_token: 目标文件夹 token；留空则创建到根目录

        Returns:
            新建表格的 spreadsheet_token
        """
        url = f"{FEISHU_API_BASE}/sheets/v3/spreadsheets"
        body: Dict[str, Any] = {"title": title}
        if folder_token:
            body["folder_token"] = folder_token
        resp = requests.post(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = self._check_resp(resp.json(), f"创建电子表格「{title}」")
        ss = data["data"]["spreadsheet"]
        spreadsheet_token = ss["spreadsheet_token"]
        sheet_url = ss.get("url", "")
        print(f"[✓] 电子表格已创建: 「{title}」")
        print(f"    spreadsheet_token : {spreadsheet_token}")
        print(f"    url               : {sheet_url}")
        return spreadsheet_token

    # ──────────────────────────────────────────
    # 工作表（Sheet）
    # ──────────────────────────────────────────

    def get_sheets(self, spreadsheet_token: str) -> List[Dict]:
        """
        列出电子表格内的所有工作表。
        使用 v2/metainfo 接口，返回 sheets 数组。

        Returns:
            工作表列表，每项含 sheetId、title、index 等
        """
        url = f"{FEISHU_API_BASE}/sheets/v2/spreadsheets/{spreadsheet_token}/metainfo"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        data = self._check_resp(resp.json(), "获取表格元数据")
        return data.get("data", {}).get("sheets", [])

    def rename_sheet(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        new_title: str,
    ) -> None:
        """
        重命名指定工作表。

        Args:
            spreadsheet_token: 表格 token
            sheet_id:          工作表 ID
            new_title:         新名称
        """
        url = f"{FEISHU_API_BASE}/sheet/v2/spreadsheets/{spreadsheet_token}/sheets_batch_update"
        body = {
            "requests": [
                {
                    "updateSheet": {
                        "properties": {
                            "sheetId": sheet_id,
                            "title": new_title,
                        }
                    }
                }
            ]
        }
        resp = requests.post(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        self._check_resp(resp.json(), f"重命名工作表 → 「{new_title}」")
        print(f"[✓] 工作表已重命名: 「{new_title}」  sheet_id={sheet_id}")

    # ──────────────────────────────────────────
    # 数据写入
    # ──────────────────────────────────────────

    def write_data(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        data: List[List[Any]],
        start_row: int = 1,
        start_col: str = "A",
    ) -> dict:
        """
        从指定单元格开始写入二维数据（覆盖模式）。

        Args:
            spreadsheet_token: 表格 token
            sheet_id:          工作表 ID
            data:              二维数组，第一行通常为表头
            start_row:         起始行号（1-indexed）
            start_col:         起始列字母，默认 "A"

        Returns:
            API 响应 JSON
        """
        if not data:
            return {}

        # 计算结束单元格：列数转为字母列号
        num_cols = max(len(row) for row in data)
        end_col = self._col_index_to_letter(
            self._letter_to_col_index(start_col) + num_cols - 1
        )
        end_row = start_row + len(data) - 1
        range_spec = f"{sheet_id}!{start_col}{start_row}:{end_col}{end_row}"

        url = f"{FEISHU_API_BASE}/sheets/v2/spreadsheets/{spreadsheet_token}/values"
        body = {"valueRange": {"range": range_spec, "values": data}}
        resp = requests.put(url, json=body, headers=self._headers(), timeout=20)
        resp.raise_for_status()
        result = self._check_resp(resp.json(), f"写入数据到 {range_spec}")
        print(f"[✓] 已写入 {len(data)} 行 × {num_cols} 列  →  范围: {range_spec}")
        return result

    def append_rows(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        rows: List[List[Any]],
    ) -> dict:
        """
        在工作表现有数据末尾追加行（不覆盖已有内容）。

        Args:
            spreadsheet_token: 表格 token
            sheet_id:          工作表 ID
            rows:              要追加的行（二维数组）

        Returns:
            API 响应 JSON
        """
        if not rows:
            return {}
        url = f"{FEISHU_API_BASE}/sheets/v2/spreadsheets/{spreadsheet_token}/values_append"
        body = {"valueRange": {"range": f"{sheet_id}!A1", "values": rows}}
        resp = requests.post(url, json=body, headers=self._headers(), timeout=20)
        resp.raise_for_status()
        result = self._check_resp(resp.json(), "追加行")
        print(f"[✓] 已追加 {len(rows)} 行")
        return result

    # ──────────────────────────────────────────
    # 一键构建
    # ──────────────────────────────────────────

    def build(
        self,
        title: str,
        sheet_title: str,
        headers: List[str],
        rows: List[List[Any]],
        folder_token: str = "",
    ) -> Dict[str, str]:
        """
        一步完成：创建表格 → 重命名默认工作表 → 写入表头 + 数据。

        Args:
            title:        表格文件名
            sheet_title:  工作表标签名
            headers:      表头列表，如 ["实验名称", "Acc", "状态"]
            rows:         数据行（不含表头），如 [["exp_001", 0.95, "完成"]]
            folder_token: 目标文件夹 token

        Returns:
            {"spreadsheet_token": ..., "sheet_id": ..., "url": ...}
        """
        print(f"\n{'=' * 50}")
        print(f"  开始构建: 「{title}」 > 「{sheet_title}」")
        print(f"{'=' * 50}")

        # 第 1 步：创建表格
        spreadsheet_token = self.create_spreadsheet(title, folder_token=folder_token)
        time.sleep(0.5)

        # 第 2 步：获取默认工作表（新建表格自带一个）
        sheets = self.get_sheets(spreadsheet_token)
        if not sheets:
            raise RuntimeError("未能获取到工作表列表")
        default_sheet = sheets[0]
        sheet_id = default_sheet["sheetId"]
        print(f"[✓] 默认工作表: sheet_id={sheet_id}")
        time.sleep(0.3)

        # 第 3 步：重命名工作表
        self.rename_sheet(spreadsheet_token, sheet_id, sheet_title)
        time.sleep(0.3)

        # 第 4 步：写入表头 + 数据
        all_data = [headers] + rows
        print(f"\n── 写入数据（{len(rows)} 行 × {len(headers)} 列）──")
        self.write_data(spreadsheet_token, sheet_id, all_data)

        # 拼出访问 URL
        sheet_url = f"https://open.feishu.cn/open-apis/drive/v1/files/{spreadsheet_token}"

        print(f"\n{'=' * 50}")
        print(f"  全部完成！")
        print(f"  spreadsheet_token : {spreadsheet_token}")
        print(f"  sheet_id          : {sheet_id}")
        print(f"{'=' * 50}\n")

        return {
            "spreadsheet_token": spreadsheet_token,
            "sheet_id": sheet_id,
        }

    # ──────────────────────────────────────────
    # 工具函数：列号转换
    # ──────────────────────────────────────────

    @staticmethod
    def _letter_to_col_index(col: str) -> int:
        """将列字母转为 1-indexed 整数，如 "A"→1, "Z"→26, "AA"→27。"""
        result = 0
        for ch in col.upper():
            result = result * 26 + (ord(ch) - ord("A") + 1)
        return result

    @staticmethod
    def _col_index_to_letter(n: int) -> str:
        """将 1-indexed 整数转为列字母，如 1→"A", 26→"Z", 27→"AA"。"""
        result = ""
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            result = chr(ord("A") + remainder) + result
        return result
