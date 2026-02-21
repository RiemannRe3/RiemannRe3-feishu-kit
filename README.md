# feishu-kit

个人开发的CLI+Python API的工具包（使用Cusor Agent开发）

主要用于将实验数据自动导入到飞书中。

飞书文档管理工具包。提供两种使用方式：

- **交互式 CLI**：像操作 Linux 文件系统一样浏览和管理飞书云盘与知识库（Wiki）
- **Python API**：在脚本中直接操作 Wiki 节点、多维表格、电子表格

---

## 功能一览

| 功能 | CLI | Python API |
|------|:---:|:----------:|
| 浏览云盘/Wiki 目录（ls / cd / pwd） | ✓ | ✓ |
| 打开文件网页链接 | ✓ | ✓ |
| 创建文件夹 / Wiki 文档节点 | ✓ | ✓ |
| 创建多维表格 / 电子表格 | ✓ | ✓ |
| 移动 / 删除文件 | ✓ | — |
| 向多维表格写入/查询记录 | — | ✓ |
| 向电子表格写入/追加数据 | — | ✓ |
| 书签系统（快速跳转 Wiki 节点） | ✓ | ✓（共享书签文件） |

---

## 安装

```bash
git clone <this-repo>
cd d03_feishu

pip install requests python-dotenv prompt_toolkit

# 注册包路径（等效 pip install -e .）
echo "$PWD" > ~/.local/lib/python3.10/site-packages/feishu_kit.pth
```

---

## 配置

复制 `.env.example` 为 `.env` 并填写：

```bash
cp .env.example .env
```

```ini
# 飞书自建应用凭证（必填）
FEISHU_APP_ID=cli_xxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 企业域前缀，从任意文档 URL 中提取
# 例：https://n3kyhtp7sz.feishu.cn/... → n3kyhtp7sz
FEISHU_DOMAIN=n3kyhtp7sz

# 云盘根文件夹 token（URL 中 /folder/ 后面的字符串）
# 仅使用云盘功能时需要填写
FEISHU_FOLDER_TOKEN=fldxxxxxxxxxxxxxxxx

# CLI 默认启动模式：wiki（推荐） | drive | auto
FEISHU_DEFAULT_MODE=wiki
```

### 飞书应用权限设置

