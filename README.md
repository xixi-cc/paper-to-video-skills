# 论文分享工作流 Skills

本仓库是论文到演示文稿工作流面向 Codex Desktop/WSL 的适配版本。项目以 Beamer 为主要幻灯片格式，并保留原有的 Skill、脚本、模板和资源目录结构。

使用本工作流制作的论文解读视频发布在
[溪溪-cc 的哔哩哔哩主页](https://space.bilibili.com/628726196)。

## 项目来源与改编

这套 Skills 的原始版本来自 B 站 UP 主
[白拾的物理AI组会](https://space.bilibili.com/98639326)（亦称“白拾的物理组会”）。感谢原作者设计并分享论文解析、Beamer 幻灯片、视频制作和哔哩哔哩投稿工作流。

本仓库维护者 [溪溪-cc](https://space.bilibili.com/628726196) 在该版本基础上，根据自己的实际使用情况进行了修改，主要面向：

- Codex Desktop、Codex CLI 与 WSL/Linux 环境；
- 物理与人工智能交叉方向的论文阅读、组会汇报和视频分享；
- 可复现的本地依赖配置、IndexTTS2 配音、质量检查和发布安全边界。

因此，本仓库是针对个人科研工作流制作的 Codex 适配与扩展版本，不是完全独立创作的原始 Skill 套件，也不代表原作者或其频道对本仓库提供官方背书。

原始 Skill 套件及本仓库维护者在其基础上新增或修改的内容，经原作者明确书面授权，采用 [MIT 许可证](LICENSE)发布。该授权允许修改、公开再分发并以 MIT 许可证发布；授权记录由维护者留存。另行列出的第三方模板、模型、工具和服务仍适用各自的条款；安装、使用或再分发前请阅读
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本仓库不包含模型、凭据、虚拟环境以及生成的论文或视频产物。合成语音 Voice 319 的参考音频采用单独的
[CC BY 4.0 许可证](VOICE_LICENSE.md)发布，详情见其
[可复现性说明](pdf-slides-to-video/references/voice-319.md)。

## 工作流

```text
论文 PDF
  → pdf-to-markdown
  → paper-to-beamer
  → pdf-slides-to-video
  → 可选：markdown-to-video-cover 海报
  → 可选：bilibili-video-uploader 投稿
```

`pdf-to-bilibili` 负责组织完整工作流；`sustech-beamer-theme-fix` 用于诊断 Beamer 主题和编译问题。

## 快速安装

### 1. 克隆仓库

将仓库克隆到一个稳定位置：

```bash
git clone https://github.com/xixi-cc/paper-to-video-skills.git \
  "$HOME/.local/share/paper-to-video-skills"
cd "$HOME/.local/share/paper-to-video-skills"
```

### 2. 让 Codex 发现这些 Skills

Codex 会从 `~/.agents/skills` 发现用户级 Skills，并支持符号链接形式的 Skill 目录。下面的命令会链接全部 7 个 Skills，同时避免复制它们共用的脚本、模板和资源：

```bash
mkdir -p "$HOME/.agents/skills"
repo_root="$HOME/.local/share/paper-to-video-skills"

for skill in \
  bilibili-video-uploader \
  markdown-to-video-cover \
  paper-to-beamer \
  pdf-slides-to-video \
  pdf-to-bilibili \
  pdf-to-markdown \
  sustech-beamer-theme-fix
do
  target="$HOME/.agents/skills/$skill"
  if [ -e "$target" ] || [ -L "$target" ]; then
    printf '跳过已存在路径：%s\n' "$target"
  else
    ln -s "$repo_root/$skill" "$target"
  fi
done
```

也可以让 `$skill-installer` 从 GitHub 仓库安装选定的 Skills。若新安装的 Skill 没有出现，再重启 Codex。Skill 的发现位置和调用方式以当前的
[OpenAI Skills 构建文档](https://learn.chatgpt.com/docs/build-skills)为准。

### 3. 安装运行依赖

完成上述链接后，Codex 可以立即发现这些 Skills；但论文解析、TeX、音频、视频和投稿阶段仍需要独立的系统工具和 Python 环境。运行完整工作流前，请按照
[ENVIRONMENT.md](ENVIRONMENT.md)配置环境。本仓库不提供模型、凭据、哔哩哔哩 cookies 或私有配置。

## 最小示例

安装 Skills 后，在包含论文的工作区中启动 Codex，并显式调用其中一个阶段：

```text
使用 $pdf-to-markdown 将 /absolute/path/to/paper.pdf 转换为结构化 Markdown。
保持源 PDF 不变，并将输出写到论文旁边的独立目录。
```

配置好 TeX、FFmpeg、Poppler、IndexTTS2 和 G2PW 后，可以运行完整的分阶段工作流：

```text
对 /absolute/path/to/paper.pdf 使用 $pdf-to-bilibili。
生成并验证 Markdown、Beamer 幻灯片和配音视频，但不要投稿到哔哩哔哩。
```

投稿始终是可选操作，只有用户明确要求上传或发布时才会执行。

## Skill 目录

| Skill | 功能 |
| --- | --- |
| `pdf-to-markdown` | 从论文中提取结构化 Markdown、公式、表格和图片。 |
| `paper-to-beamer` | 创建并逐页检查能够独立阅读的 SUSTech Beamer 幻灯片。 |
| `pdf-slides-to-video` | 生成与页面对齐的讲稿和语音，并组装经过验证的 MP4。 |
| `markdown-to-video-cover` | 创建可选的宣传海报；它不会取代 Beamer 标题页视频封面。 |
| `bilibili-video-uploader` | 校验元数据、执行预演、上传并核验经过明确授权的投稿。 |
| `pdf-to-bilibili` | 协调整个分阶段工作流及其人工检查关口。 |
| `sustech-beamer-theme-fix` | 诊断主题、资源路径、宏定义和 TeX 编译故障。 |

## 许可证摘要

| 内容 | 许可证或适用条款 |
| --- | --- |
| 本仓库维护者独立新增或修改的原创代码和文档 | [MIT 许可证](LICENSE) |
| 来自“白拾的物理AI组会”的原始 Skill 套件及其衍生内容 | [MIT 许可证](LICENSE)；原作者已明确书面授权修改、公开再分发并以 MIT 许可证发布，授权记录由维护者留存 |
| `pdf-slides-to-video/assets/voices/voice-319-reference.wav` | [CC BY 4.0](VOICE_LICENSE.md) |
| SUSTech 幻灯片模板 | MIT；再分发时须保留其[本地许可证](sustech-slides-template/LICENSE)和作者声明 |
| 基于 Gemini 修改的 Beamer 海报主题 | MIT；参见[第三方许可证副本](third_party_licenses/GEMINI-MIT.txt) |
| IndexTTS2 源码、模型权重及生成输出 | 适用上游单独的 Bilibili Model Use License，不属于本仓库 MIT 许可证的授权范围 |
| 其他外部工具、模型、字体和服务 | 分别适用各自的上游条款 |

再分发或部署前，请阅读 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。仓库级 MIT 许可证覆盖已获原作者授权的 Skill 套件及本仓库贡献者拥有权利的修改内容，但不会额外授予外部模型、服务、生成语音输出或上述范围以外第三方资源的使用权。

## Codex 运行约定

系统依赖、隔离运行环境、私有配置路径和验证命令见
[ENVIRONMENT.md](ENVIRONMENT.md)。

- 在当前工作区内运行；相邻 Skills 的位置应相对于本仓库解析。
- 使用官方 PDF Skill 检查源文件和渲染后的页面。
- 使用 `latex:latex-doctor` 和 `latex:latex-compile` 发现并调用 TeX 环境。
- 使用 `uv sync --project pdf-slides-to-video` 创建视频处理环境。
- 只使用本地 IndexTTS2、G2PW 发音审计和仓库内置参考语音 Voice 319 生成旁白。CUDA 运行环境和模型必须放在 Skill 目录之外，并通过 `~/.config/article-to-video/tts.json` 配置。
- 新生成的视频保留 TTS 原生语速，并在 FFmpeg 合成阶段默认应用 1.25 倍播放速度；不会自动重写既有视频。
- 通过 `PATH` 或 Codex 捆绑的工作区运行环境发现 `python`、`latexmk`、`xelatex`、`lualatex`、`pdftoppm`、`ffmpeg` 和 `ffprobe`。
- 保持源 PDF 不变，将生成物写入明确指定的论文或输出目录。
- 不要在仓库中保存凭据。哔哩哔哩 cookies 应放在 `~/.bilibili/cookies.json`。
- 用户明确请求 `bilibili` 模式即视为上传授权。应先执行校验和预演，再提交投稿，不重复弹出第二次确认。
- 每条哔哩哔哩视频简介以 `一句话概述：本文……；其重要性在于……。` 开头，随后提供简短、通俗的视频介绍。
- 批量处理论文时，使用 `pdf-to-bilibili/scripts/batch.py`：它会持续清空 CPU 准备队列，将所有准备完成且缓存失效的页面交给单个批次级 GPU worker，并在每篇论文的音频完成后立即启动该论文的视频处理和质量检查。队列清空后，GPU worker 会自动退出。
- 每篇新论文都必须创建 `paper_presentation.json`。它是 Beamer 元数据和帧内容、旁白和证据审计、哔哩哔哩投稿元数据的唯一内容来源。
- 每个批次只加载一次 IndexTTS2，并保持 GPU 推理串行执行。模型推理前先完成 G2PW 发音预检；标准化音频完成后发送页面和论文完成事件；一篇论文完成后立即将其交给共享后处理队列，同时后续论文继续执行 TTS。TTS 音频标准化 worker 应占用统一配置的 FFmpeg 总预算；若总预算无法同时支持两个池，则推迟后处理直至 TTS 结束。XeLaTeX 需要单独限流，不能按论文重复扩增 worker 池。

## 主要输出

- Beamer：`main.tex`、`main.pdf`、`figures/`、`sustech-theme/`
- 视频：`video_frames/`、旁白文本、MP3 音频、配音 MP4、封面和元数据
- 可选海报：`poster.tex`、`poster.pdf`、`poster.png`

每份幻灯片都必须成功编译并逐页进行视觉检查。每个视频都必须为渲染后的每一页 PDF 提供一组对应的旁白文本和音频，并通过 `ffprobe` 验证。

每张实质性幻灯片即使没有旁白也应能够独立理解：页面上需要明确展示研究对象或问题、证据或机制，以及可见的核心结论。批量运行在进入 TTS 或发布前，还必须进行一次静音五秒可读性检查，确保不存在信息过于稀疏的页面。

## 开发与发布验证

发布改动前，在仓库根目录运行：

```bash
python3 scripts/validate_skills.py
python3 -m unittest discover -s tests -q
python3 scripts/check_markdown_links.py
python3 scripts/check_python_syntax.py
bash -n pdf-slides-to-video/scripts/setup_indextts2_runtime.sh
```

GitHub Actions 会在每次 push 和 pull request 时运行 Skill 校验、Python 语法检查和回归测试、Shell 语法检查以及本地 Markdown 链接检查。

不要将 `.venv/`、缓存、凭据、模型、私有或自定义参考语音、日志和生成物加入提交。Voice 319 是仓库中唯一有意保留的音频资源。上传和撤稿命令不得用作冒烟测试。贡献流程见
[CONTRIBUTING.md](CONTRIBUTING.md)，私密漏洞报告方式见
[SECURITY.md](SECURITY.md)。
