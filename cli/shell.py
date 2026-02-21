# -*- coding: utf-8 -*-
"""
飞书云盘 CLI 文件管理器
交互式命令行，支持浏览云盘目录和知识库（Wiki）、创建/重命名/移动/删除文件。

依赖：requests, python-dotenv, prompt_toolkit
安装：pip install -e .（项目根目录）
运行：feishu  或  python -m cli.shell

云盘命令：
  ls / ls -l          列出当前目录（-l 显示 token）
  cd <name>           进入子文件夹（Tab 补全）
  cd ..               返回上一级
  pwd                 显示当前路径
  open <name>         打印文件网页链接
  mkdir <name>        创建文件夹
  touch sheet <name>  创建电子表格
  touch bitable <name>创建多维表格
  mv <src> <dst>      移动到当前目录下的文件夹
  rename <old> <new>  重命名
  rm <name>           删除（带确认）
  refresh             刷新当前目录缓存

知识库命令：
  wiki spaces         列出可访问的知识库空间
  wiki <space_id>     进入指定知识库空间（ls/cd/open 自动切换为 wiki 模式）
  wiki node <token>   通过节点 token 直接跳转到某个 wiki 节点
  wiki @<别名>        通过书签别名跳转

书签命令（快速保存 wiki 节点）：
  bm <别名>           把当前 wiki 节点保存为别名
  bm list             列出所有书签
  bm rm <别名>        删除指定书签

通用：
  help                显示帮助
  exit / q            退出
"""

import os
import sys
import json

# 加载项目根目录的 .env 文件（override=True 防止旧 Shell 变量干扰）
from feishu_kit.config import load_config as _load_feishu_config
_load_feishu_config()

from typing import List, Dict, Optional, Tuple, Any
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.history import InMemoryHistory

from feishu_kit.drive_api import FeishuDriveAPI, FILE_TYPE_FOLDER
from feishu_kit.sheet_builder import FeishuSheetBuilder
from feishu_kit.bitable_builder import FeishuBitableBuilder
from feishu_kit.wiki_api import FeishuWikiAPI


# ────────────────────────────────────────────
# 颜色/样式
# ────────────────────────────────────────────

SHELL_STYLE = Style.from_dict({
    "prompt.bracket": "#888888",
    "prompt.path":    "#44aaff bold",
    "prompt.wiki":    "#cc88ff bold",   # wiki 模式路径显示为紫色
    "prompt.arrow":   "#ffffff",
})

COL_RESET   = "\033[0m"
COL_BOLD    = "\033[1m"
COL_CYAN    = "\033[96m"
COL_GREEN   = "\033[92m"
COL_YELLOW  = "\033[93m"
COL_RED     = "\033[91m"
COL_GREY    = "\033[90m"
COL_BLUE    = "\033[94m"
COL_MAGENTA = "\033[95m"   # wiki 模式使用紫色


def _c(text: str, color: str) -> str:
    """包裹 ANSI 颜色（终端非 TTY 时自动跳过）。"""
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{COL_RESET}"


# ────────────────────────────────────────────
# Tab 补全
# ────────────────────────────────────────────

