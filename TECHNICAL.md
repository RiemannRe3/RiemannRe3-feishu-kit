# feishu-kit 技术文档

> 面向 AI 辅助调试 / 二次开发。与 README.md（用户快速上手）独立，记录内部架构、模块职责、API 映射和常见错误模式。

---

## 目录

1. [项目结构](#1-项目结构)
2. [包安装方式](#2-包安装方式)
3. [配置加载机制](#3-配置加载机制)
4. [模块职责速查](#4-模块职责速查)
5. [feishu_kit 内部模块详解](#5-feishu_kit-内部模块详解)
6. [CLI 实现细节](#6-cli-实现细节)
7. [书签系统](#7-书签系统)
8. [飞书 API 映射表](#8-飞书-api-映射表)
9. [认证机制](#9-认证机制)
10. [已知错误与修复记录](#10-已知错误与修复记录)
11. [测试说明](#11-测试说明)

---

## 1. 项目结构

```
d03_feishu/
├── feishu_kit/                  ← pip 可安装的核心包
│   ├── __init__.py              ← 公开导出所有主要类
│   ├── config.py                ← 统一配置加载（load_config / get_env_path）
│   ├── client.py                ← FeishuClient（统一门面层）
│   ├── nodes.py                 ← WikiNode / BitableNode / SheetNode
│   ├── drive_api.py             ← FeishuDriveAPI（云盘操作）
│   ├── wiki_api.py              ← FeishuWikiAPI（知识库操作）
│   ├── bitable_builder.py       ← FeishuBitableBuilder（多维表格构建）
│   └── sheet_builder.py         ← FeishuSheetBuilder（电子表格构建）
│
├── cli/
│   ├── __init__.py
│   └── shell.py                 ← 交互式 CLI（FeishuShell REPL）
│
├── tests/
│   ├── test_config.py           ← 配置加载测试（纯本地，6 用例）
│   ├── test_wiki.py             ← Wiki 集成测试（需真实 API 权限）
│   ├── test_bitable.py          ← 多维表格集成测试（需写权限）
│   ├── test_sheet.py            ← 电子表格集成测试（需写权限）
│   └── test_client.py           ← FeishuClient 测试（本地 8 + 集成若干）
│
├── examples/
│   ├── demo_bitable.py          ← 多维表格完整演示
│   ├── demo_sheet.py            ← 电子表格完整演示
│   └── demo_client.py           ← FeishuClient API 演示（书签 / 路径解析）
│
├── .env                         ← 运行时配置（不提交 git）
├── .env.example                 ← 配置模板
├── .feishu_bookmarks.json       ← CLI 书签持久化（不提交 git）
├── pyproject.toml               ← 包定义 + feishu CLI 入口
├── setup.py                     ← 兼容旧版 setuptools editable install
├── requirements.txt             ← 开发依赖
│
├── feishu_bitable_uploader.py   ← 遗留文件：简单 Bitable 上传器
├── feishu_sheet_uploader.py     ← 遗留文件：简单 Sheet 上传器
└── demo.py                      ← 遗留文件：最早的 demo
```

---

## 2. 包安装方式

由于系统 Python 环境限制，采用手动 `.pth` 方式模拟 editable install：

```bash
# 实际执行的安装（等效 pip install -e .）
echo "/home/test/d01_my_project/d03_feishu" > ~/.local/lib/python3.10/site-packages/feishu_kit.pth

# CLI 入口脚本（等效 pyproject.toml [project.scripts]）
# 文件位于 ~/.local/bin/feishu
```

`pyproject.toml` 定义了标准包元数据，未来在其他环境中可正常 `pip install -e .`。

**验证安装：**

```python
import feishu_kit
print(feishu_kit.__version__)   # 应输出 "0.1.0"
```

---

## 3. 配置加载机制

### 优先级（高 → 低）

```
.env 文件（override=True）> shell 环境变量 > 代码内默认值
```

`override=True` 是关键——防止 `source .env`（旧值残留在 shell）污染运行时配置。

### 加载路径解析

`feishu_kit/config.py` 中的 `get_env_path()`：

```python
# config.py 位于 feishu_kit/config.py
# 上一级 = 项目根 = /home/test/d01_my_project/d03_feishu
pkg_dir = Path(__file__).parent   # → feishu_kit/
return pkg_dir.parent / ".env"    # → d03_feishu/.env
```

### 返回的配置键

| 键             | 环境变量               | 说明                                 |
|----------------|------------------------|--------------------------------------|
| `app_id`       | `FEISHU_APP_ID`        | 飞书自建应用 ID                       |
| `app_secret`   | `FEISHU_APP_SECRET`    | 飞书自建应用 Secret                   |
| `domain`       | `FEISHU_DOMAIN`        | 企业域前缀（如 `n3kyhtp7sz`）         |
| `folder_token` | `FEISHU_FOLDER_TOKEN`  | 云盘根文件夹 token（`fld...` 开头）   |
| `default_mode` | `FEISHU_DEFAULT_MODE`  | CLI 默认模式：`wiki`/`drive`/`auto`  |

### CLI 调用时机

`cli/shell.py` 顶层 `_load_feishu_config()` 在模块导入时执行，确保所有 API 类初始化前环境变量已就绪。

---

## 4. 模块职责速查

```
用户代码 / CLI
    │
    ▼
FeishuClient (client.py)          ← 统一入口，负责书签、路径解析
    │
    ├─► WikiNode / BitableNode / SheetNode (nodes.py)   ← 面向对象节点操作
    │       │
    │       ├─► FeishuWikiAPI (wiki_api.py)             ← 知识库 REST 封装
    │       ├─► FeishuBitableBuilder (bitable_builder.py) ← 多维表格 REST 封装
    │       └─► FeishuSheetBuilder (sheet_builder.py)   ← 电子表格 REST 封装
    │
    └─► FeishuDriveAPI (drive_api.py)                   ← 云盘 REST 封装
```

所有 API 类均**自行管理 tenant_access_token 缓存**（提前 60 秒刷新），相互独立。

---

## 5. feishu_kit 内部模块详解

### 5.1 `config.py`

```python
load_config(env_path: str = "") -> Dict[str, Any]
get_env_path() -> Path
```

无副作用（不修改全局状态），可多次调用。

---

### 5.2 `drive_api.py` — FeishuDriveAPI

| 方法 | HTTP | 飞书 API 路径 |
|------|------|--------------|
| `get_root_folder_token()` | GET | `/drive/explorer/v2/root_folder/meta` |
| `list_files(folder_token)` | GET | `/drive/v1/files?folder_token=...` |
| `create_folder(name, parent_token)` | POST | `/drive/v1/files/create_folder` |
| `move_file(token, type, dst_token)` | POST | `/drive/v1/files/{token}/move` |
| `rename_file(token, type, new_name)` | PATCH | `/drive/v1/files/{token}` |
| `delete_file(token, type)` | DELETE | `/drive/v1/files/{token}?type=...` |
| `get_file_url(token, type)` | —（本地拼接）| — |

**重要限制：**
- `list_files` 仅支持 `folder_token`、`page_size`、`page_token` 三个参数，**不支持 `order_by`/`direction`**（传入会 400）
- `folder_token` 以 `nod` 开头时（wiki 节点 token），自动转为空字符串（否则 400）
- `tenant_access_token` 无法访问个人空间"我的空间"，必须用 `FEISHU_FOLDER_TOKEN` 指向已授权的共享文件夹

**URL 拼接规则（get_file_url）：**

| 类型 | URL 模板 |
|------|----------|
| folder | `https://{domain}.feishu.cn/drive/folder/{token}` |
| sheet | `https://{domain}.feishu.cn/sheets/{token}` |
| bitable | `https://{domain}.feishu.cn/base/{token}` |
| doc/docx | `https://{domain}.feishu.cn/docx/{token}` |
| file | `https://{domain}.feishu.cn/file/{token}` |

---

### 5.3 `wiki_api.py` — FeishuWikiAPI

| 方法 | HTTP | 飞书 API 路径 |
|------|------|--------------|
| `list_spaces()` | GET | `/wiki/v2/spaces` |
| `list_nodes(space_id, parent_node_token="")` | GET | `/wiki/v2/spaces/{space_id}/nodes` |
| `get_node(node_token)` | GET | `/wiki/v2/spaces/get_node?token=...&obj_type=wiki` |
| `get_ancestor_chain(node_token)` | — | 递归调用 `get_node`，向上回溯到根 |
| `create_node(space_id, title, obj_type, parent_token)` | POST | `/wiki/v2/spaces/{space_id}/nodes` |
| `delete_node(space_id, node_token)` | DELETE | `/wiki/v2/spaces/{space_id}/nodes/{token}` |
| `move_node(space_id, node_token, target_parent_token)` | POST | `/wiki/v2/spaces/{space_id}/nodes/move` |
| `get_doc_content(obj_token)` | GET | `/docx/v1/documents/{obj_token}/raw_content` |
| `node_url(node_token)` | —（本地拼接）| `https://{domain}.feishu.cn/wiki/{token}` |

**前置权限要求：**
1. 飞书开放平台 → 权限管理 → 开通 `wiki:wiki:readonly`（读）/ `wiki:wiki`（读写）
2. **知识库设置 → 成员 → 将应用添加为协作者**（仅开权限不加成员会 403）

`get_ancestor_chain` 实现：从当前 `node_token` 出发，循环调用 `get_node` 读取 `parent_node_token`，直至 token 为空或已访问过（防循环）。返回从根到当前节点的有序列表。

---

### 5.4 `bitable_builder.py` — FeishuBitableBuilder

| 方法 | HTTP | 飞书 API 路径 |
|------|------|--------------|
| `create_bitable(name, folder_token)` | POST | `/bitable/v1/apps` |
| `create_table(app_token, table_name)` | POST | `/bitable/v1/apps/{app_token}/tables` |
| `get_fields(app_token, table_id)` | GET | `/bitable/v1/apps/{app_token}/tables/{table_id}/fields` |
| `update_field(...)` | PUT | `/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}` |
| `add_field(...)` | POST | `/bitable/v1/apps/{app_token}/tables/{table_id}/fields` |
| `add_records(app_token, table_id, records)` | POST | `/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create` |
| `build(...)` | — | 组合调用：create→create_table→setup_fields→add_records |

**数字字段 formatter 合法值（坑）：**

```
"0"  "0.0"  "0.00"  "0.000"  "0.0000"  "0%"  "0.00%"
```

不在此列表的格式字符串（如 `"0.000000"`）会返回 `code=1254001 WrongRequestBody`。

**并发写冲突 (code=1254291)：**  
`setup_fields` 每次字段操作之间 `sleep(0.2s)` 防止并发写冲突。

---

### 5.5 `sheet_builder.py` — FeishuSheetBuilder

| 方法 | HTTP | 飞书 API 路径 |
|------|------|--------------|
| `create_spreadsheet(title, folder_token)` | POST | `/sheets/v3/spreadsheets` |
| `get_sheets(spreadsheet_token)` | GET | `/sheets/v2/spreadsheets/{token}/metainfo` |
| `rename_sheet(token, sheet_id, new_title)` | POST | `/sheet/v2/spreadsheets/{token}/sheets_batch_update` |
| `write_data(token, sheet_id, data, start_row, start_col)` | PUT | `/sheets/v2/spreadsheets/{token}/values` |
| `append_rows(token, sheet_id, rows)` | POST | `/sheets/v2/spreadsheets/{token}/values_append` |

**注意 API 版本混用（设计原因）：**
- 列出工作表：`v2/metainfo`（非 `v3/sheets`，v3 的 `/sheets` endpoint 需要不同的响应结构）
- 重命名工作表：`sheet/v2`（注意：是 `sheet` 不是 `sheets`）
- 写入/追加：`sheets/v2`

---

### 5.6 `nodes.py` — 节点对象层

三种节点类型及懒加载关系：

```
WikiNode
  ._get_api()  → FeishuWikiAPI（懒加载，首次调用时实例化）
  .ls()        → list_nodes() → [WikiNode | BitableNode | SheetNode]
  .get(name)   → ls() + 名称匹配（精确优先，再模糊）
  .cd(name)    → get(name)，要求返回 WikiNode
  .create_child(title, obj_type)
  .delete()
  .read_content()   → 仅 docx 类型有效
  .to_bitable()     → 转换为 BitableNode（需 obj_type == 'bitable'）
  .to_sheet()       → 转换为 SheetNode（需 obj_type == 'sheet'）

BitableNode
  ._get_builder()  → FeishuBitableBuilder（懒加载）
  .list_tables()
  .get_table_id(table_name)
  .query(table_name, filter_formula, page_size)
  .append_rows(rows, table_name)
  .create_table(table_name, fields_config)

SheetNode
  ._get_builder()  → FeishuSheetBuilder（懒加载）
  .get_sheets()
  .get_sheet_id(sheet_name)
  .write(data, sheet_name, start_row, start_col)
  .append(rows, sheet_name)
```

`_make_node(raw, api)` 工厂函数：根据 `obj_type` 决定返回类型（`bitable`→BitableNode，`sheet`→SheetNode，其余→WikiNode）。

---

### 5.7 `client.py` — FeishuClient

所有 API 实例均懒加载（首次访问时创建）：

```python
_get_wiki_api()     → FeishuWikiAPI
_get_drive_api()    → FeishuDriveAPI
_get_bitable_builder() → FeishuBitableBuilder
_get_sheet_builder()   → FeishuSheetBuilder
```

**书签键格式：** 统一规范化为 `@alias`（含 `@` 前缀）存储在 JSON 文件中。

**`resolve(path)` 路径解析逻辑：**

```python
"@bot/实验记录/子表"
  → parts = ["@bot", "实验记录", "子表"]
  → goto("@bot")              → WikiNode
  → node.get("实验记录")      → WikiNode / BitableNode / SheetNode
  → node.get("子表")          → ...（若上一步返回非 WikiNode，则 TypeError）
```

---

## 6. CLI 实现细节

**文件：** `cli/shell.py`

### 状态机

```python
path_stack: List[Tuple[str, str]]  # [(显示名, token), ...]
mode_stack: List[str]              # "drive" | "wiki"（与 path_stack 等长）
wiki_space_id: str                 # 当前 wiki 空间 ID
```

`is_wiki_mode` = `mode_stack` 非空且最后一项为 `"wiki"`

### 启动流程（start 方法）

```
1. 验证 tenant_access_token（_get_token()）
2. 读取 FEISHU_DEFAULT_MODE
3. 若 mode != "wiki" 且 FEISHU_FOLDER_TOKEN 非空 → 尝试 list_files() 检测云盘权限
4. 决定起始模式：
   - wiki 模式：path_stack = []，显示书签列表
   - drive 模式：path_stack = [(root_name, folder_token)]
```

### 缓存结构

```python
file_cache: Dict[str, List[Dict]]  # drive folder_token → 文件列表
wiki_cache: Dict[str, List[Dict]]  # wiki node_token → 子节点列表
```

两套缓存独立，`invalidate_cache(token)` 同时清除两者对应键。

### Tab 补全（FeishuCompleter）

`get_completions` 根据当前输入的命令前缀决定补全源：

| 输入前缀 | 补全来源 |
|----------|----------|
| `cd` / `open` / `rm` / `rename` | `get_cached_files()`（当前目录文件名） |
| `cd @` | `_bookmarks` 键集合 |
| `mv` 第 2 词（目标） | `get_cached_files()`（文件夹/节点） |
| `touch` 第 2 词 | wiki 模式：`doc/sheet/bitable`；drive 模式：`sheet/bitable` |
| `wiki` 第 2 词 | `spaces/node` + `@`书签 |
| `bm rm` 第 3 词 | `_bookmarks` 键集合 |

### 书签文件路径（CLI 侧）

```python
# cli/shell.py 中
self._bm_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".feishu_bookmarks.json",
)
# = d03_feishu/.feishu_bookmarks.json
```

与 `feishu_kit/client.py` 中的 `_bookmark_path()` 指向同一文件（CLI 和 Python API 共享书签）。

---

## 7. 书签系统

### 存储格式（`.feishu_bookmarks.json`）

```json
{
  "bot": {
    "token": "YAPrwq6eaiHwZHkHJX6cCa1DnNf",
    "space_id": "7xxxxxxxxxxxxxxxxx",
    "title": "bot",
    "url": "https://n3kyhtp7sz.feishu.cn/wiki/YAPrwq6eaiHwZHkHJX6cCa1DnNf"
  }
}
```

**注意：** JSON 文件中的键不含 `@`（如 `"bot"`），CLI 显示和 `goto()` 调用时加 `@` 前缀（`@bot`）。`client.py` 存储时统一规范化为含 `@` 前缀。

### CLI 书签命令

| 命令 | 作用 |
|------|------|
| `bm <别名>` | 将当前 wiki 节点保存为书签，别名不加 `@` |
| `bm list` | 列出所有书签 |
| `bm rm <别名>` | 删除书签（不加 `@`） |
| `bm rm @<别名>` | **错误**：会被解析为 `@@别名`，查找失败 |
| `cd @<别名>` | 等价于 `wiki @<别名>` |
| `wiki @<别名>` | 跳转到书签节点，调用 `get_ancestor_chain` 重建完整路径 |

---

## 8. 飞书 API 映射表

### Token 类型对照

| Token 名称 | 格式前缀 | 用于 |
|------------|----------|------|
| `tenant_access_token` | 无固定 | 所有 API 的认证 header |
| `folder_token` | `fld...` | Drive 文件夹操作 |
| `file_token` | 类型相关 | Drive 文件操作 |
| `node_token` | `wikc...` | Wiki 节点操作（注意：旧格式为 `nod...`） |
| `space_id` | `7...`（纯数字长 ID）| Wiki 空间标识 |
| `app_token` | `BrVPb...` | Bitable 多维表格 |
| `spreadsheet_token` | `shtcn...` | Sheets 电子表格 |
| `obj_token` | 取决于类型 | Wiki 节点对应底层资源 |

### 飞书资源系统区分

| 系统 | URL 特征 | 使用 Token | API 前缀 |
|------|----------|-----------|---------|
| 云盘（Drive）| `/drive/folder/` | `folder_token` | `/drive/v1/` |
| 知识库（Wiki）| `/wiki/` | `node_token` | `/wiki/v2/` |
| 多维表格（Bitable）| `/base/` | `app_token` | `/bitable/v1/` |
| 电子表格（Sheets）| `/sheets/` | `spreadsheet_token` | `/sheets/v2/` 或 `/sheets/v3/` |

**Drive 和 Wiki 是独立系统**，权限分开管理。Wiki 节点 token（`wikc...`）**不能**传给 Drive 的 `folder_token` 参数（会 400）。

---

## 9. 认证机制

### tenant_access_token 获取

```http
POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
Content-Type: application/json

{"app_id": "...", "app_secret": "..."}
```

返回：`{"tenant_access_token": "t-xxx", "expire": 7200}`

### 缓存策略（所有 API 类一致）

```python
if self._token and time.time() < self._token_expire_at - 60:
    return self._token  # 提前 60 秒刷新
```

### 权限范围要求

| 功能 | 所需权限 scope |
|------|--------------|
| 云盘文件列表/创建/移动 | `drive:drive` 或 `drive:file` |
| 知识库只读 | `wiki:wiki:readonly` + **应用为知识库成员** |
| 知识库读写 | `wiki:wiki` + **应用为知识库编辑成员** |
| 多维表格操作 | `bitable:app` |
| 电子表格操作 | `sheets:spreadsheet` |

---

## 10. 已知错误与修复记录

### 错误 E1：`list_files` 400 Bad Request（`order_by` 参数）

**原因：** `/drive/v1/files` 不支持 `order_by`/`direction` 参数。  
**修复：** 移除这两个参数，仅保留 `folder_token`/`page_size`/`page_token`。

### 错误 E2：`list_files` 400（`folder_token=nod...`）

**原因：** `get_root_folder_token()` 有时返回 wiki 节点 token（`nod...`），该 token 不被 `/drive/v1/files` 接受。  
**修复：** `list_files` 内检测 `folder_token.startswith("nod")`，若是则置空（返回"我的空间"）。

### 错误 E3：`list_files` 99991661（Missing access token）

**原因 A：** `tenant_access_token` 无权访问"我的空间"（个人空间需 `user_access_token`）。  
**修复 A：** 改用 `FEISHU_FOLDER_TOKEN`（已授权共享文件夹）作为 CLI 根目录。

**原因 B：** 执行过 `source .env` 后，shell 中残留了旧的占位符值（`FEISHU_APP_ID=your_app_id`），覆盖了真实值。  
**修复 B：** `load_dotenv(override=True)` 确保 `.env` 文件值优先于 shell 环境变量。

### 错误 E4：`create_table` 1254001 WrongRequestBody

**原因：** 请求体中的 `fields` 数组为空或格式不对。  
**修复：** 创建数据表时始终传入至少一个占位主字段 `{"field_name": "标题", "type": 1}`。

### 错误 E5：`add_field` 1254001（number formatter 无效）

**原因：** `formatter` 值为 `"0.0000"` 之外的自定义格式（如 `"0.000000"`）不合法。  
**修复：** Demo 中所有 formatter 改为合法值。合法集合：`"0"` `"0.0"` `"0.00"` `"0.000"` `"0.0000"` `"0%"` `"0.00%"`。

### 错误 E6：`get_sheets` 404（v3 endpoint）

**原因：** 使用了 `/sheets/v3/.../sheets` 端点，实际应使用 `/sheets/v2/.../metainfo`。  
**修复：** `get_sheets` 改为调用 v2 metainfo。

### 错误 E7：`rename_sheet` 90204（request body is wrong）

**原因：** 使用了错误的 endpoint 格式（`v3` 或 body 结构错误）。  
**修复：** 改用 `POST /sheet/v2/spreadsheets/{token}/sheets_batch_update`，注意 URL 路径是 `sheet`（非 `sheets`）。

### 错误 E8：`touch sheet/mkdir` 在 wiki 模式下报错

**原因：** wiki 节点 token 被错误传入 Drive API（两个系统 token 不通用）。  
**修复：** 在所有写命令中增加 `is_wiki_mode` 判断，wiki 模式下调用 `wiki_api.create_node()` 替代 Drive/Sheet API。

### 错误 E9：`wiki spaces` 返回空（Permission Denied）

**原因：** 仅开通 `wiki:wiki:readonly` 权限但未将应用加入知识库成员列表。  
**修复（配置）：** 在飞书知识库 → 设置 → 成员 中将应用添加为协作者。

### 错误 E10：`pip install -e .` 失败（旧版 setuptools）

**原因：** 系统 setuptools 版本 59.6.0，不支持 `build_editable` hook。  
**修复：** 手动写 `.pth` 文件到 `~/.local/lib/python3.10/site-packages/`，并手动创建 `~/.local/bin/feishu` 入口脚本。

---

## 11. 测试说明

### 运行方式

```bash
# 纯本地测试（无网络请求，速度快）
pytest tests/test_config.py -v
pytest tests/test_client.py::TestClientConfig -v
pytest tests/test_client.py::TestBookmarkManagement -v
pytest tests/test_client.py::TestDirectNodeConstruction -v

# 需要真实 API 的集成测试
pytest tests/test_wiki.py -v -s       # 需要 wiki:wiki 权限 + 知识库成员
pytest tests/test_bitable.py -v -s    # 需要 bitable:app 权限 + FEISHU_FOLDER_TOKEN
pytest tests/test_sheet.py -v -s      # 需要 sheets:spreadsheet + FEISHU_FOLDER_TOKEN
pytest tests/test_client.py -v -s     # 综合测试

# 全量运行
pytest tests/ -v
```

### 集成测试的资源清理策略

`test_bitable.py` / `test_sheet.py` 使用 `scope="module"` 的 fixture + `yield`，在所有用例执行完毕后通过 `FeishuDriveAPI.delete_file()` 清理测试文件。若清理失败，fixture 打印文件 token 供手动删除。

### 测试跳过条件

| 测试 | 跳过条件 |
|------|----------|
| `test_wiki.py::TestListSpaces` | 无可访问知识库空间 |
| `test_wiki.py::TestCreateDeleteNode` | 无写权限 |
| `test_bitable.py` / `test_sheet.py` 写操作 | `FEISHU_FOLDER_TOKEN` 为空 |
| `test_client.py::TestGoto::test_goto_real_bookmark` | 无真实 wiki 书签 |
