# link2md

把一条链接整理成一篇 Obsidian 笔记。粘贴哔哩哔哩、小宇宙、微信公众号或普通网页的分享文案，程序提取正文（视频和播客会优先用字幕，否则转写音频），可选地用大模型整理成摘要、要点和标签，然后把 Markdown 写进你的仓库。

项目目标、当前进度、验收项和后续里程碑见 [docs/PLAN.md](docs/PLAN.md)。

## 安装

需要 Python 3.11 及以上，以及 `ffmpeg`（云端转写、部分音频切分会用到）。

```bash
pip install -e .
```

只要本地转写或阿里云转写时再装可选依赖：

```bash
pip install -e ".[asr]"     # faster-whisper
pip install -e ".[cloud]"   # dashscope（Paraformer）
```

安装后命令是 `link2md`，也可以 `python -m link2md`。

## 配置

```bash
link2md init
```

Linux 上会写到 `~/.config/link2md/config.yaml`。模板是 [`config.example.yaml`](config.example.yaml)（与 `src/link2md/resources/config.example.yaml` 相同）。已有文件时加 `--force` 才会覆盖。

至少填写 Obsidian 仓库路径：

```yaml
vault:
  path: ~/Obsidian/MyVault
  notes_dir: link2md
  attachments_dir: link2md/attachments
```

也可以不改文件，直接设环境变量 `LINK2MD_VAULT`。指定别的配置文件用 `--config` 或 `LINK2MD_CONFIG`。

密钥放在环境变量里，不要写进配置：

| 变量 | 用途 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 默认的 DeepSeek 接口。变量名可用 `llm.api_key_env` 改 |
| `DASHSCOPE_API_KEY` | `asr.backend` 为 `dashscope` 时使用 |
| `LINK2MD_ASR_BACKEND` | 临时改成 `faster-whisper` 或 `dashscope` |
| `LINK2MD_VAULT` | 覆盖 `vault.path` |

模型层走 OpenAI 兼容的 Chat Completions。默认是 DeepSeek：

- `base_url`: `https://api.deepseek.com`
- `model`: `deepseek-flash`（2026-07-24 之后 `deepseek-chat` 已停用）

换其他兼容服务时，改 `llm.provider`、`llm.base_url`、`llm.model`、`llm.api_key_env` 即可。

检查环境：

```bash
link2md doctor
```

## 用法

```bash
link2md "https://www.bilibili.com/video/BVxxxx"
link2md "【分享】https://b23.tv/xxxx 点击观看"
link2md "https://www.xiaoyuzhoufm.com/episode/xxxx"
link2md "https://mp.weixin.qq.com/s/xxxx"
link2md "https://example.com/post/1"

link2md --no-llm "https://mp.weixin.qq.com/s/xxxx"   # 不调用模型
link2md --update "https://mp.weixin.qq.com/s/xxxx"   # 覆盖已保存的同一链接
link2md --asr dashscope "https://www.bilibili.com/video/BVxxxx"
```

分享文案里只要能找到第一个 `http(s)` 链接即可。`b23.tv` 会先尝试展开。同一条规范链接（去掉追踪参数之后）默认跳过；配置 `duplicate_policy: update` 或加上 `--update` 会覆盖原笔记。

成功时标准输出一行路径：

```text
已保存：~/Obsidian/MyVault/link2md/标题-a1b2c3d4.md
```

## 笔记里有什么

YAML front matter：

- `title`、`platform`（`bilibili` / `xiaoyuzhou` / `wechat` / `web`）
- `author`、`source_url`、`publish_date`（页面能解析到才写）
- `saved_at`、`tags`、`content_type`（`video` / `audio` / `article`）
- `text_source`：`article`、`subtitle:zh-Hans`、`subtitle:ai-zh`、`asr:faster-whisper` 等

正文顺序是摘要、要点、节目介绍（有简介或 shownotes 才有）、全文。图片下载到附件目录，Markdown 里改成相对路径。微信图片请求会带 `Referer: https://mp.weixin.qq.com/`，避免公众号图床的防盗链。

去重索引用笔记目录里的 `.link2md-index.json`。索引丢了会再扫这个目录下笔记的 `source_url`。

## 各平台怎么取正文

