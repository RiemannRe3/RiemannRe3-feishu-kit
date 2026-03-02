# -*- coding: utf-8 -*-
"""
将本地 PDF 上传为飞书文档附件，并插入到指定 Wiki 文档中。

用法：
    python upload_pdf_to_doc.py
"""

import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

# ── 加载 .env ───────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

APP_ID     = os.environ["FEISHU_APP_ID"]
APP_SECRET = os.environ["FEISHU_APP_SECRET"]
API_BASE   = "https://open.feishu.cn/open-apis"

# ── 参数 ────────────────────────────────────────────────────────────────────
PDF_PATH        = Path("/home/test/.openclaw/workspace/GenAI_for_Systems.pdf")
WIKI_NODE_TOKEN = "N5ZtwQB7NiGTETkPliacVB32n9f"   # URL 中 /wiki/ 后的部分


# ── Token ───────────────────────────────────────────────────────────────────
def get_token() -> str:
    resp = requests.post(
        f"{API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 token 失败: {data}")
    return data["tenant_access_token"]


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def check(data: dict, action: str) -> dict:
    if data.get("code") != 0:
        raise RuntimeError(f"{action} 失败 (code={data['code']}): {data.get('msg')}")
    return data


# ── Step 0：通过 wiki node_token 获取 obj_token（文档 document_id）──────────
def get_doc_token(token: str, node_token: str) -> str:
    """从 Wiki 节点信息中提取对应文档的 obj_token。"""
    url = f"{API_BASE}/wiki/v2/spaces/get_node"
    resp = requests.get(
        url,
        params={"token": node_token, "obj_type": "wiki"},
        headers={**headers(token), "Content-Type": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = check(resp.json(), "获取 Wiki 节点")
    node = data["data"]["node"]
    obj_token = node["obj_token"]
    obj_type  = node.get("obj_type", "docx")
    print(f"[✓] Wiki 节点: {node.get('title', '(无标题)')}")
    print(f"    obj_type={obj_type}, obj_token={obj_token}")
    return obj_token


# ── Step 1：在文档末尾创建空文件 Block，获取内层 block_id ──────────────────
def create_empty_file_block(token: str, document_id: str, file_name: str) -> str:
    """
    在文档末尾创建一个空的文件 Block（block_type=23），返回内层 block_id。

    飞书 API 会自动包一个 block_type=33（视图 Block）外壳，
    真正的文件 Block 是它的子节点。
    """
    url = f"{API_BASE}/docx/v1/documents/{document_id}/blocks/{document_id}/children"
    # 创建时 fileToken 填占位值，后续通过 replace_file 替换
    payload = {
        "index": 1,
        "children": [
            {
                "block_type": 23,
                "file": {"fileToken": "placeholder", "fileName": file_name},
            }
        ],
    }
    print(f"\n[+] 在文档中创建空文件 Block …")
    resp = requests.post(
        url,
        headers={**headers(token), "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    data = check(resp.json(), "创建空文件 Block")
    outer = data["data"]["children"][0]
    inner_block_id = outer["children"][0]   # 真正的文件 block
    print(f"[✓] 空文件 Block 创建成功，inner_block_id={inner_block_id}")
    return inner_block_id


# ── Step 2：将 PDF 上传为与该 Block 关联的素材 ───────────────────────────────
def upload_media(token: str, inner_block_id: str, pdf_path: Path) -> str:
    """
    以内层文件 Block 的 block_id 为 parent_node 上传 PDF，返回 file_token。

    注意：parent_node 必须是文件 Block 的 block_id（doxcn... 格式），
    不能是文档的 document_id，否则 replace_file 会报 1770013 relation mismatch。
    """
    url = f"{API_BASE}/drive/v1/medias/upload_all"
    file_size = pdf_path.stat().st_size
    print(f"\n[↑] 上传素材: {pdf_path.name}  ({file_size/1024/1024:.2f} MB)")

    with open(pdf_path, "rb") as f:
        resp = requests.post(
            url,
            headers=headers(token),
            data={
                "file_name":   pdf_path.name,
                "parent_type": "docx_file",
                "parent_node": inner_block_id,   # 关键：用 block_id，不是 document_id
                "size":        str(file_size),
            },
            files={"file": (pdf_path.name, f, "application/pdf")},
            timeout=60,
        )
    resp.raise_for_status()
    data = check(resp.json(), "上传素材")
    file_token = data["data"]["file_token"]
    print(f"[✓] 素材上传成功，file_token={file_token}")
    return file_token


# ── Step 3：replace_file，将 file_token 写入 Block ───────────────────────────
def insert_file_block(token: str, document_id: str, inner_block_id: str, file_token: str) -> None:
    """用 replace_file patch 操作，将 file_token 与文件 Block 正式关联。"""
    url = f"{API_BASE}/docx/v1/documents/{document_id}/blocks/{inner_block_id}"
    payload = {"replace_file": {"token": file_token}}
    print(f"\n[✎] 关联文件 token 到 Block …")
    resp = requests.patch(
        url,
        headers={**headers(token), "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    if not resp.ok:
        print(f"[✗] HTTP {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    data = check(resp.json(), "replace_file")
    file_info = data["data"]["block"].get("file", {})
    print(f"[✓] 文件关联成功：name={file_info.get('name')}, token={file_info.get('token')}")


# ── 主流程 ───────────────────────────────────────────────────────────────────
def main():
    if not PDF_PATH.exists():
        print(f"[✗] PDF 文件不存在: {PDF_PATH}", file=sys.stderr)
        sys.exit(1)

    print("=" * 55)
    print("飞书文档 PDF 附件上传工具")
    print("=" * 55)

    tok = get_token()
    print(f"[✓] 获取 tenant_access_token 成功")

    # 0. 获取文档 document_id
    doc_id = get_doc_token(tok, WIKI_NODE_TOKEN)

    # 1. 创建空文件 Block，拿到内层 block_id
    inner_block_id = create_empty_file_block(tok, doc_id, PDF_PATH.name)

    # 2. 以 inner_block_id 为 parent_node 上传 PDF，确保关联关系正确
    file_token = upload_media(tok, inner_block_id, PDF_PATH)

    # 3. replace_file：将 file_token 正式写入 Block
    insert_file_block(tok, doc_id, inner_block_id, file_token)

    print("\n[✓] 完成！PDF 已作为附件插入到文档中。")


if __name__ == "__main__":
    main()
