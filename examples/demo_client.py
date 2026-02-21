# -*- coding: utf-8 -*-
"""
FeishuClient 统一门面层 Demo
演示：通过书签导航、路径解析、直接构造节点等 Python API 操作飞书。

运行方式：
  python examples/demo_client.py

前置条件：
  1. .env 中已配置 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_DOMAIN
  2. 已在 CLI 中用 `bm <alias>` 保存了至少一个 Wiki 书签
     或手动调用 client.save_bookmark("bot", node_token=..., space_id=...)
"""

from feishu_kit import FeishuClient


def demo_bookmark_navigation():
    """演示：通过书签别名导航 Wiki 节点。"""
    client = FeishuClient()
    print("当前配置:", client.config)
    print()

    bookmarks = client.list_bookmarks()
    if not bookmarks:
        print("暂无书签。请先在 CLI 中执行 `bm <别名>` 保存一个 Wiki 节点。")
        print("也可以直接调用 client.save_bookmark() 手动保存：")
        print("  client.save_bookmark('@bot', node_token='wikcnXXX', space_id='7xxx', title='Bot 根目录')")
        return

    print(f"已有书签 {len(bookmarks)} 个：")
    for alias, info in bookmarks.items():
        print(f"  {alias}  →  {info.get('title')}  ({info.get('node_token')})")
    print()

    # 用第一个书签演示
    alias = list(bookmarks.keys())[0]
    print(f"[演示] 跳转到书签 {alias!r}...")
    node = client.goto(alias)
    print(f"  节点：{node}")

    print(f"\n[演示] 列出 {alias!r} 的子节点...")
    children = node.ls()
    for child in children[:5]:
        print(f"  {child}")

    return node


def demo_path_resolve():
    """演示：路径解析。"""
    client = FeishuClient()
    bookmarks = client.list_bookmarks()
    if not bookmarks:
        print("请先保存书签后再运行此 Demo。")
        return

    alias = list(bookmarks.keys())[0]
    children = client.goto(alias).ls()

    if children:
        first_child_title = getattr(children[0], "title", None)
        if first_child_title:
            path = f"{alias}/{first_child_title}"
            print(f"[演示] 解析路径: {path!r}")
            try:
                node = client.resolve(path)
                print(f"  结果：{node}")
            except Exception as e:
                print(f"  解析失败: {e}")


def demo_bitable_operations(app_token: str):
    """演示：直接通过 app_token 操作多维表格。"""
    client = FeishuClient()
    bitable = client.bitable(app_token)

    print(f"[演示] 列出多维表格的数据表：{app_token}")
    tables = bitable.list_tables()
    for t in tables:
        print(f"  {t['table_id']}  {t.get('name')}")

    if tables:
        table_name = tables[0].get("name", "")
        print(f"\n[演示] 查询数据表 {table_name!r} 的前 5 条记录...")
        records = bitable.query(table_name=table_name, page_size=5)
        for i, r in enumerate(records[:5], 1):
            print(f"  [{i}] {r}")

    print(f"\n多维表格链接：{bitable.url}")


if __name__ == "__main__":
    print("=" * 60)
    print("  Demo 1: 书签导航")
    print("=" * 60)
    demo_bookmark_navigation()

    print()
    print("=" * 60)
    print("  Demo 2: 路径解析")
    print("=" * 60)
    demo_path_resolve()

    # 如需演示多维表格操作，填入真实 app_token：
    # print()
    # print("=" * 60)
    # print("  Demo 3: 多维表格操作")
    # print("=" * 60)
    # demo_bitable_operations("BrVPb...")
