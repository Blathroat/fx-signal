# 部署手册

## 前置

- 一台已装好 OpenClaw Gateway 的机器（Docker 或本机均可）
- Python 3.8+（无第三方依赖）
- 能访问：新浪财经、CFETS、外管局、Frankfurter、纽约联储

## 1. 放置代码

OpenClaw 的工作区默认在 `~/.openclaw/workspace`。若 Gateway 跑在 Docker 里，宿主机路径通常是 `/root/.openclaw/workspace`，容器内挂载为 `/home/node/.openclaw/workspace`。

```bash
cp -r fx-signal ~/.openclaw/workspace/fx-signal
chown -R 1000:1000 ~/.openclaw/workspace/fx-signal
```

## 2. 配置推送目标

```bash
cp config/settings.example.json config/settings.json
```

填入你的聊天目标（QQ C2C 的 openid、Telegram chat id 等）：

```json
{ "channel": "qqbot", "target": "<你的目标 ID>" }
```

也可以用环境变量 `FX_QQ_CHANNEL` / `FX_QQ_TARGET` 覆盖。**settings.json 不要提交到仓库。**

## 3. 自检

```bash
python3 src/fx_daily.py            # 文字版
python3 src/fx_daily.py --json     # 结构化快照
python3 src/fx_daily.py --chart    # 出图 data/chart.png
```

## 4. 注册定时任务

在 Gateway 容器/主机里执行（把 `<PATH>` 换成容器内路径）：

```bash
openclaw cron add \
  --name "人民币汇率信号日报" \
  --cron "5 10 * * *" --tz Asia/Shanghai \
  --message "$(cat <PATH>/config/prompt.md)" \
  --channel <channel> --to <target> \
  --announce --best-effort-deliver \
  --timeout-seconds 600 \
  --declaration-key fx-daily-agent
```

## 5. 注册聊天命令

在 `~/.openclaw/workspace/AGENTS.md` 里追加 standing orders（见仓库 `config/AGENTS.snippet.md`），模型每次会话都会读到，于是 `/fx`、`/help` 就能被识别。

## 6. 自定义

- 改信号阈值：`src/fx_daily.py` 里 `build()` 的判定条件；
- 改图表配色/布局：`src/render.py`；
- 改日报风格：`config/prompt.md`。

## 常见问题

**Q: 为什么现价和中间价日期不一致？**
中间价每日 9:15 发布；若任务跑在 9:15 之前，或遇到节假日，两者会差一天。脚本会检测并标注「非同日」，此时不计算偏离度。

**Q: 结售汇数据为什么总是上个月的？**
外管局每月中下旬发布上月数据，天然滞后约 20 天，属于结构性指标，不适合做日内信号。

**Q: 容器重建后要重装吗？**
不用。本项目零第三方依赖，代码和数据都在 `data/` 和 `src/`，随工作区挂载保留。