在 [飞书开放平台](https://open.feishu.cn/) 为自建应用开通对应权限：

| 使用功能 | 需开通的权限 scope |
|----------|-------------------|
| 云盘文件浏览/管理 | `drive:drive` |
| 知识库（Wiki）只读 | `wiki:wiki:readonly` |
| 知识库（Wiki）读写 | `wiki:wiki` |
| 多维表格 | `bitable:app` |
| 电子表格 | `sheets:spreadsheet` |

> **知识库额外步骤**：开通权限后，还需要在知识库页面 → 设置 → 成员中，将应用添加为协作者，否则 API 会返回空列表。

---

## 使用方式一：交互式 CLI

```bash
# 直接运行
python -m cli.shell

# 或使用已注册的入口命令
feishu
```

### 启动界面

```
飞书云盘 CLI
输入 "help" 查看命令，Tab 键补全，Ctrl-C / exit 退出

正在连接飞书... ✓
  📖 Wiki 模式（FEISHU_DEFAULT_MODE=wiki）

  书签（可用 cd @<别名> 或 wiki @<别名> 快速跳转）:
    @bot          bot

[📖 wiki-only] ❯
```

### 命令速查

**通用命令**

```bash
ls              # 列出当前目录的文件/节点
ls -l           # 同上，额外显示 token
cd <名称>       # 进入子文件夹或 Wiki 节点（Tab 补全）
cd ..           # 返回上一级
cd @<别名>      # 通过书签跳转（等同于 wiki @<别名>）
pwd             # 显示当前路径
open <名称>     # 打印该文件/节点的飞书网页链接
refresh         # 刷新当前目录缓存
help            # 查看帮助
exit / q        # 退出
```

**云盘命令**

```bash
mkdir <名称>              # 创建文件夹
touch sheet <名称>        # 创建电子表格
touch bitable <名称>      # 创建多维表格
mv <源> <目标文件夹>       # 移动文件
rename <旧名> <新名>      # 重命名
rm <名称>                 # 删除（带二次确认）
```

**知识库（Wiki）命令**

```bash
wiki spaces               # 列出可访问的知识库空间
wiki <space_id>           # 进入指定知识库空间
wiki node <token>         # 通过节点 token 跳转，自动显示完整路径
wiki @<别名>              # 通过书签别名跳转

touch doc <名称>          # 在当前节点下新建文档
touch sheet <名称>        # 在当前节点下新建电子表格
touch bitable <名称>      # 在当前节点下新建多维表格
mv <源节点> <目标节点>    # 移动 Wiki 节点
rm <名称>                 # 删除节点（含所有子节点，不可恢复）
```

**书签命令**

```bash
bm <别名>          # 将当前 Wiki 节点保存为书签
bm list            # 列出所有书签
bm rm <别名>       # 删除书签
```

---

## 使用方式二：Python API

### 初始化

```python
from feishu_kit import FeishuClient

client = FeishuClient()  # 自动读取项目根目录的 .env
```

### 通过书签导航 Wiki 节点

```python
# 先在 CLI 中用 `bm bot` 保存书签，然后在代码中直接使用
node = client.goto("@bot")      # 返回 WikiNode
children = node.ls()            # 列出子节点
sub = node.get("实验记录")      # 按名称查找子节点（支持模糊匹配）
```

### 路径解析（`@别名/子节点名/...`）

```python
# 从书签 @bot 向下导航到"实验记录"
target = client.resolve("@bot/实验记录")
```

### 操作多维表格（Bitable）

```python
# 方式 A：通过路径解析（节点类型为 bitable 时自动转换）
bitable = client.resolve("@bot/实验记录")   # 返回 BitableNode

# 方式 B：直接用 app_token 构造
bitable = client.bitable("BrVPbxxxxxxxx")

# 查询记录
records = bitable.query(table_name="训练结果")
print(records)  # [{"实验名称": "exp_001", "Acc": 0.95, ...}, ...]

# 追加记录
bitable.append_rows([
    {"实验名称": "exp_003", "Acc": 0.97, "状态": "完成"},
], table_name="训练结果")
```

### 操作电子表格（Sheet）

```python
# 方式 A：路径解析
sheet = client.resolve("@bot/周报")   # 返回 SheetNode

# 方式 B：直接构造
sheet = client.sheet("shtcnxxxxxxxx")

# 覆盖写入（第一行为表头）
sheet.write([
    ["实验名称", "Acc", "Loss"],
    ["exp_001",   0.95,  0.23],
    ["exp_002",   0.97,  0.18],
])

# 追加行
sheet.append([["exp_003", 0.98, 0.15]])
```

### 在云盘创建文件

```python
# 在 FEISHU_FOLDER_TOKEN 目录下创建多维表格
bitable = client.create_bitable_in_drive("实验结果_2026")

# 在云盘创建电子表格
sheet = client.create_sheet_in_drive("周报_0221")
```

### 书签管理

```python
# 保存书签（与 CLI 的 bm 命令共享同一个 .feishu_bookmarks.json）
client.save_bookmark("@bot", node_token="wikcnXXX", space_id="7xxx", title="Bot 根目录")

# 查看所有书签
print(client.list_bookmarks())

# 删除书签
client.delete_bookmark("@bot")
```

---

## 项目结构

```
feishu_kit/          核心包
  config.py          配置加载（读取 .env）
  client.py          FeishuClient 统一门面
  nodes.py           WikiNode / BitableNode / SheetNode
  drive_api.py       云盘 API 封装
  wiki_api.py        知识库 API 封装
  bitable_builder.py 多维表格构建器
  sheet_builder.py   电子表格构建器

cli/shell.py         交互式 CLI
examples/            使用示例
tests/               pytest 测试集
.env                 配置文件（本地，不提交 git）
.feishu_bookmarks.json  书签文件（CLI 与 Python API 共享）
```

---

## 运行测试

```bash
# 本地测试（无需网络）
pytest tests/test_config.py tests/test_client.py::TestClientConfig -v

# 集成测试（需要真实 API 权限）
pytest tests/ -v -s
```

详细技术文档见 [TECHNICAL.md](TECHNICAL.md)。