class FeishuCompleter(Completer):
    """根据命令上下文动态补全文件名。"""

    def __init__(self, shell: "FeishuShell"):
        self._shell = shell

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        words = text.split()
        if not words:
            return

        cmd = words[0].lower()
        # 正在输入命令本身
        if len(words) == 1 and not text.endswith(" "):
            cmds = ["ls", "cd", "pwd", "open", "mkdir", "touch", "mv",
                    "rename", "rm", "refresh", "wiki", "bm", "help", "exit", "q"]
            for c in cmds:
                if c.startswith(cmd):
                    yield Completion(c, start_position=-len(words[0]))
            return

        # touch 子命令补全（wiki 模式多一个 doc）
        if cmd == "touch" and len(words) == 2 and not text.endswith(" "):
            subs = ["doc", "sheet", "bitable"] if self._shell.is_wiki_mode else ["sheet", "bitable"]
            for sub in subs:
                if sub.startswith(words[1].lower()):
                    yield Completion(sub, start_position=-len(words[1]))
            return

        # wiki 子命令 / 书签别名补全
        if cmd == "wiki" and len(words) == 2 and not text.endswith(" "):
            prefix = words[1]
            for sub in ["spaces", "node"]:
                if sub.startswith(prefix.lower()):
                    yield Completion(sub, start_position=-len(prefix))
            # @别名补全
            if prefix.startswith("@") or not prefix:
                for alias in self._shell._bookmarks:
                    candidate = "@" + alias
                    if candidate.startswith(prefix):
                        info = self._shell._bookmarks[alias]
                        yield Completion(
                            candidate,
                            start_position=-len(prefix),
                            display=f"{candidate}  ({info.get('title', '')})",
                        )
            return

        # bm 子命令补全
        if cmd == "bm" and len(words) == 2 and not text.endswith(" "):
            prefix = words[1]
            for sub in ["list", "rm"]:
                if sub.startswith(prefix.lower()):
                    yield Completion(sub, start_position=-len(prefix))
            # 书签别名补全（用于 bm rm）
            for alias in self._shell._bookmarks:
                if alias.startswith(prefix):
                    yield Completion(alias, start_position=-len(prefix),
                                     display=f"{alias}  ({self._shell._bookmarks[alias].get('title', '')})")
            return

        # bm rm <别名> 的第三个词补全
        if cmd == "bm" and len(words) == 3 and words[1] == "rm" and not text.endswith(" "):
            prefix = words[2]
            for alias in self._shell._bookmarks:
                if alias.startswith(prefix):
                    yield Completion(alias, start_position=-len(prefix),
                                     display=f"{alias}  ({self._shell._bookmarks[alias].get('title', '')})")
            return

        # 文件名/节点名补全
        if cmd in ("cd", "open", "mv", "rename", "rm"):
            is_wiki = self._shell.is_wiki_mode
            folders_only = not is_wiki and (cmd == "cd" or (cmd == "mv" and len(words) >= 3))
            prefix = words[-1] if len(words) > 1 else ""

            # @别名补全（cd / wiki 都支持）
            if prefix.startswith("@"):
                for alias in self._shell._bookmarks:
                    candidate = "@" + alias
                    if candidate.startswith(prefix):
                        info = self._shell._bookmarks[alias]
                        yield Completion(
                            candidate,
                            start_position=-len(prefix),
                            display=f"{candidate}  ({info.get('title', '')})",
                        )
                return

            files = self._shell.get_cached_files()
            for f in files:
                name = f.get("name", "") or f.get("title", "")
                ftype = f.get("type") or f.get("obj_type", "")
                is_folder = ftype == FILE_TYPE_FOLDER or f.get("has_child", False)
                if folders_only and not is_folder:
                    continue
                if name.lower().startswith(prefix.lower()):
                    icon = "📁 " if is_folder else ""
                    yield Completion(
                        name,
                        start_position=-len(prefix),
                        display=f"{icon}{name}",
                    )


# ────────────────────────────────────────────
# Shell 主体
# ────────────────────────────────────────────

