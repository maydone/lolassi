# LOL 队友锐评助手

Windows 命令行工具。在英雄联盟选人阶段读取全队近期战绩，调用 DeepSeek API
`deepseek-v4-flash` 生成犀利幽默的短评，并按队员逐条发送到队伍聊天。

## 功能

- 自动发现 `LeagueClientUx.exe` 并连接本地 LCU。
- 监听选人阶段，默认从最近 20 局中筛选并分析最新 15 场有效对局。
- 统计胜率、KDA、参团率、伤害、经济、视野和补刀，输出可解释标签。
- 按评分给出“夯、顶级、人上人、NPC、拉完了”五档评级。
- 聊天最终格式固定为
  “玩家名【夯/顶级/人上人/NPC/拉完了】胜率：xx% 评分：xxx 一句话点评”；
  不附带 Tag 编号、局数、KDA、参团率或英雄信息。
- 点评采用损友开黑嘴替风格，通过反差比喻和补刀式结尾加强笑点，但只调侃
  操作、意识和近期战绩。
- 一次模型请求生成匿名点评，不向模型发送玩家名称；文风采用夸张的开黑段子，
  强者会被“封神”，普通表现会被幽默调侃，较差表现则针对具体数据夸张吐槽。
- 仅在模型成功返回全部合规点评时自动发送；模型失败或输出不完整时整局不发送。
- 单局去重，发送间隔不低于 2.2 秒。

## 安装

需要 Windows、英雄联盟客户端和 Python 3.11+。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config.example.json config.json
```

在项目根目录创建 `key.md`，第一行填写 DeepSeek API Key，例如：

```text
sk-xxxxxxxx
```

程序优先读取 `key.md` 的第一个非空、非标题行，也兼容
`DEEPSEEK_API_KEY` 环境变量。`key.md` 已加入 `.gitignore`，密钥不会写入日志。

## 使用

### 双击启动

首次使用先双击 `安装依赖.cmd`，然后在项目根目录创建 `key.md`，第一行填写
API Key。之后直接双击 `启动助手.cmd`，脚本会请求管理员权限并自动使用项目
虚拟环境运行程序。

首次建议使用预览模式：

```powershell
python main.py --dry-run --once
```

如果使用 WeGame 启动客户端，WeGame 可能让 `LeagueClientUx.exe` 以管理员权限
运行。出现“当前终端无权读取 LCU 凭据”时，请关闭当前终端，右键
**Windows PowerShell -> 以管理员身份运行**，再进入项目目录执行上述命令。

确认分析结果后启用交互发送：

```powershell
python main.py
```

模型成功后程序会自动发送全部点评，无需按键确认。发送前会重新确认仍处于
选人阶段并刷新聊天会话；如果选人已经结束，则取消发送。

参数：

- `--config PATH`：指定配置文件，默认 `config.json`。
- `--dry-run`：真实分析并调用模型，但不发送聊天。
- `--once`：成功处理一个选人会话后退出。
- `--debug`：显示调试日志。
- `--print-default-config`：打印当前默认配置。

配置文件不存在时会使用内置默认值。`auto_send=false` 与 `--dry-run` 均会禁用发送。
默认最多等待队员信息 4 秒，并发抓取每人的 15 场详情。

## 运行说明

- 保持本工具运行后再进入匹配；客户端退出后程序会持续等待并自动重连。
- 优先从选人会话读取成员，并使用聊天系统消息补充；不足五人时仍会分析和发送
  已识别成员。
- 腾讯服队列号不在标准列表时，若标准筛选结果为空，会回退分析非云顶、非自定义的
  有效对局。使用 `--debug` 可查看历史数量、筛选数量和队列号。
- LCU 是客户端内部接口，版本更新可能导致字段变化。使用前请遵守 Riot
  服务条款及所在地区规则。

## 测试

```powershell
python -m unittest discover -v
```

## 打包发布

双击 `打包发布.cmd`。脚本会安装 PyInstaller、构建目录包并生成：

```text
dist\LOL-Roast-Assistant.zip
```

把该 ZIP 发给其他人即可。发布包不会包含你的 `key.md`；使用者需要将
`key.example.md` 重命名为 `key.md`，并填写自己的 DeepSeek API Key。

## 致谢与许可

LCU 接入和战绩评分思路参考
[`real-web-world/hh-lol-prophet`](https://github.com/real-web-world/hh-lol-prophet)，
该项目采用 MIT License。当前项目为独立 Python 实现，详见
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
