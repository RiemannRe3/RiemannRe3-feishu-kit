#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将本地 Markdown 文件通过飞书 Import API 转换为飞书云文档（docx）。

比 create_doc_from_md.py 的逐块写入方式更简单，飞书服务端直接解析 MD 格式。
适合不需要精确控制 Block 结构的场景。

流程：
  1. 将 .md 文件上传到云空间，拿到 file_token
  2. 创建异步导入任务（md → docx），拿到 ticket
  3. 轮询任务状态，直到完成，拿到新建文档的 token + url

可选后续：
  4. 将文档移动到指定 Wiki 节点下（需要 wiki:wiki 权限）

用法：
  # 上传到云盘根目录，生成飞书文档
  python import_md_to_doc.py --file /path/to/note.md

  # 上传到指定云盘文件夹
  python import_md_to_doc.py --file note.md --folder_token YuJIf5UtUlDFMsdKNIOc0vJynIe

  # 上传后自动移入 Wiki 节点
  python import_md_to_doc.py --file note.md \\
    --wiki_url "https://xxx.feishu.cn/wiki/<parent_node_token>"

成功输出 JSON（stdout）：
  {"status":"ok","doc_token":"...","url":"...","title":"...","wiki_node_token":"..."}
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

API_BASE = "https://open.feishu.cn/open-apis"

# 轮询参数
_POLL_INTERVAL_INIT = 1.5   # 首次等待秒数
_POLL_INTERVAL_MAX  = 10.0  # 最大等待间隔（指数退避上限）
_POLL_TIMEOUT       = 120   # 最长等待秒数

# job_status 枚举（飞书 import_task 实际返回值）
# 0 = 成功（job_error_msg="success" 且 token 非空）
# 1 = 初始化中（刚创建，尚未开始处理）
# 2 = 处理中
# 3 = 失败
_JOB_STATUS = {0: "成功/排队", 1: "初始化", 2: "处理中", 3: "失败"}


# ── 认证 ─────────────────────────────────────────────────────────────────────

def load_creds(env_path: str = "") -> tuple:
    p = Path(env_path) if env_path else Path(__file__).parent / ".env"
    load_dotenv(p)
    app_id     = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    domain     = os.environ.get("FEISHU_DOMAIN", "feishu.cn")
    if not app_id or not app_secret:
        raise RuntimeError("未找到 FEISHU_APP_ID / FEISHU_APP_SECRET，请检查 .env 文件")
    return app_id, app_secret, domain


