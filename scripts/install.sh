#!/usr/bin/env bash
# 把项目部署到 OpenClaw 工作区
set -euo pipefail

WORKDIR="${1:-$HOME/.openclaw/workspace/fx-signal}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> 部署到 $WORKDIR"
mkdir -p "$WORKDIR"
rsync -a --exclude data --exclude .git "$SRC"/ "$WORKDIR"/
mkdir -p "$WORKDIR/data"

if [ ! -f "$WORKDIR/config/settings.json" ]; then
  cp "$WORKDIR/config/settings.example.json" "$WORKDIR/config/settings.json"
  echo "!! 请编辑 $WORKDIR/config/settings.json 填入聊天目标 ID"
fi

# 用实际路径替换提示词里的占位符
sed -i "s#{{WORKDIR}}#$WORKDIR#g" "$WORKDIR/config/prompt.md"

echo "==> 自检"
python3 "$WORKDIR/src/fx_daily.py" | head -20

cat <<EOF

==> 完成。接下来：
  1) 编辑 $WORKDIR/config/settings.json
  2) 在 AGENTS.md 追加 config/AGENTS.snippet.md（把 <WORKDIR> 换成 $WORKDIR）
  3) 注册定时任务：bash $WORKDIR/scripts/ops.sh add-cron
EOF
