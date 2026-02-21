# -*- coding: utf-8 -*-
"""
飞书多维表格构建器
支持：在指定文件夹创建多维表格、新建数据表、管理字段、批量写入记录。

API 参考：
  - 创建多维表格:  POST /open-apis/bitable/v1/apps
  - 新增数据表:    POST /open-apis/bitable/v1/apps/{app_token}/tables
  - 列出/新增/更新字段: /open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields
  - 批量新增记录:  POST /open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create
"""

import os
import time
import requests
from typing import List, Dict, Optional, Any


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
TOKEN_URL = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"

# 字段类型常量（type 值）
FIELD_TYPE_TEXT        = 1   # 多行文本
FIELD_TYPE_NUMBER      = 2   # 数字；property.formatter 合法值: "0" "0.0" "0.00" "0.000" "0.0000" "0%" "0.00%"
FIELD_TYPE_SELECT      = 3   # 单选
FIELD_TYPE_MULTISELECT = 4   # 多选
FIELD_TYPE_DATE        = 5   # 日期
FIELD_TYPE_CHECKBOX    = 7   # 复选框
FIELD_TYPE_URL         = 15  # 超链接
FIELD_TYPE_AUTO_NO     = 1005  # 自动编号（系统字段，不可新增，仅供参考）

# 单次批量写入记录上限
BATCH_CREATE_LIMIT = 500