| 平台 | v1 行为 |
| --- | --- |
| 哔哩哔哩 | yt-dlp 读元数据。字幕优先人工中文，其次 `ai-zh` 等 AI 字幕，再是英文。没有字幕就下音频并转写 |
| 小宇宙 | 公开单集页的 `og:audio` 和 `__NEXT_DATA__` 里的 `enclosure.url`。有正文转写就直接用，否则下载 m4a 再转写。只支持 `/episode/` 链接 |
| 微信公众号 | 用微信内置浏览器 UA 拉页面，正文在 `#js_content`，图片用 `data-src` |
| 其他网页 | trafilatura 抽正文，抽不到再用页面结构兜底 |

抖音、小红书会直接提示 v2 再做，不会当成普通网页去抓。配置里的 `cookies.douyin` 和 `cookies.xiaohongshu` 是预留位。

B 站如果要登录态，把 Netscape 格式的 `cookies.txt` 填到 `cookies.bilibili`（yt-dlp 的 `cookiefile`）。字幕接口经常要求登录；匿名请求在部分网络上还会直接返回 HTTP 412。

## 转写

`asr.backend`：

- `faster-whisper`：本地模型，默认 `small` / `cpu` / `int8`。模型缓存在缓存目录的 `whisper/` 下。
- `dashscope`：阿里云百炼 Paraformer。文件转写接口 `paraformer-v2` 要求公网 URL，所以本地文件走 `paraformer-realtime-v2` 的 `Recognition.call(路径)`。长音频会先转成 16 kHz 单声道 WAV，再按 `chunk_seconds`（默认 600 秒）切段。

新增一个后端：实现 `ensure_available` 和 `transcribe`，在 `link2md.asr.create_transcriber` 里登记。

## 模型整理

有 API Key 时，模型会整理标点和段落，并生成摘要、要点、标签。超过 `llm.chunk_chars`（默认 8000）会分段整理再合并摘要。图片和代码块会换成占位符，模型若把占位符弄丢或把正文砍得过短，这一段会保留原文。

没配密钥、加了 `--no-llm`、或接口失败时，笔记仍会保存，摘要处会写明原因。

## 缓存和日志

默认缓存目录是系统缓存（Linux 为 `~/.cache/link2md`），里面有下载的音频、日志 `link2md.log`。`link2md -v` 会把调试日志打到终端。

## 扩展点

- 平台解析器：一个平台一个模块，在 `src/link2md/parsers/registry.py` 的 `builtin_parsers()` 里注册。抖音 / 小红书实现后从 `_RESERVED` 挪进来，并读取对应的 cookie 文件。
- 转写：`src/link2md/asr/`。
- 模型：任何 OpenAI 兼容接口，只改配置。

## 路线图

完整的里程碑、勾选任务、验收标准和风险在 [docs/PLAN.md](docs/PLAN.md)。摘要如下：

- v1 收尾：用真实环境跑通 `faster-whisper`、DashScope、DeepSeek 整理，以及带登录 Cookie 的 B 站
- v2：抖音、小红书、Cookie 管理、任务队列和失败重试
- 再往后：SQLite 全文检索、语义检索、基于笔记的问答

## 已知限制

这些是对照当前页面和工具实际行为写的，不是假设。

- 本环境里，yt-dlp 2026.08.19 请求 `https://www.bilibili.com/video/BV1GJ411x7h7` 以及 B 站公开 view 接口，匿名访问都是 HTTP 412。程序会把这个错误说清楚，并提示配置 `cookies.bilibili`。字幕列表即使页面能打开，也经常要登录（yt-dlp 的 B 站提取器会看 `need_login_subtitle`）。`ai-zh` 在 yt-dlp 里目前放在普通 `subtitles`，不在 `automatic_captions`，选择顺序已经按这个实现。
- 小宇宙公开单集（抽查 `episode/67164e0d0d2f24f289c01c1e`）能直接拿到 `og:audio` 和 `enclosure.url`，CDN 支持 Range 下载。这一集的 `transcript` 只有 `mediaId`，没有正文，所以会走转写。付费或私密单集没有音频直链。
- 微信文章在带 MicroMessenger UA 时能拿到 `#js_content`、`#activity-name`、`#js_name` 和 `create_time`。图片在 `mmbiz.qpic.cn`，带 `wx_fmt`。笔记里改为本地文件，是因为公众号图床按 Referer 做防盗链；在这台机器上，同一张样图不带 Referer 也返回了 200，但 Obsidian 打开远程链接时仍然可能被拦。
- 验证页、失效的微信链接、需要登录的网页，会得到明确错误，而不是空笔记。
- 单元测试不访问网络，也不调用真实的模型或转写。
