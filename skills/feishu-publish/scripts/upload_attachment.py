#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书文档附件上传工具 — 供 OpenClaw 等自动化流程调用

用法（三种方式均可）：

  # 方式 1：直接传 document_id（docx 的 obj_token）
  python upload_attachment.py --doc_id <document_id> --file /path/to/paper.pdf

  # 方式 2：传 Wiki 节点 URL 中的 node_token（自动解析为 doc_id）
  python upload_attachment.py --wiki_token <wiki_node_token> --file /path/to/paper.pdf

  # 方式 3：传完整 Wiki URL（自动提取 token）
  python upload_attachment.py --wiki_url https://xxx.feishu.cn/wiki/N5ZtwQB7... --file /path/to/paper.pdf

可选参数：
  --env     .env 文件路径（默认：脚本同目录下的 .env）
  --mime    文件 MIME 类型（默认自动检测，PDF 为 application/pdf）

成功时输出 JSON：{"status": "ok", "doc_id": "...", "block_id": "...", "file_token": "..."}
失败时以非 0 退出码退出，并将错误信息写入 stderr。
"""

import argparse
import json
import mimetypes
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

API_BASE = "https://open.feishu.cn/open-apis"


# ── 凭证与 Token ─────────────────────────────────────────────────────────────

def load_credentials(env_path: str = "") -> tuple[str, str]:
    """从 .env 加载 FEISHU_APP_ID / FEISHU_APP_SECRET。"""
    path = Path(env_path) if env_path else Path(__file__).parent / ".env"
    load_dotenv(path)
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        raise RuntimeError("未找到 FEISHU_APP_ID / FEISHU_APP_SECRET，请检查 .env 文件")
    return app_id, app_secret


def get_tenant_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        f"{API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 token 失败: {data}")
    return data["tenant_access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def json_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _check(data: dict, action: str) -> dict:
    if data.get("code") != 0:
        raise RuntimeError(f"{action} 失败 (code={data['code']}): {data.get('msg')}")
    return data


# ── Wiki → document_id 解析 ──────────────────────────────────────────────────

def wiki_url_to_token(url: str) -> str:
    """从完整 Wiki URL 中提取 node_token。"""
    m = re.search(r"/wiki/([A-Za-z0-9]+)", url)
    if not m:
        raise ValueError(f"无法从 URL 中提取 wiki node_token: {url}")
    return m.group(1)


def resolve_wiki_token(token: str, node_token: str) -> str:
    """通过 wiki node_token 查询对应文档的 document_id（obj_token）。"""
    resp = requests.get(
        f"{API_BASE}/wiki/v2/spaces/get_node",
        params={"token": node_token, "obj_type": "wiki"},
        headers=json_headers(token),
        timeout=10,
    )
    resp.raise_for_status()
    data = _check(resp.json(), "获取 Wiki 节点")
    node = data["data"]["node"]
    _log(f"Wiki 节点: {node.get('title', '(无标题)')}  →  obj_token={node['obj_token']}")
    return node["obj_token"]


# ── 文档根 Block 子节点数量 ──────────────────────────────────────────────────

def get_root_children_count(token: str, document_id: str) -> int:
    """获取根 Block 当前的子节点数量，用于计算追加位置。"""
    resp = requests.get(
        f"{API_BASE}/docx/v1/documents/{document_id}/blocks/{document_id}",
        headers=json_headers(token),
        timeout=10,
    )
    resp.raise_for_status()
    data = _check(resp.json(), "获取根 Block")
    return len(data["data"]["block"].get("children", []))


# ── 三步上传核心逻辑 ─────────────────────────────────────────────────────────

def create_empty_file_block(token: str, document_id: str, file_name: str) -> str:
    """
    Step 1：在文档末尾创建一个空文件 Block，返回内层文件 Block 的 block_id。

    飞书 API 会在 block_type=23（文件）外自动套一个 block_type=33（视图），
    内层 block_id 才是后续 replace_file 的目标。
    """
    index = get_root_children_count(token, document_id)
    resp = requests.post(
        f"{API_BASE}/docx/v1/documents/{document_id}/blocks/{document_id}/children",
        headers=json_headers(token),
        json={
            "index": index,
            "children": [
                {
                    "block_type": 23,
                    # fileToken 用占位值，后续 replace_file 会覆盖
                    "file": {"fileToken": "placeholder", "fileName": file_name},
                }
            ],
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = _check(resp.json(), "创建空文件 Block")
    outer = data["data"]["children"][0]
    inner_block_id: str = outer["children"][0]
    _log(f"空文件 Block 已创建，inner_block_id={inner_block_id}")
    return inner_block_id


def upload_media(token: str, inner_block_id: str, file_path: Path, mime: str) -> str:
    """
    Step 2：以内层文件 Block 的 block_id 为 parent_node 上传文件，返回 file_token。

    关键：parent_node 必须是内层 block_id（doxcn... 格式），
          不能用 document_id，否则 replace_file 会报 1770013 relation mismatch。
    """
    file_size = file_path.stat().st_size
    _log(f"上传文件: {file_path.name}  ({file_size / 1024 / 1024:.2f} MB)")
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{API_BASE}/drive/v1/medias/upload_all",
            headers=auth_headers(token),
            data={
                "file_name":   file_path.name,
                "parent_type": "docx_file",
                "parent_node": inner_block_id,
                "size":        str(file_size),
            },
            files={"file": (file_path.name, f, mime)},
            timeout=120,
        )
    resp.raise_for_status()
    data = _check(resp.json(), "上传素材")
    file_token: str = data["data"]["file_token"]
    _log(f"素材上传成功，file_token={file_token}")
    return file_token


def replace_file(token: str, document_id: str, inner_block_id: str, file_token: str) -> None:
    """
    Step 3：patch replace_file，将 file_token 正式写入 Block，文件变为可访问状态。
    """
    resp = requests.patch(
        f"{API_BASE}/docx/v1/documents/{document_id}/blocks/{inner_block_id}",
        headers=json_headers(token),
        json={"replace_file": {"token": file_token}},
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"replace_file HTTP {resp.status_code}: {resp.text}")
    data = _check(resp.json(), "replace_file")
    file_info = data["data"]["block"].get("file", {})
    _log(f"文件关联成功：name={file_info.get('name')}")


# ── 日志 & 主入口 ─────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"  {msg}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="将本地文件作为附件上传到飞书文档（供 OpenClaw 等自动化工具调用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--doc_id",     metavar="DOC_ID",
                        help="飞书文档的 document_id（obj_token）")
    target.add_argument("--wiki_token", metavar="NODE_TOKEN",
                        help="Wiki 页面 URL 中 /wiki/ 后面的 token")
    target.add_argument("--wiki_url",   metavar="URL",
                        help="Wiki 页面完整 URL，自动提取 token")

    p.add_argument("--file", required=True, metavar="FILE_PATH",
                   help="要上传的本地文件路径")
    p.add_argument("--env",  default="",   metavar="ENV_FILE",
                   help=".env 文件路径（默认：脚本同目录下的 .env）")
    p.add_argument("--mime", default="",   metavar="MIME_TYPE",
                   help="文件 MIME 类型（留空自动检测）")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    file_path = Path(args.file).expanduser().resolve()
    if not file_path.exists():
        print(json.dumps({"status": "error", "message": f"文件不存在: {file_path}"}))
        sys.exit(1)

    # 自动检测 MIME
    mime = args.mime or (mimetypes.guess_type(str(file_path))[0] or "application/octet-stream")

    try:
        app_id, app_secret = load_credentials(args.env)
        tok = get_tenant_token(app_id, app_secret)
        _log("tenant_access_token 获取成功")

        # 解析目标文档 ID
        if args.doc_id:
            doc_id = args.doc_id
        elif args.wiki_token:
            doc_id = resolve_wiki_token(tok, args.wiki_token)
        else:  # wiki_url
            node_token = wiki_url_to_token(args.wiki_url)
            doc_id = resolve_wiki_token(tok, node_token)
        _log(f"目标文档 document_id={doc_id}")

        # 三步核心流程
        inner_id  = create_empty_file_block(tok, doc_id, file_path.name)
        file_token = upload_media(tok, inner_id, file_path, mime)
        replace_file(tok, doc_id, inner_id, file_token)

        # 成功：输出 JSON 到 stdout（OpenClaw 可解析）
        result = {
            "status":     "ok",
            "doc_id":     doc_id,
            "block_id":   inner_id,
            "file_token": file_token,
            "file_name":  file_path.name,
        }
        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
