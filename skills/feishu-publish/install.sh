#!/usr/bin/env bash
# 将 feishu-publish skill 安装到 OpenClaw skills 目录
# 用法：bash .cursor/skills/feishu-publish/install.sh [目标目录]
# 默认目标：~/.openclaw/skills/feishu-publish/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-$HOME/.openclaw/skills/feishu-publish}"

echo "→ 安装目标：$TARGET"
mkdir -p "$TARGET"
cp -r "$SCRIPT_DIR/scripts" "$TARGET/"
cp "$SCRIPT_DIR/SKILL.md"   "$TARGET/"

echo "✓ 安装完成"
echo ""
echo "下一步：将凭证写入 ~/.openclaw/skills/feishu-publish/.env"
echo "  FEISHU_APP_ID=cli_xxx"
echo "  FEISHU_APP_SECRET=xxx"
echo "  FEISHU_FOLDER_TOKEN=xxx"
echo "  FEISHU_DOMAIN=xxx"
