---
name: feishu-publish
description: 将本地 Markdown 文件发布为飞书 Wiki 文档，并可选地将 PDF 等文件作为附件挂在该文档末尾。当用户提到"把 MD 上传到飞书"、"在飞书创建论文总结"、"发布到飞书 Wiki 并附上 PDF"、"publish to feishu"时使用。
---

# 飞书一键发布（MD 建文档 + PDF 附件）

## 安装

在 feishu-kit 仓库根目录执行：

```bash
bash .cursor/skills/feishu-publish/install.sh
```

安装后目录结构：

```
~/.openclaw/skills/feishu-publish/
├── SKILL.md
├── .env                  ← 安装后手动创建，写入凭证
└── scripts/
    ├── publish_to_feishu.py   ← 主入口
    ├── import_md_to_doc.py
    └── upload_attachment.py
```

`.env` 需包含（凭证来自飞书开放平台自建应用）：

```ini
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_FOLDER_TOKEN=xxx      # 云盘文件夹 token（避免调用根目录 API）
FEISHU_DOMAIN=xxx            # 飞书企业域前缀，如 xcn0zxz3zfn1
```

---

## 使用方法

脚本位于 `$SKILL_DIR/scripts/publish_to_feishu.py`，凭证默认读取 `$SKILL_DIR/.env`。

### 场景 1：MD 建文档 + PDF 附件 + 移入 Wiki（完整流程）

```bash
python $SKILL_DIR/scripts/publish_to_feishu.py \
  --env $SKILL_DIR/.env \
  --md /path/to/summary.md \
  --pdf /path/to/paper.pdf \
  --wiki_url "https://xxx.feishu.cn/wiki/<父节点token>"
```

### 场景 2：只建文档

```bash
python $SKILL_DIR/scripts/publish_to_feishu.py \
  --env $SKILL_DIR/.env \
  --md /path/to/summary.md \
  --wiki_url "https://xxx.feishu.cn/wiki/<父节点token>"
```

### 场景 3：给已有文档挂附件

```bash
python $SKILL_DIR/scripts/publish_to_feishu.py \
  --env $SKILL_DIR/.env \
  --doc_id <document_id> \
  --pdf /path/to/paper.pdf
```

> `$SKILL_DIR` 安装后为 `~/.openclaw/skills/feishu-publish`

---

## 全部参数

| 参数 | 说明 |
|------|------|
| `--md <path>` | 本地 Markdown 文件（与 `--doc_id` 二选一） |
| `--doc_id <id>` | 已有文档的 document_id（跳过建文档，直接挂附件） |
| `--pdf <path>` | 附件文件路径（可选；`--doc_id` 时必填） |
| `--wiki_url <url>` | 移入该 Wiki 父节点 URL |
| `--wiki_token <token>` | 移入该 Wiki 父节点 token（与 `--wiki_url` 二选一） |
| `--env <path>` | .env 文件路径（默认：脚本同目录的 .env） |
| `--folder_token <token>` | 覆盖 .env 中的 FEISHU_FOLDER_TOKEN |

---

## 成功输出（stdout JSON）

```json
{
  "status": "ok",
  "title": "summary",
  "doc_token": "Xxxxx",
  "url": "https://xxx.feishu.cn/wiki/Xxxxx",
  "wiki_node_token": "Xxxxx"
}
```

失败：`{"status":"error","message":"..."}` + 非 0 退出码。

`url` 字段即为生成的飞书文档链接，可直接发给用户。

---

## 所需飞书 Bot 权限

| Scope | 用途 |
|-------|------|
| `drive:file:upload` | 上传 MD 文件到云盘 |
| `docs:document:import` | 创建/查询导入任务 |
| `wiki:wiki` | 移入 Wiki 节点（使用 `--wiki_url`/`--wiki_token` 时） |
| `docs:document.media:upload` | 上传附件素材（使用 `--pdf` 时） |
| `docs:document` | 操作文档 Block（使用 `--pdf` 时） |

---

## 典型 OpenClaw 工作流（论文处理）

```
1. 下载论文 PDF 到本地
2. 阅读并整理为 Markdown 总结，写入 /tmp/summary.md
3. 执行：
   SKILL_DIR=~/.openclaw/skills/feishu-publish
   result=$(python $SKILL_DIR/scripts/publish_to_feishu.py \
     --env $SKILL_DIR/.env \
     --md /tmp/summary.md \
     --pdf /path/to/paper.pdf \
     --wiki_url "https://xxx.feishu.cn/wiki/<目标节点>")
4. 解析结果：
   echo $result | python -c "import sys,json;print(json.load(sys.stdin)['url'])"
5. 将 url 返回给用户
```