class FeishuShell:
    """
    飞书云盘 + 知识库交互式 CLI。

    path_stack:  [(显示名, token), ...]，第 0 项为当前模式的根目录。
    mode_stack:  与 path_stack 等长，每项为 "drive" 或 "wiki"。
    wiki_space_id: 当前 wiki 模式使用的空间 ID。
    """

    def __init__(self):
        self.api = FeishuDriveAPI()
        self.wiki_api = FeishuWikiAPI(
            app_id=self.api.app_id,
            app_secret=self.api.app_secret,
            domain=self.api.domain,
        )
        self.sheet_builder  = FeishuSheetBuilder(
            app_id=self.api.app_id, app_secret=self.api.app_secret
        )
        self.bitable_builder = FeishuBitableBuilder(
            app_id=self.api.app_id, app_secret=self.api.app_secret
        )

        self.path_stack: List[Tuple[str, str]] = []
        self.mode_stack: List[str] = []          # "drive" | "wiki"
        self.wiki_space_id: str = ""             # 当前 wiki 空间 ID

        # drive 和 wiki 各自独立的缓存
        self.file_cache: Dict[str, List[Dict]] = {}
        self.wiki_cache: Dict[str, List[Dict]] = {}

        # 权限标志（start() 中赋值）
        self._drive_available: bool = False
        self._wiki_available: bool = False

        # 书签：别名 → {token, space_id, title, url}
        # 与 feishu_kit.client 共享同一个 .feishu_bookmarks.json（项目根目录）
        self._bm_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".feishu_bookmarks.json",
        )
        self._bookmarks: Dict[str, Dict] = self._load_bookmarks()

        self._session = PromptSession(
            history=InMemoryHistory(),
            completer=FeishuCompleter(self),
            complete_while_typing=False,
            style=SHELL_STYLE,
        )

    # ──────────────────────────────────────────
    # 状态辅助
    # ──────────────────────────────────────────

    @property
    def is_wiki_mode(self) -> bool:
        return bool(self.mode_stack) and self.mode_stack[-1] == "wiki"

    @property
    def current_token(self) -> str:
        return self.path_stack[-1][1] if self.path_stack else ""

    # 兼容旧代码引用
    @property
    def current_folder_token(self) -> str:
        return self.current_token

    @property
    def current_path(self) -> str:
        if not self.path_stack:
            return "/"
        return "/" + "/".join(name for name, _ in self.path_stack)

    def get_cached_files(self) -> List[Dict]:
        """返回当前目录的文件/节点列表（优先使用缓存）。"""
        token = self.current_token
        if self.is_wiki_mode:
            if token not in self.wiki_cache:
                self.wiki_cache[token] = self.wiki_api.list_nodes(
                    self.wiki_space_id, token
                )
            return self.wiki_cache[token]
        else:
            if token not in self.file_cache:
                self.file_cache[token] = self.api.list_files(token)
            return self.file_cache[token]

    def invalidate_cache(self, token: Optional[str] = None) -> None:
        """清除指定 token（或当前目录）的缓存。"""
        key = token or self.current_token
        self.file_cache.pop(key, None)
        self.wiki_cache.pop(key, None)

    def find_file(self, name: str) -> Optional[Dict]:
        """在当前目录中按名称查找文件/节点，大小写精确匹配。"""
        for f in self.get_cached_files():
            fname = f.get("name") or f.get("title", "")
            if fname == name:
                return f
        return None

    # ──────────────────────────────────────────
    # 书签（持久化到 .feishu_bookmarks.json）
    # ──────────────────────────────────────────

    def _load_bookmarks(self) -> Dict[str, Dict]:
        if os.path.exists(self._bm_path):
            try:
                with open(self._bm_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_bookmarks(self) -> None:
        with open(self._bm_path, "w", encoding="utf-8") as f:
            json.dump(self._bookmarks, f, ensure_ascii=False, indent=2)

    def _cmd_bm(self, args: List[str]) -> None:
        """
        bm <别名>       保存当前 wiki 节点为别名
        bm list         列出所有书签
        bm rm <别名>    删除书签
        """
        if not args or args[0] == "list":
            # 列出所有书签
            if not self._bookmarks:
                print(_c("  （暂无书签，用 bm <别名> 保存当前 wiki 节点）", COL_GREY))
                return
            print()
            print(_c(f"  {'别名':<20} {'标题':<30} TOKEN", COL_BOLD))
            print(_c("  " + "─" * 70, COL_GREY))
            for alias, info in sorted(self._bookmarks.items()):
                title = info.get("title", "")
                token = info.get("token", "")
                print(
                    f"  {_c('@' + alias, COL_MAGENTA):<20} "
                    f"{_c(title, COL_RESET):<30} "
                    f"{_c(token, COL_GREY)}"
                )
            print()
            return

        if args[0] == "rm":
            alias = args[1] if len(args) > 1 else ""
            if not alias:
                print(_c("用法: bm rm <别名>", COL_YELLOW))
                return
            if alias not in self._bookmarks:
                print(_c(f'书签 "@{alias}" 不存在', COL_YELLOW))
                return
            del self._bookmarks[alias]
            self._save_bookmarks()
            print(_c(f'[✓] 已删除书签 "@{alias}"', COL_GREEN))
            return

        # bm <别名>：保存当前位置
        alias = args[0]
        if not self.is_wiki_mode:
            print(_c("只能在 wiki 模式下添加书签，请先 wiki node <token> 进入知识库节点", COL_YELLOW))
            return
        token = self.current_token
        title = self.path_stack[-1][0] if self.path_stack else token
        url   = self.wiki_api.node_url(token)
        self._bookmarks[alias] = {
            "token":    token,
            "space_id": self.wiki_space_id,
            "title":    title,
            "url":      url,
        }
        self._save_bookmarks()
        print(_c(f'[✓] 已保存书签 "@{alias}" → 「{title}」  ({token})', COL_GREEN))

    def _prompt_message(self):
        if not self.path_stack:
            # wiki-only 模式，尚未导航到任何节点
            return HTML(
                '<prompt.bracket>[</prompt.bracket>'
                '<prompt.wiki>📖 wiki-only</prompt.wiki>'
                '<prompt.bracket>]</prompt.bracket>'
                '<prompt.arrow> ❯ </prompt.arrow>'
            )
        mode_prefix = "📖 " if self.is_wiki_mode else ""
        path_color  = "prompt.wiki" if self.is_wiki_mode else "prompt.path"
        return HTML(
            f'<prompt.bracket>[</prompt.bracket>'
            f'<{path_color}>{mode_prefix}{self.current_path}</{path_color}>'
            f'<prompt.bracket>]</prompt.bracket>'
            f'<prompt.arrow> ❯ </prompt.arrow>'
        )

    # ──────────────────────────────────────────
    # 启动与主循环
    # ──────────────────────────────────────────

    def start(self) -> None:
        """初始化并进入 REPL 循环。"""
        print(_c("飞书云盘 CLI", COL_BOLD + COL_CYAN))
        print(_c('输入 "help" 查看命令，Tab 键补全，Ctrl-C / exit 退出\n', COL_GREY))

        # ── 步骤1：验证基础凭证（获取 tenant_access_token）────────────
        print(_c("正在连接飞书...", COL_GREY), end="", flush=True)
        try:
            self.api._get_token()   # 如果 app_id/secret 错误会在这里抛出
        except Exception as e:
            print(_c(f"\n凭证验证失败: {e}", COL_RED))
            print(_c("请检查 .env 中的 FEISHU_APP_ID / FEISHU_APP_SECRET", COL_YELLOW))
            return

        # 读取用户偏好：FEISHU_DEFAULT_MODE = wiki | drive | auto（默认 auto）
        default_mode = os.environ.get("FEISHU_DEFAULT_MODE", "auto").strip().lower()

        # ── 步骤2：按需检测云盘（wiki/auto 模式跳过 drive 检测）──────────
        self._drive_available = False
        drive_err = ""
        if default_mode != "wiki" and self.api.root_folder_token:
            try:
                self.api.list_files(self.api.root_folder_token)
                self._drive_available = True
            except Exception as e:
                drive_err = str(e)

        # ── 步骤3：wiki 始终可用（与 drive 共用 token）────────────────────
        self._wiki_available = True  # token 已在步骤1验证成功

        # ── 步骤4：根据偏好和可用权限设置起始状态 ─────────────────────────
        use_wiki_start = (
            default_mode == "wiki"
            or (default_mode == "auto" and not self._drive_available)
        )

        if not use_wiki_start and self._drive_available:
            # 云盘模式启动
            root_name = (
                os.environ.get("FEISHU_ROOT_NAME")
                or f"…{self.api.root_folder_token[-8:]}"
            )
            self.path_stack = [(root_name, self.api.root_folder_token)]
            self.mode_stack = ["drive"]
            start_msg = ""
        else:
            # Wiki 模式启动
            self.path_stack = []
            self.mode_stack = []
            if default_mode == "wiki":
                start_msg = _c("  📖 Wiki 模式（FEISHU_DEFAULT_MODE=wiki）\n", COL_MAGENTA)
            elif drive_err:
                start_msg = (
                    _c("  [!] 云盘权限不足，已切换为 Wiki 模式\n", COL_YELLOW) +
                    _c(f"      {drive_err[:100]}\n", COL_GREY)
                )
            else:
                start_msg = _c("  📖 Wiki 模式\n", COL_MAGENTA)

        print(_c(" ✓", COL_GREEN))
        if start_msg:
            print(start_msg)

        # ── Wiki 启动：自动显示书签列表（如有） ─────────────────────────
        if use_wiki_start and self._bookmarks:
            print(_c("  书签（可用 cd @<别名> 或 wiki @<别名> 快速跳转）:", COL_BOLD))
            for alias, info in sorted(self._bookmarks.items()):
                title = info.get("title", "")
                print(f"    {_c('@' + alias, COL_MAGENTA):<22} {title}")
            print()

        while True:
            try:
                raw = self._session.prompt(self._prompt_message())
            except KeyboardInterrupt:
                print()
                continue
            except EOFError:
                break

            line = raw.strip()
            if not line:
                continue

            parts = line.split()
            cmd = parts[0].lower()

            try:
                if cmd in ("exit", "q"):
                    break
                elif cmd == "help":
                    self._cmd_help()
                elif cmd == "pwd":
                    self._cmd_pwd()
                elif cmd == "ls":
                    verbose = len(parts) > 1 and parts[1] == "-l"
                    self._cmd_ls(verbose=verbose)
                elif cmd == "cd":
                    target = parts[1] if len(parts) > 1 else ""
                    self._cmd_cd(target)
                elif cmd == "open":
                    name = " ".join(parts[1:]) if len(parts) > 1 else ""
                    self._cmd_open(name)
                elif cmd == "mkdir":
                    name = " ".join(parts[1:]) if len(parts) > 1 else ""
                    self._cmd_mkdir(name)
                elif cmd == "touch":
                    sub = parts[1].lower() if len(parts) > 1 else ""
                    name = " ".join(parts[2:]) if len(parts) > 2 else ""
                    self._cmd_touch(sub, name)
                elif cmd == "mv":
                    src  = parts[1] if len(parts) > 1 else ""
                    dst  = " ".join(parts[2:]) if len(parts) > 2 else ""
                    self._cmd_mv(src, dst)
                elif cmd == "rename":
                    old = parts[1] if len(parts) > 1 else ""
                    new = " ".join(parts[2:]) if len(parts) > 2 else ""
                    self._cmd_rename(old, new)
                elif cmd == "rm":
                    name = " ".join(parts[1:]) if len(parts) > 1 else ""
                    self._cmd_rm(name)
                elif cmd == "refresh":
                    self._cmd_refresh()
                elif cmd == "wiki":
                    arg1 = parts[1] if len(parts) > 1 else ""
                    arg2 = parts[2] if len(parts) > 2 else ""
                    self._cmd_wiki(arg1, arg2)
                elif cmd == "bm":
                    self._cmd_bm(parts[1:])
                else:
                    print(_c(f"未知命令: {cmd}（输入 help 查看帮助）", COL_YELLOW))
            except KeyboardInterrupt:
                print()
            except Exception as e:
                print(_c(f"错误: {e}", COL_RED))

        print(_c("再见！", COL_GREY))

    # ──────────────────────────────────────────
    # 只读命令
    # ──────────────────────────────────────────

    def _cmd_help(self) -> None:
        drive_cmds = [
            ("ls / ls -l",          "列出当前目录（-l 显示 token）"),
            ("cd <name>",           "进入子文件夹 / wiki 节点"),
            ("cd ..",               "返回上一级"),
            ("pwd",                 "显示当前路径"),
            ("open <name>",         "打印飞书网页链接"),
            ("mkdir <name>",        "创建文件夹（仅云盘模式）"),
            ("touch sheet <name>",  "创建电子表格（云盘）/ wiki 节点（wiki 模式）"),
            ("touch bitable <name>","创建多维表格（云盘）/ wiki 节点（wiki 模式）"),
            ("touch doc <name>",    "创建文档节点（仅 wiki 模式）"),
            ("mv <src> <dst>",      "移动文件 / wiki 节点"),
            ("rename <old> <new>",  "重命名（仅云盘模式）"),
            ("rm <name>",           "删除文件 / wiki 节点（带确认）"),
            ("refresh",             "刷新缓存"),
        ]
        wiki_cmds = [
            ("wiki spaces",         "列出可访问的知识库空间"),
            ("wiki <space_id>",     "进入指定知识库空间"),
            ("wiki node <token>",   "通过节点 token 直接跳转"),
            ("wiki @<别名>",        "通过书签别名跳转"),
            ("bm <别名>",           "将当前 wiki 节点保存为书签"),
            ("bm list",             "列出所有书签"),
            ("bm rm <别名>",        "删除书签"),
        ]
        other_cmds = [
            ("help",   "显示此帮助"),
            ("exit / q", "退出"),
        ]
        print()
        print(_c("  ── 云盘 & 通用 ──────────────────────────────────────", COL_GREY))
        for cmd, desc in drive_cmds:
            print(f"  {_c(cmd, COL_CYAN):<32}  {desc}")
        print()
        print(_c("  ── 知识库（Wiki）────────────────────────────────────", COL_GREY))
        for cmd, desc in wiki_cmds:
            print(f"  {_c(cmd, COL_MAGENTA):<32}  {desc}")
        print()
        for cmd, desc in other_cmds:
            print(f"  {_c(cmd, COL_CYAN):<32}  {desc}")
        print()

    def _cmd_pwd(self) -> None:
        print(_c(self.current_path, COL_CYAN))

    def _cmd_ls(self, verbose: bool = False) -> None:
        files = self.get_cached_files()
        if not files:
            print(_c("  （空目录）", COL_GREY))
            return

        token_col = "  TOKEN                          " if verbose else ""
        print()
        print(_c(f"  {'ICON':<4} {'NAME':<40}{token_col}", COL_BOLD))
        print(_c("  " + "─" * (46 + (34 if verbose else 0)), COL_GREY))

        if self.is_wiki_mode:
            # wiki 节点列表
            for node in files:
                title    = node.get("title", "（无标题）")
                ntoken   = node.get("node_token", "")
                obj_type = node.get("obj_type", "wiki")
                has_child = node.get("has_child", False)
                icon     = self.wiki_api.icon(obj_type)
                display  = title + "/" if has_child else title
                color    = COL_MAGENTA if has_child else COL_RESET
                token_part = f"  {_c(ntoken, COL_GREY)}" if verbose else ""
                print(f"  {icon:<5} {_c(display, color)}{token_part}")
        else:
            # drive 文件列表（文件夹优先）
            folders = [f for f in files if f.get("type") == FILE_TYPE_FOLDER]
            others  = [f for f in files if f.get("type") != FILE_TYPE_FOLDER]
            for f in folders + others:
                ftype  = f.get("type", "file")
                fname  = f.get("name", "")
                ftoken = f.get("token", "")
                icon   = self.api.icon(ftype)
                display_name = fname + "/" if ftype == FILE_TYPE_FOLDER else fname
                name_color   = COL_BLUE if ftype == FILE_TYPE_FOLDER else COL_RESET
                token_part   = f"  {_c(ftoken, COL_GREY)}" if verbose else ""
                print(f"  {icon:<5} {_c(display_name, name_color)}{token_part}")

        print()
        print(_c(f"  共 {len(files)} 个{'节点' if self.is_wiki_mode else '文件'}", COL_GREY))
        print()

    def _cmd_cd(self, target: str) -> None:
        if not target:
            hint = "cd <节点名/@别名> 或 cd .." if self.is_wiki_mode else "cd <文件夹名/@别名> 或 cd .."
            print(_c(f"用法: {hint}", COL_YELLOW))
            return

        # cd @<alias>：书签跳转（与 wiki @<alias> 等价）
        if target.startswith("@"):
            self._cmd_wiki(target, "")
            return

        if target == "..":
            if len(self.path_stack) <= 1:
                print(_c("已在根目录", COL_YELLOW))
                return
            self.path_stack.pop()
            self.mode_stack.pop()
            return

        f = self.find_file(target)
        if f is None:
            print(_c(f'未找到: "{target}"', COL_YELLOW))
            return

        if self.is_wiki_mode:
            # wiki 中每个节点都可当"目录"进入，无论是否有子节点
            self.path_stack.append((target, f["node_token"]))
            self.mode_stack.append("wiki")
        else:
            if f.get("type") != FILE_TYPE_FOLDER:
                print(_c(f'"{target}" 不是文件夹', COL_YELLOW))
                return
            self.path_stack.append((target, f["token"]))
            self.mode_stack.append("drive")

    def _cmd_open(self, name: str) -> None:
        if not name:
            print(_c("用法: open <文件名>", COL_YELLOW))
            return
        f = self.find_file(name)
        if f is None:
            print(_c(f'未找到: "{name}"', COL_YELLOW))
            return
        if self.is_wiki_mode:
            url = self.wiki_api.node_url(f["node_token"])
        else:
            url = self.api.get_file_url(f["token"], f.get("type", "file"))
        print(_c(url, COL_CYAN))

    # ──────────────────────────────────────────
    # Wiki 命令
    # ──────────────────────────────────────────

    def _cmd_wiki(self, arg1: str, arg2: str) -> None:
        """
        wiki spaces          → 列出所有可访问的知识库空间
        wiki <space_id>      → 进入该知识库空间的根目录
        wiki node <token>    → 通过节点 token 直接跳转
        """
        # wiki @<别名>：书签跳转
        if arg1.startswith("@"):
            alias = arg1[1:]
            if alias not in self._bookmarks:
                print(_c(f'书签 "@{alias}" 不存在，用 bm list 查看所有书签', COL_YELLOW))
                return
            info = self._bookmarks[alias]
            token    = info["token"]
            space_id = info["space_id"]
            self.wiki_space_id = space_id
            # 重建完整路径
            print(_c("正在解析节点路径...", COL_GREY), end="", flush=True)
            chain = self.wiki_api.get_ancestor_chain(token)
            self.path_stack = []
            self.mode_stack = []
            for ancestor in chain:
                t = ancestor.get("title", ancestor.get("node_token", "?"))
                k = ancestor.get("node_token", "")
                self.path_stack.append((t, k))
                self.mode_stack.append("wiki")
            self.wiki_cache.pop(token, None)
            title = info["title"]
            print(_c(f" ✓", COL_GREEN))
            print(_c(f'[✓] 已跳转到书签 "@{alias}" → 「{title}」  路径: {self.current_path}', COL_GREEN))
            return

        if not arg1 or arg1 == "spaces":
            # 列出知识库空间
            spaces = self.wiki_api.list_spaces()
            if not spaces:
                print(_c("  未找到可访问的知识库空间。", COL_YELLOW))
                print(_c("  请在知识库设置 → 成员 中将应用添加为协作者。", COL_GREY))
                return
            print()
            print(_c(f"  {'SPACE_ID':<25} {'名称'}", COL_BOLD))
            print(_c("  " + "─" * 55, COL_GREY))
            for s in spaces:
                sid  = s.get("space_id", "")
                name = s.get("name", "（无名称）")
                print(f"  {_c(sid, COL_GREY):<25}  {_c(name, COL_MAGENTA)}")
            print()
            return

        if arg1 == "node":
            # 通过 node_token 跳转，自动回溯父节点链以显示完整路径
            node_token = arg2
            if not node_token:
                print(_c("用法: wiki node <node_token>", COL_YELLOW))
                return
            print(_c("正在解析节点路径...", COL_GREY), end="", flush=True)
            node = self.wiki_api.get_node(node_token)
            if not node:
                print()
                print(_c("未找到该节点", COL_RED))
                return
            space_id = node.get("space_id", "")
            self.wiki_space_id = space_id

            # 回溯祖先链，构建完整 path_stack
            chain = self.wiki_api.get_ancestor_chain(node_token)
            self.path_stack = []
            self.mode_stack = []
            for ancestor in chain:
                t = ancestor.get("title", ancestor.get("node_token", "?"))
                k = ancestor.get("node_token", "")
                self.path_stack.append((t, k))
                self.mode_stack.append("wiki")

            title = node.get("title", node_token)
            print(_c(f" ✓", COL_GREEN))
            print(_c(f"[✓] 已跳转到 wiki 节点: 「{title}」  路径: {self.current_path}", COL_GREEN))
            return

        # wiki <space_id> → 进入该知识库根目录
        space_id = arg1
        self.wiki_space_id = space_id
        # 获取空间元信息（名称）
        spaces = self.wiki_api.list_spaces()
        space_name = next(
            (s.get("name", space_id) for s in spaces if s.get("space_id") == space_id),
            f"wiki:{space_id[-8:]}",
        )
        # 进入 wiki 模式：以空字符串作为根节点 token（表示空间根目录）
        self.path_stack = [(space_name, "")]
        self.mode_stack = ["wiki"]
        print(_c(f"[✓] 已进入知识库: 「{space_name}」  输入 ls 查看节点", COL_GREEN))

    # ──────────────────────────────────────────
    # 创建命令
    # ──────────────────────────────────────────

    def _drive_only_guard(self, op: str = "该操作") -> bool:
        """检查当前是否可执行云盘写操作，不可用时打印提示并返回 True（表示应跳过）。"""
        if self.is_wiki_mode:
            print(_c(f'wiki 模式不支持「{op}」，请先 cd .. 回到云盘目录', COL_YELLOW))
            return True
        if not self._drive_available:
            print(_c(f'云盘权限不足，无法执行「{op}」', COL_YELLOW))
            return True
        return False

    def _cmd_mkdir(self, name: str) -> None:
        if self.is_wiki_mode:
            print(_c('wiki 模式请用 "touch doc <名称>" 创建文档节点', COL_YELLOW))
            return
        if not self._drive_available:
            print(_c("云盘权限不足，无法创建文件夹", COL_YELLOW))
            return
        if not name:
            print(_c("用法: mkdir <文件夹名>", COL_YELLOW))
            return
        result = self.api.create_folder(name, self.current_folder_token)
        self.invalidate_cache()
        print(_c(f'[✓] 文件夹已创建: 「{name}」  token={result["token"]}', COL_GREEN))

    def _cmd_touch(self, sub: str, name: str) -> None:
        if self.is_wiki_mode:
            # wiki 模式：创建知识库节点（docx / sheet / bitable）
            type_map = {"doc": "docx", "docx": "docx", "sheet": "sheet", "bitable": "bitable"}
            if sub not in type_map:
                print(_c("wiki 模式用法: touch doc/sheet/bitable <名称>", COL_YELLOW))
                return
            if not name:
                print(_c(f"用法: touch {sub} <名称>", COL_YELLOW))
                return
            obj_type = type_map[sub]
            parent = self.current_token
            node = self.wiki_api.create_node(
                self.wiki_space_id, name, obj_type=obj_type,
                parent_node_token=parent,
            )
            self.invalidate_cache()
            ntoken = node.get("node_token", "")
            url = self.wiki_api.node_url(ntoken)
            print(_c(f"[✓] 已在知识库创建节点 ({obj_type})  →  {url}", COL_GREEN))
            return

        # 云盘模式
        if sub not in ("sheet", "bitable"):
            print(_c("用法: touch sheet <名称>  或  touch bitable <名称>", COL_YELLOW))
            return
        if not name:
            print(_c(f"用法: touch {sub} <名称>", COL_YELLOW))
            return

        folder_token = self.current_folder_token
        if sub == "sheet":
            token = self.sheet_builder.create_spreadsheet(name, folder_token=folder_token)
            ftype = "sheet"
        else:
            token = self.bitable_builder.create_bitable(name, folder_token=folder_token)
            ftype = "bitable"

        self.invalidate_cache()
        url = self.api.get_file_url(token, ftype)
        print(_c(f"[✓] 已创建  →  {url}", COL_GREEN))

    # ──────────────────────────────────────────
    # 修改命令
    # ──────────────────────────────────────────

    def _cmd_mv(self, src: str, dst: str) -> None:
        if not src or not dst:
            print(_c("用法: mv <源名称> <目标名称>", COL_YELLOW))
            return

        if self.is_wiki_mode:
            src_node = self.find_file(src)
            if src_node is None:
                print(_c(f'未找到: "{src}"', COL_YELLOW))
                return
            dst_node = self.find_file(dst)
            if dst_node is None:
                print(_c(f'目标节点未找到: "{dst}"', COL_YELLOW))
                return
            self.wiki_api.move_node(
                self.wiki_space_id,
                src_node["node_token"],
                dst_node["node_token"],
            )
            self.invalidate_cache()
            print(_c(f'[✓] 已移动: 「{src}」 → 「{dst}/」', COL_GREEN))
            return

        src_file = self.find_file(src)
        if src_file is None:
            print(_c(f'未找到: "{src}"', COL_YELLOW))
            return
        dst_file = self.find_file(dst)
        if dst_file is None:
            print(_c(f'目标文件夹未找到: "{dst}"', COL_YELLOW))
            return
        if dst_file.get("type") != FILE_TYPE_FOLDER:
            print(_c(f'"{dst}" 不是文件夹', COL_YELLOW))
            return

        self.api.move_file(src_file["token"], src_file.get("type", "file"), dst_file["token"])
        self.invalidate_cache()
        print(_c(f'[✓] 已移动: 「{src}」 → 「{dst}/」', COL_GREEN))

    def _cmd_rename(self, old: str, new: str) -> None:
        if self.is_wiki_mode:
            print(_c("wiki 节点暂不支持重命名（请在飞书网页端操作）", COL_YELLOW))
            return
        if not self._drive_available:
            print(_c("云盘权限不足，无法重命名", COL_YELLOW))
            return
        if not old or not new:
            print(_c("用法: rename <旧名称> <新名称>", COL_YELLOW))
            return

        f = self.find_file(old)
        if f is None:
            print(_c(f'未找到: "{old}"', COL_YELLOW))
            return

        self.api.rename_file(f["token"], f.get("type", "file"), new)
        self.invalidate_cache()
        print(_c(f'[✓] 已重命名: 「{old}」 → 「{new}」', COL_GREEN))

    def _cmd_rm(self, name: str) -> None:
        if not name:
            print(_c("用法: rm <文件名>", COL_YELLOW))
            return

        f = self.find_file(name)
        if f is None:
            print(_c(f'未找到: "{name}"', COL_YELLOW))
            return

        if self.is_wiki_mode:
            obj_type = f.get("obj_type", "wiki")
            icon = self.wiki_api.icon(obj_type)
            print(_c(f"警告：将永久删除 {icon} 「{name}」（含所有子节点），不可恢复！", COL_RED))
            try:
                confirm = input(_c("确认删除？输入 yes 继续: ", COL_YELLOW)).strip().lower()
            except (KeyboardInterrupt, EOFError):
                print()
                print(_c("已取消", COL_GREY))
                return
            if confirm != "yes":
                print(_c("已取消", COL_GREY))
                return
            self.wiki_api.delete_node(self.wiki_space_id, f["node_token"])
            self.invalidate_cache()
            print(_c(f'[✓] 已删除: 「{name}」', COL_GREEN))
            return

        ftype = f.get("type", "file")
        icon  = self.api.icon(ftype)
        print(_c(f"警告：将永久删除 {icon} 「{name}」（类型: {ftype}），不可恢复！", COL_RED))
        try:
            confirm = input(_c("确认删除？输入 yes 继续: ", COL_YELLOW)).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            print(_c("已取消", COL_GREY))
            return

        if confirm != "yes":
            print(_c("已取消", COL_GREY))
            return

        self.api.delete_file(f["token"], ftype)
        self.invalidate_cache()
        print(_c(f'[✓] 已删除: 「{name}」', COL_GREEN))

    def _cmd_refresh(self) -> None:
        self.invalidate_cache()
        # 预加载，给用户即时反馈
        files = self.get_cached_files()
        print(_c(f"[✓] 已刷新，当前目录共 {len(files)} 个文件", COL_GREEN))


# ────────────────────────────────────────────
# 入口
# ────────────────────────────────────────────

def main() -> None:
    if not os.environ.get("FEISHU_APP_ID") or not os.environ.get("FEISHU_APP_SECRET"):
        print("\033[91m错误：请先在 .env 中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET\033[0m")
        sys.exit(1)
    FeishuShell().start()


if __name__ == "__main__":
    main()