def get_token(app_id: str, app_secret: str) -> str:
    r = requests.post(
        f"{API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    r.raise_for_status()
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(f"获取 token 失败: {d}")
    return d["tenant_access_token"]


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def _hj(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _chk(d: dict, action: str) -> dict:
    if d.get("code") != 0:
        raise RuntimeError(f"{action} 失败 (code={d['code']}): {d.get('msg')}")
    return d


# ── Step 0（可选）：获取云盘根目录 token ─────────────────────────────────────

def get_root_folder_token(tok: str) -> str:
    """获取云空间根目录的 folder_token（上传文件时用作 parent_node）。"""
    r = requests.get(
        f"{API_BASE}/drive/explorer/v2/root_folder/meta",
        headers=_hj(tok), timeout=10,
    )
    r.raise_for_status()
    data = _chk(r.json(), "获取根目录")
    token = data["data"]["token"]
    _log(f"云空间根目录 token: {token}")
    return token


# ── Step 1：上传 MD 文件到云空间，拿到 file_token ───────────────────────────

def upload_file(tok: str, file_path: Path, folder_token: str) -> str:
    """
    将本地文件上传到飞书云空间指定目录，返回 file_token。
    使用 drive/v1/files/upload_all（小文件，≤20 MB）。
    """
    file_size = file_path.stat().st_size
    _log(f"上传文件: {file_path.name}  ({file_size / 1024:.1f} KB) → 云空间目录 {folder_token}")

    with open(file_path, "rb") as f:
        r = requests.post(
            f"{API_BASE}/drive/v1/files/upload_all",
            headers=_h(tok),
            data={
                "file_name":   file_path.name,
                "parent_type": "explorer",       # 上传到云空间
                "parent_node": folder_token,
                "size":        str(file_size),
            },
            files={"file": (file_path.name, f, "text/markdown")},
            timeout=60,
        )
    r.raise_for_status()
    data = _chk(r.json(), "上传文件")
    file_token = data["data"]["file_token"]
    _log(f"文件上传成功，file_token={file_token}")
    return file_token


# ── Step 2：创建导入任务（md → docx）───────────────────────────────────────

def create_import_task(
    tok: str,
    file_token: str,
    file_name: str,
    folder_token: str,
) -> str:
    """
    创建异步导入任务，将已上传的 md 文件转为飞书 docx 文档。
    返回 ticket（任务 ID）。

    point.mount_type=1 表示挂载到云空间目录（explorer）
    point.mount_key=folder_token 表示导入后文档所在的目录
    """
    # 文档名去掉后缀
    title = Path(file_name).stem

    payload = {
        "file_extension": "md",
        "file_token":     file_token,
        "type":           "docx",
        "file_name":      title,
        "point": {
            "mount_type": 1,             # 1=云空间目录
            "mount_key":  folder_token,  # 导入后文档所在目录
        },
    }
    _log(f"创建导入任务: {title}")
    r = requests.post(
        f"{API_BASE}/drive/v1/import_tasks",
        headers=_hj(tok), json=payload, timeout=15,
    )
    r.raise_for_status()
    data = _chk(r.json(), "创建导入任务")
    ticket = data["data"]["ticket"]
    _log(f"导入任务已创建，ticket={ticket}")
    return ticket


# ── Step 3：轮询任务状态，拿到 doc_token ────────────────────────────────────

def poll_import_task(tok: str, ticket: str) -> dict:
    """
    轮询导入任务直到完成，返回 {"token": ..., "url": ..., "job_status": ...}。
    使用指数退避策略，避免频繁请求。
    """
    interval   = _POLL_INTERVAL_INIT
    elapsed    = 0.0
    attempt    = 0

    while elapsed < _POLL_TIMEOUT:
        time.sleep(interval)
        elapsed  += interval
        attempt  += 1
        interval  = min(interval * 1.5, _POLL_INTERVAL_MAX)

        r = requests.get(
            f"{API_BASE}/drive/v1/import_tasks/{ticket}",
            headers=_hj(tok), timeout=10,
        )
        r.raise_for_status()
        data = _chk(r.json(), "查询导入任务")
        task = data["data"]["result"]

        status    = task.get("job_status", -1)
        doc_token = task.get("token", "")
        err_msg   = task.get("job_error_msg", "")
        status_text = _JOB_STATUS.get(status, f"未知({status})")
        _log(f"  [{attempt}] status={status}({status_text})  token={doc_token or '—'}  "
             f"msg={err_msg or '—'}  (已等待 {elapsed:.1f}s)")

        # 成功：token 非空且 job_error_msg="success"（实测 job_status=0）
        if doc_token and err_msg == "success":
            url = task.get("url", "")
            _log(f"导入成功！doc_token={doc_token}")
            return {"token": doc_token, "url": url, "job_status": status}

        # 明确失败
        if status == 3 or (err_msg and err_msg != "success" and not doc_token):
            raise RuntimeError(f"导入任务失败 (status={status}): {err_msg}")

    raise TimeoutError(f"导入任务超时（已等待 {_POLL_TIMEOUT}s）")


# ── Step 4（可选）：将文档移入 Wiki ─────────────────────────────────────────

def wiki_url_to_token(url: str) -> str:
    m = re.search(r"/wiki/([A-Za-z0-9]+)", url)
    if not m:
        raise ValueError(f"无法从 URL 提取 wiki token: {url}")
    return m.group(1)


def get_wiki_node_info(tok: str, node_token: str) -> dict:
    r = requests.get(
        f"{API_BASE}/wiki/v2/spaces/get_node",
        params={"token": node_token, "obj_type": "wiki"},
        headers=_hj(tok), timeout=10,
    )
    r.raise_for_status()
    return _chk(r.json(), "获取 Wiki 节点")["data"]["node"]


def move_doc_to_wiki(
    tok: str,
    space_id: str,
    parent_node_token: str,
    doc_token: str,
    doc_type: str = "docx",
) -> str:
    """
    将云空间中的文档移动到 Wiki 指定节点下，返回新建的 wiki_node_token。
    使用异步接口，简单轮询等待完成。
    """
    _log(f"将文档移入 Wiki 节点 {parent_node_token}…")
    r = requests.post(
        f"{API_BASE}/wiki/v2/spaces/{space_id}/nodes/move_docs_to_wiki",
        headers=_hj(tok),
        json={
            "parent_wiki_token": parent_node_token,
            "obj_type":          doc_type,
            "obj_token":         doc_token,
        },
        timeout=15,
    )
    r.raise_for_status()
    data = _chk(r.json(), "移动文档到 Wiki")
    # move_docs_to_wiki 是异步任务，返回 task_id
    task_id = data["data"].get("task_id", "")
    wiki_token = data["data"].get("wiki_token", "")
    _log(f"移动任务已创建  task_id={task_id}  wiki_token={wiki_token}")

    if task_id:
        # 轮询任务直到完成，取回新 wiki node_token
        node_token_from_task = _poll_wiki_task(tok, task_id)
        if node_token_from_task:
            wiki_token = node_token_from_task

    return wiki_token


def _poll_wiki_task(tok: str, task_id: str) -> str:
    """
    轮询 wiki 移动任务直到完成，返回新 wiki node_token。
    move_result[0].node.node_token 即为新节点 token。
    """
    interval = 1.0
    for _ in range(30):
        time.sleep(interval)
        interval = min(interval * 1.5, 5.0)
        r = requests.get(
            f"{API_BASE}/wiki/v2/tasks/{task_id}",
            params={"task_type": "move"},
            headers=_hj(tok), timeout=10,
        )
        if not r.ok:
            break
        task = r.json().get("data", {}).get("task", {})
        results = task.get("move_result", [])
        if results:
            node_token = results[0].get("node", {}).get("node_token", "")
            status_msg = results[0].get("status_msg", "")
            _log(f"Wiki 移动完成  node_token={node_token}  status={status_msg}")
            return node_token
    return ""


# ── 日志 & CLI ────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"  {msg}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="将本地 Markdown 文件通过飞书 Import API 转为飞书云文档",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--file", required=True, metavar="MD_FILE",
                   help="本地 Markdown 文件路径")
    p.add_argument("--folder_token", default="", metavar="TOKEN",
                   help="目标云盘文件夹 token（留空则使用根目录）")

    wiki = p.add_mutually_exclusive_group()
    wiki.add_argument("--wiki_url",   metavar="URL",
                      help="移入该 Wiki 节点 URL 下（可选）")
    wiki.add_argument("--wiki_token", metavar="NODE_TOKEN",
                      help="移入该 Wiki node_token 下（可选）")

    p.add_argument("--env", default="", metavar="ENV_FILE",
                   help=".env 文件路径（默认：脚本同目录 .env）")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    md_path = Path(args.file).expanduser().resolve()
    if not md_path.exists():
        print(json.dumps({"status": "error", "message": f"文件不存在: {md_path}"}))
        sys.exit(1)
    if md_path.stat().st_size > 20 * 1024 * 1024:
        print(json.dumps({"status": "error", "message": "文件超过 20 MB，请使用分片上传"}))
        sys.exit(1)

    try:
        app_id, app_secret, domain = load_creds(args.env)
        tok = get_token(app_id, app_secret)
        _log("tenant_access_token 获取成功")

        # Step 0：确定上传目标文件夹
        folder_token = (
            args.folder_token
            or os.environ.get("FEISHU_FOLDER_TOKEN", "")
            or get_root_folder_token(tok)
        )

        # Step 1：上传 MD 文件
        file_token = upload_file(tok, md_path, folder_token)

        # Step 2：创建导入任务
        ticket = create_import_task(tok, file_token, md_path.name, folder_token)

        # Step 3：轮询等待完成
        _log("等待导入完成（指数退避轮询）…")
        result = poll_import_task(tok, ticket)
        doc_token = result["token"]
        doc_url   = result["url"]

        wiki_node_token = ""

        # Step 4（可选）：移入 Wiki
        if args.wiki_url or args.wiki_token:
            parent_token = (
                wiki_url_to_token(args.wiki_url) if args.wiki_url else args.wiki_token
            )
            node_info = get_wiki_node_info(tok, parent_token)
            space_id  = node_info["space_id"]
            wiki_node_token = move_doc_to_wiki(tok, space_id, parent_token, doc_token)
            if wiki_node_token:
                doc_url = f"https://{domain}.feishu.cn/wiki/{wiki_node_token}"

        output = {
            "status":          "ok",
            "title":           md_path.stem,
            "doc_token":       doc_token,
            "url":             doc_url,
            "wiki_node_token": wiki_node_token,
        }
        print(json.dumps(output, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
