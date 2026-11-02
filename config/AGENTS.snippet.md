## 聊天命令（standing orders）

以下命令在任何聊天窗口输入即可，无需额外部署：

| 命令 | 动作 |
|---|---|
| `/fx` | 立刻执行汇率日报：运行 `<WORKDIR>/src/fx_daily.py --json --chart --send`，然后按 `<WORKDIR>/config/prompt.md` 的格式输出日报正文 |
| `/help` | 列出本节全部命令 |

规则：
- 收到 `/fx` 时，直接执行，不要追问；执行失败就把错误原文回给用户。
- 收到 `/help` 时，输出上面这张表（用聊天友好的纯文本，不要 markdown 表格语法）。
- 命令不区分大小写。
