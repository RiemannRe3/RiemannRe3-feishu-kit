# 飞书多维表格上传 Demo

将科研实验数据方便地上传到飞书**多维表格（Bitable）**的小组件，可集成到现有 Python 实验脚本中。

## 快速开始

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **配置飞书**
   - 在 [飞书开放平台](https://open.feishu.cn/) 创建自建应用，获取 `App ID`、`App Secret`
   - 为应用开通「多维表格」相关权限并发布
   - 打开目标多维表格，在表格中为自建应用开通「可管理」权限
   - 从多维表格 URL 获取 `app_token` 和 `table_id`：
     - URL 格式：`https://xxx.feishu.cn/base/{app_token}?table={table_id}`
     - `app_token`：`/base/` 后面、`?table=` 前面的部分（通常以 `bas` 开头）
     - `table_id`：`table=` 后面的部分（通常以 `tbl` 开头）

3. **设置环境变量**（或复制 `.env.example` 为 `.env` 后填入）
   ```bash
   export FEISHU_APP_ID=xxx
   export FEISHU_APP_SECRET=xxx
   export FEISHU_APP_TOKEN=bascnxxx
   export FEISHU_TABLE_ID=tblxxx
   ```

4. **运行 Demo**
   ```bash
   python demo.py
   ```

## 在实验脚本中集成

```python
from feishu_bitable_uploader import FeishuBitableUploader

# 使用环境变量
uploader = FeishuBitableUploader()

# 每条记录是「列名 -> 值」的字典，列名需与多维表格中的列名一致
uploader.add_records([
    {"实验名称": "exp_001", "指标A": 0.95, "指标B": 0.88, "备注": "baseline"},
    {"实验名称": "exp_002", "指标A": 0.96, "指标B": 0.90, "备注": "tuned"},
])

# 单条记录
uploader.add_record({"实验名称": "exp_003", "指标A": 0.97, "指标B": 0.91})
```

也可在初始化时直接传入 `app_id`、`app_secret`、`app_token`、`table_id`。单次最多 500 条，超出会自动分批。
