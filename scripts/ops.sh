#!/usr/bin/env bash
# 运维快捷命令
set -uo pipefail
WORKDIR="${FX_WORKDIR:-$HOME/.openclaw/workspace/fx-signal}"
CONT="${FX_CONTAINER:-}"          # 若 Gateway 跑在 Docker，填容器名
COROOT="${FX_CONTAINER_WORKDIR:-/home/node/.openclaw/workspace/fx-signal}"

run() {  # run <cmd...>
  if [ -n "$CONT" ]; then
    docker exec -u 1000 "$CONT" sh -lc "cd /app && $*"
  else
    sh -lc "$*"
  fi
}

case "${1:-}" in
  report)   python3 "$WORKDIR/src/fx_daily.py" ;;
  json)     python3 "$WORKDIR/src/fx_daily.py" --json ;;
  chart)    python3 "$WORKDIR/src/fx_daily.py" --chart ;;
  send)     python3 "$WORKDIR/src/fx_daily.py" --chart --send ;;
  add-cron) run "node dist/index.js cron add --name \"人民币汇率信号日报\" --cron \"5 10 * * *\" --tz Asia/Shanghai --message \"\$(cat $COROOT/config/prompt.md)\" --channel qqbot --to \"<TARGET>\" --announce --best-effort-deliver --timeout-seconds 600 --declaration-key fx-daily-agent" ;;
  list)     run "node dist/index.js cron list" ;;
  now)      run "node dist/index.js cron run <JOB_ID>" ;;
  runs)     run "node dist/index.js cron runs <JOB_ID>" ;;
  off)      run "node dist/index.js cron disable <JOB_ID>" ;;
  on)       run "node dist/index.js cron enable <JOB_ID>" ;;
  *)        sed -n '2,20p' "$0" ;;
esac