class FeishuBitableBuilder:
    """
    飞书多维表格构建器：从零开始在指定文件夹创建多维表格并写入数据。

    典型用法：
        builder = FeishuBitableBuilder()  # 从环境变量读取 app_id / app_secret

        # 1. 在指定文件夹下创建多维表格
        app_token = builder.create_bitable("实验记录_2026", folder_token="Defhfgi6ulrigHdvFuYc86lbnE5")

        # 2. 在多维表格内新建数据表
        table_id = builder.create_table(app_token, "训练结果")

        # 3. 配置字段（改默认主字段名 + 新增自定义字段）
        builder.setup_fields(app_token, table_id, [
            {"field_name": "实验名称", "type": FIELD_TYPE_TEXT},         # 主字段改名
            {"field_name": "Acc",      "type": FIELD_TYPE_NUMBER, "property": {"formatter": "0.0000"}},
            {"field_name": "状态",     "type": FIELD_TYPE_SELECT,
             "property": {"options": [{"name": "进行中"}, {"name": "完成"}]}},
        ])

        # 4. 写入数据
        builder.add_records(app_token, table_id, [
            {"实验名称": "exp_001", "Acc": 0.956, "状态": "完成"},
        ])
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
    # 内部：Token 管理
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
            raise RuntimeError(f"{action} 失败 (code={data.get('code')}): {data.get('msg')} | 详情: {data}")
        return data

    # ──────────────────────────────────────────
    # 多维表格（Bitable App）
    # ──────────────────────────────────────────

    def create_bitable(self, name: str, folder_token: str = "") -> str:
        """
        在指定文件夹下创建一个多维表格（Bitable App）。

        Args:
            name:         多维表格的名称
            folder_token: 目标文件夹的 token；留空则创建到机器人的默认位置

        Returns:
            新建多维表格的 app_token

        说明：创建 Bitable 时会自动生成一个默认数据表（default_table_id），
              如果不需要额外数据表，可直接用 default_table_id 操作字段和记录。
        """
        url = f"{FEISHU_API_BASE}/bitable/v1/apps"
        body: Dict[str, Any] = {"name": name}
        if folder_token:
            body["folder_token"] = folder_token
        resp = requests.post(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = self._check_resp(resp.json(), f"创建多维表格「{name}」")
        app_info = data["data"]["app"]
        app_token = app_info["app_token"]
        app_url = app_info.get("url", "")
        default_table_id = app_info.get("default_table_id", "")
        print(f"[✓] 多维表格已创建: 「{name}」")
        print(f"    app_token        : {app_token}")
        print(f"    default_table_id : {default_table_id}")
        print(f"    url              : {app_url}")
        return app_token

    # ──────────────────────────────────────────
    # 数据表（Table）
    # ──────────────────────────────────────────

    def create_table(
        self,
        app_token: str,
        table_name: str,
        default_view_name: str = "默认视图",
    ) -> str:
        """
        在指定多维表格内新增一个数据表。

        Args:
            app_token:         多维表格的 app_token
            table_name:        数据表名称
            default_view_name: 默认视图名称

        Returns:
            新建数据表的 table_id

        注意：飞书 API 要求 fields 数组不能为空，此处传入占位主字段，
              后续通过 setup_fields 改名即可。
        """
        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{app_token}/tables"
        body = {
            "table": {
                "name": table_name,
                "default_view_name": default_view_name,
                # fields 为必填项，至少需要一个主字段，后续通过 setup_fields 更新名称
                "fields": [{"field_name": "标题", "type": FIELD_TYPE_TEXT}],
            }
        }
        resp = requests.post(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = self._check_resp(resp.json(), f"新增数据表「{table_name}」")
        table_id = data["data"]["table_id"]
        print(f"[✓] 数据表已创建: 「{table_name}」  table_id={table_id}")
        return table_id

    # ──────────────────────────────────────────
    # 字段（Field）
    # ──────────────────────────────────────────

    def get_fields(self, app_token: str, table_id: str) -> List[Dict]:
        """
        列出数据表的所有字段。

        Returns:
            字段列表，每项含 field_id、field_name、type 等
        """
        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        data = self._check_resp(resp.json(), "列出字段")
        return data.get("data", {}).get("items", [])

    def update_field(
        self,
        app_token: str,
        table_id: str,
        field_id: str,
        field_name: str,
        field_type: int = FIELD_TYPE_TEXT,
        property: Optional[Dict] = None,
    ) -> dict:
        """
        更新已有字段（常用于改默认主字段的名称）。

        Args:
            field_id:   要更新的字段 ID
            field_name: 新字段名
            field_type: 字段类型（默认 1=多行文本）
            property:   字段额外属性，如 number 的 formatter

        Returns:
            API 响应 data 字段
        """
        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}"
        body: Dict[str, Any] = {"field_name": field_name, "type": field_type}
        if property:
            body["property"] = property
        resp = requests.put(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = self._check_resp(resp.json(), f"更新字段「{field_name}」")
        print(f"[✓] 字段已更新: 「{field_name}」(type={field_type})")
        return data.get("data", {})

    def add_field(
        self,
        app_token: str,
        table_id: str,
        field_name: str,
        field_type: int,
        property: Optional[Dict] = None,
    ) -> str:
        """
        在数据表中新增一个字段。

        Args:
            field_name: 字段名
            field_type: 字段类型（使用模块顶部的 FIELD_TYPE_* 常量）
            property:   字段额外属性，例如
                        - 数字: {"formatter": "0.0000"}
                        - 单选: {"options": [{"name": "A"}, {"name": "B"}]}

        Returns:
            新字段的 field_id
        """
        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        body: Dict[str, Any] = {"field_name": field_name, "type": field_type}
        if property:
            body["property"] = property
        resp = requests.post(url, json=body, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = self._check_resp(resp.json(), f"新增字段「{field_name}」")
        field_id = data["data"]["field"]["field_id"]
        print(f"[✓] 字段已新增: 「{field_name}」(type={field_type})  field_id={field_id}")
        return field_id

    def setup_fields(
        self,
        app_token: str,
        table_id: str,
        fields_config: List[Dict],
    ) -> None:
        """
        一次完成字段配置：第一项自动用于更新默认主字段，后续项逐个新增。
        每次操作之间自动 sleep 0.2s，避免并发写冲突（错误码 1254291）。

        Args:
            fields_config: 字段配置列表，每项为 dict，支持以下键：
                - field_name (必填): 字段名
                - type       (必填): 字段类型
                - property   (可选): 字段属性

        示例::
            builder.setup_fields(app_token, table_id, [
                {"field_name": "实验名称",  "type": FIELD_TYPE_TEXT},
                {"field_name": "Acc",       "type": FIELD_TYPE_NUMBER, "property": {"formatter": "0.0000"}},
                {"field_name": "状态",      "type": FIELD_TYPE_SELECT,
                 "property": {"options": [{"name": "进行中"}, {"name": "已完成"}]}},
            ])
        """
        if not fields_config:
            return

        # 第一个字段：更新默认主字段（每张新表都有一个默认主字段）
        primary_cfg = fields_config[0]
        existing = self.get_fields(app_token, table_id)
        if not existing:
            raise RuntimeError("获取默认字段失败，无法设置主字段名")
        primary_field_id = existing[0]["field_id"]
        time.sleep(0.2)
        self.update_field(
            app_token, table_id, primary_field_id,
            field_name=primary_cfg["field_name"],
            field_type=primary_cfg.get("type", FIELD_TYPE_TEXT),
            property=primary_cfg.get("property"),
        )

        # 后续字段：逐个新增
        for cfg in fields_config[1:]:
            time.sleep(0.2)
            self.add_field(
                app_token, table_id,
                field_name=cfg["field_name"],
                field_type=cfg["type"],
                property=cfg.get("property"),
            )

    # ──────────────────────────────────────────
    # 记录（Record）
    # ──────────────────────────────────────────

    def add_records(
        self,
        app_token: str,
        table_id: str,
        records: List[Dict[str, Any]],
    ) -> dict:
        """
        向数据表批量新增记录（单次最多 500 条，超出自动分批）。

        Args:
            records: 记录列表，每条为 {字段名: 值} 的映射。
                     数值类型字段直接传 int/float 即可，无需手动转字符串。

        Returns:
            最后一批的 API 响应
        """
        if not records:
            return {}
        url = f"{FEISHU_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
        result: dict = {}
        total = len(records)
        for i in range(0, total, BATCH_CREATE_LIMIT):
            chunk = records[i: i + BATCH_CREATE_LIMIT]
            body = {
                "records": [{"fields": r} for r in chunk]
            }
            resp = requests.post(url, json=body, headers=self._headers(), timeout=20)
            resp.raise_for_status()
            result = self._check_resp(resp.json(), "批量新增记录")
            added = len(result.get("data", {}).get("records", []))
            print(f"[✓] 写入记录 {i + 1}~{min(i + BATCH_CREATE_LIMIT, total)} / {total}  (本批实际入库: {added} 条)")
            if i + BATCH_CREATE_LIMIT < total:
                time.sleep(0.2)
        return result

    # ──────────────────────────────────────────
    # 一键建表（组合步骤）
    # ──────────────────────────────────────────

    def build(
        self,
        bitable_name: str,
        table_name: str,
        fields_config: List[Dict],
        records: List[Dict[str, Any]],
        folder_token: str = "",
    ) -> Dict[str, str]:
        """
        一步完成：创建多维表格 → 建数据表 → 配置字段 → 写入记录。

        Args:
            bitable_name:  多维表格名称
            table_name:    数据表名称
            fields_config: 字段配置（同 setup_fields）
            records:       数据记录列表（同 add_records）
            folder_token:  目标文件夹 token

        Returns:
            {"app_token": ..., "table_id": ...}
        """
        print(f"\n{'=' * 50}")
        print(f"  开始构建: 「{bitable_name}」 > 「{table_name}」")
        print(f"{'=' * 50}")

        app_token = self.create_bitable(bitable_name, folder_token=folder_token)
        time.sleep(0.5)  # 等待服务端创建完成

        table_id = self.create_table(app_token, table_name)
        time.sleep(0.5)

        if fields_config:
            print("\n── 配置字段 ──")
            self.setup_fields(app_token, table_id, fields_config)

        if records:
            print(f"\n── 写入 {len(records)} 条记录 ──")
            self.add_records(app_token, table_id, records)

        print(f"\n{'=' * 50}")
        print(f"  全部完成！")
        print(f"  app_token : {app_token}")
        print(f"  table_id  : {table_id}")
        print(f"{'=' * 50}\n")

        return {"app_token": app_token, "table_id": table_id}
