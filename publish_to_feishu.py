#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将本地 Markdown 文件创建为飞书文档，并可选地将 PDF 作为附件挂在该文档末尾。

流程：
  1. import_md_to_doc  →  上传 .md、创建导入任务、拿到 doc_token
  2. （可选）移入 Wiki 节点
  3. upload_attachment →  在文档末尾插入文件附件

用法：
  # 仅创建文档
  python publish_to_feishu.py --md note.md

  # 创建文档并附 PDF，挂入 Wiki
  python publish_to_feishu.py --md note.md --pdf paper.pdf \\
    --wiki_url "https://xxx.feishu.cn/wiki/<node_token>"

  # 只附 PDF 到已有文档
  python publish_to_feishu.py --pdf paper.pdf --doc_id <doc_token>

成功输出 JSON（stdout）：
  {"status":"ok","title":"...","doc_token":"...","url":"...","wiki_node_token":"..."}
"""

import argparse
import json
import sys
from pathlib import Path

# 从同目录的两个脚本中导入功能函数
sys.path.insert(0, str(Path(__file__).parent))
import import_md_to_doc as imd
import upload_attachment as ua


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="MD 创建飞书文档 + 可选 PDF 附件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # 文档来源：从 MD 创建，或指定已有文档
    src = p.add_mutually_exclusive_group()
    src.add_argument("--md", metavar="MD_FILE",
                     help="本地 Markdown 文件（创建新文档）")
    src.add_argument("--doc_id", metavar="DOC_ID",
                     help="已有飞书文档 document_id（跳过创建步骤，直接挂附件）")

    # 附件（可选）
    p.add_argument("--pdf", metavar="FILE_PATH",
                   help="要挂在文档末尾的附件（PDF 或任意文件）")

    # Wiki 目标（可选，仅在 --md 时有效）
    wiki = p.add_mutually_exclusive_group()
    wiki.add_argument("--wiki_url",   metavar="URL",
                      help="移入该 Wiki 父节点 URL 下")
    wiki.add_argument("--wiki_token", metavar="NODE_TOKEN",
                      help="移入该 Wiki 父节点 token 下")

    p.add_argument("--folder_token", default="", metavar="TOKEN",
                   help="云盘文件夹 token（留空读 .env FEISHU_FOLDER_TOKEN）")
    p.add_argument("--env", default="", metavar="ENV_FILE",
                   help=".env 文件路径（默认：脚本同目录 .env）")
    return p.parse_args()


def _log(msg: str) -> None:
    print(f"  {msg}", file=sys.stderr)


def main() -> None:
    args = parse_args()

    if not args.md and not args.doc_id:
        print(json.dumps({"status": "error",
                          "message": "必须提供 --md（创建新文档）或 --doc_id（指定已有文档）"}))
        sys.exit(1)
    if not args.md and not args.pdf:
        print(json.dumps({"status": "error",
                          "message": "--doc_id 模式下必须同时提供 --pdf"}))
        sys.exit(1)

    try:
        # ── 凭证（两个子脚本共用同一套凭证）────────────────────────────────
        import os
        app_id, app_secret, domain = imd.load_creds(args.env)
        tok = imd.get_token(app_id, app_secret)
        _log("tenant_access_token 获取成功")

        doc_token       = ""
        doc_url         = ""
        wiki_node_token = ""
        title           = ""

        # ── Step A：从 MD 创建文档 ───────────────────────────────────────────
        if args.md:
            md_path = Path(args.md).expanduser().resolve()
            if not md_path.exists():
                raise FileNotFoundError(f"MD 文件不存在: {md_path}")

            folder_token = (
                args.folder_token
                or os.environ.get("FEISHU_FOLDER_TOKEN", "")
                or imd.get_root_folder_token(tok)
            )
            title = md_path.stem

            # 上传 MD + 创建导入任务
            file_token = imd.upload_file(tok, md_path, folder_token)
            ticket     = imd.create_import_task(tok, file_token, md_path.name, folder_token)
            _log("等待导入完成…")
            result    = imd.poll_import_task(tok, ticket)
            doc_token = result["token"]
            doc_url   = result["url"]
            _log(f"文档创建成功 doc_token={doc_token}")

            # 移入 Wiki（可选）
            if args.wiki_url or args.wiki_token:
                parent_token = (
                    imd.wiki_url_to_token(args.wiki_url)
                    if args.wiki_url else args.wiki_token
                )
                node_info       = imd.get_wiki_node_info(tok, parent_token)
                space_id        = node_info["space_id"]
                wiki_node_token = imd.move_doc_to_wiki(tok, space_id, parent_token, doc_token)
                if wiki_node_token:
                    doc_url = f"https://{domain}.feishu.cn/wiki/{wiki_node_token}"

        else:
            # 直接使用已有文档
            doc_token = args.doc_id

        # ── Step B：挂附件（可选）───────────────────────────────────────────
        if args.pdf:
            import mimetypes
            pdf_path = Path(args.pdf).expanduser().resolve()
            if not pdf_path.exists():
                raise FileNotFoundError(f"附件文件不存在: {pdf_path}")

            mime = mimetypes.guess_type(str(pdf_path))[0] or "application/octet-stream"
            _log(f"挂载附件: {pdf_path.name}  ({mime})")

            inner_id   = ua.create_empty_file_block(tok, doc_token, pdf_path.name)
            file_token = ua.upload_media(tok, inner_id, pdf_path, mime)
            ua.replace_file(tok, doc_token, inner_id, file_token)
            _log("附件挂载完成")

        # ── 输出结果 ─────────────────────────────────────────────────────────
        output = {
            "status":          "ok",
            "title":           title or doc_token,
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
