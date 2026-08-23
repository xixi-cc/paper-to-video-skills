# 📊 SUSTech Beamer 幻灯片模板

**学术报告 · 论文分享 · 课题答辩一站式中英文 LaTeX Beamer 模板**

> 基于标准 Madrid 主题，采用专业学术蓝与低饱和绯红重新设计。附带即用型幻灯片模板及 `latexmkrc`，**无需系统安装**即可编译。

> A reusable Beamer theme for academic talks, recolored with a low-saturation palette. Zero system install — just clone and `latexmk`.

> 👤 **杨昊波 (Haobo Yang)** — 2026 届计算机系博士 · [github.com/yhbcode000](https://github.com/yhbcode000) · yhbcode000@foxmail.com
> 支持中文 (CJK) 排版 via `ctexbeamer` + **XeLaTeX**

---

## 🎯 适用场景 | Use Cases

本模板适用于以下所有学术报告类型，覆盖课题组全流程：

| 🏷️ 场景 | 说明 |
|:---|:---|
| 📄 **论文分享** Paper Share | 组会文献精读，含方法、实验、贡献分析 |
| 🌏 **领域调研** Region Survey | 研究方向综述，含文献对比、趋势总结 |
| 📝 **开题答辩** Proposal | 课题背景、技术路线、预期结果 |
| 📊 **进展记录** Progress Record | 阶段成果汇报、问题与下一步计划 |
| 🎓 **结题汇报** Finalisation | 完整工作总结、发表成果、未来方向 |

---

## 📂 报告结构样例 | Sample Structures

点击展开每种报告的建议章节结构 👇

<details>
<summary>📄 <b>论文分享 | Paper Share</b> — 组会文献精读结构</summary>

```
📄 论文信息页 (标题、作者、期刊/会议、年份)
📋 背景与动机 (Background & Motivation)
🎯 问题定义 (Problem Formulation)
🔧 方法 (Method / Approach)
🧪 实验设计 (Experimental Setup)
📈 结果与分析 (Results & Analysis)
💡 核心贡献 (Contributions)
⚠️ 局限与讨论 (Limitations & Discussion)
📚 参考文献 (References)
💬 Q&A / 讨论
```

</details>

<details>
<summary>🌏 <b>领域调研 | Region Survey</b> — 研究方向综述结构</summary>

```
🌏 研究背景与范围 (Research Scope)
📊 文献分类框架 (Taxonomy / Categorization)
📋 代表性工作详述 (Method-by-method Breakdown)
📈 性能对比总表 (Benchmark Summary)
🔍 研究方向趋势 (Trends & Emerging Topics)
💡 开放问题与机遇 (Open Problems)
📚 引用文献 (Bibliography)
```

</details>

<details>
<summary>📝 <b>开题答辩 | Proposal</b> — 课题立项结构</summary>

```
📝 题目与摘要 (Title & Abstract)
🎯 研究背景与意义 (Motivation)
📚 相关工作 (Related Work)
🔧 技术路线与方案 (Technical Approach)
📅 时间规划 (Timeline / Gantt)
🎯 预期成果与创新点 (Expected Contributions)
📚 参考文献 (References)
💬 Q&A
```

</details>

<details>
<summary>📊 <b>进展记录 | Progress Record</b> — 阶段汇报结构</summary>

```
📊 阶段概览 (Progress Overview)
✅ 已完成工作 (Completed Tasks)
🔧 当前方案细节 (Technical Details)
📈 初步实验结果 (Preliminary Results)
⚠️ 遇到的问题 (Blockers & Issues)
📅 下一步计划 (Next Steps)
💬 讨论 & 建议 (Discussion)
```

</details>

<details>
<summary>🎓 <b>结题汇报 | Finalisation</b> — 最终答辩结构</summary>

```
🎓 题目与研究问题 (Title & Research Questions)
📋 背景与相关工作 (Background & Literature)
🔧 方法总览 (Method Overview)
🧪 实验设计与结果 (Experiments & Key Results)
📈 消融/对比分析 (Ablation & Comparison)
💡 贡献与创新 (Contributions)
📝 发表成果 (Publications / Outputs)
🔮 未来方向 (Future Work)
🙏 致谢 (Acknowledgements)
💬 Q&A
```

</details>

---

## 👁️ 预览 | Preview

运行 `latexmk -xelatex main_template.tex` 生成本地预览
`main_template.pdf`。PDF 是构建产物，不随源码仓库分发。

---

## 📁 仓库结构 | Repository Layout

```
.
├── main_template.tex                     # ⭐ 空白起手模板 — 复制为 main.tex
├── latexmkrc                             # 自动添加 ./sustech-theme// 到 TEXINPUTS
├── .gitignore
└── sustech-theme/
    ├── beamerthemesustech.sty            # 主主题：Madrid + 配色 + 元素
    ├── beamercolorthemesustech.sty       # 学术配色方案
    └── beamerthemesustech-elements.sty   # 宏、callout、表格、章节分隔页
```

---

## 🚀 快速开始 | Quick Start

1. 将 `main_template.tex` 复制为 `main.tex`，替换所有 `〈…〉` 占位符
2. 将图片放入 `figures/` 文件夹，把 `\phfig` 替换为 `\fitfigure{your_image}`
3. 用 XeLaTeX 编译（`latexmkrc` 自动配置主题路径）：

```bash
latexmk -xelatex main.tex
```

最小化导言区：

```latex
\documentclass[aspectratio=1610,10pt]{ctexbeamer}  % Codex 论文分享默认使用 16:10
\usetheme{sustech}
\title[短标题]{中文主标题}
\subtitle{English subtitle}
\author[汇报人]{汇报人姓名}
\institute[机构]{机构 · 会议/期刊}
\date{YYYY-MM-DD · 地点}
\begin{document}
% ... frames ...
\end{document}
```

🔁 移植到别处：将 `sustech-theme/` **和** `latexmkrc` 复制到你的 `main.tex` 旁边，然后 `\usetheme{sustech}`。

---

## 🖥️ 幻灯片比例 | Aspect Ratio

比例由 `\documentclass` 的 `aspectratio` 选项控制（beamer 要求在文档类处设置）。**只改这一个数值即可**，标题页与所有排版宏都按相对宽度自适应，正文无需改动：

```latex
\documentclass[aspectratio=1610,10pt]{ctexbeamer}  % 改 1610 为下表数值
```

| 比例 | 选项值 | 适用场景 | 推荐 |
|:---|:---|:---|:---:|
| **16:9** | `aspectratio=169` | 宽屏、会议 / 投影默认 | ✅ |
| **16:10** | `aspectratio=1610` | 部分笔记本 / 投影 | ✅ |
| **4:3** | `aspectratio=43` | 老式投影 / 教室白板 | ✅ |
| 其它 | `149` · `54` · `32` · `1410` | 14:9 · 5:4 · 3:2 · 14:10 | |

> 💡 不确定就用 **16:9**（`169`）——当前主流投影与在线会议的默认比例。

---

## 🎨 配色方案 | Color Scheme

| 角色 | 色彩 | Hex | 用途 |
|:---|:---|:---|:---|
| 🔵 主色 (深) | 深海军蓝 | `#1F4E79` | 页框标题、章节标题、表头、标题页 |
| 🔵 主色 (标准) | 学术蓝 | `#2F6B8A` | Block 标题、页脚中部 |
| 🔵 主色 (辅助) | 中间蓝 | `#3A708C` | 页脚第三级、辅助 |
| 🔴 强调色 | 学术绯红 | `#B3263B` | 关键词、强调、编号、项目符号、Callout 标题 |
| 🟥 强调色 2 | 柔和红 | `#D1495B` | `\hlbox` 浅红行内高亮 |
| 🟢 辅助色 | 灰绿 | `#526F61` | Example-block 标题 |
| ⬜ 辅助色 | 浅灰 | `#E7EAEE` | 表格交替行、卡片 |
| ⬜ 辅助色 | 柔和灰 | `#F5F7FA` | Block 主体 |
| ⬜ 背景 | 白 | `#FFFFFF` | 页面 |
| ⬛ 正文 | 深灰 | `#222B35` | 普通文本 |

---

## 🛠️ 宏与环境 | Macros & Environments

| 命令 | 功能 |
|:---|:---|
| `\shl{...}` | 🟠 强调（橙色粗体） |
| `\keyword{...}` | 🟠 关键词（橙色粗体） |
| `\brandemph{...}` | 🟠 强调（橙色斜体） |
| `\hlbox{...}` | 🟡 金色行内高亮（关键数字） |
| `\metric{num}{label}` | 🔢 大数字 + 说明（统计行） |
| `\fitfigure{file}` | 🖼️ 溢出安全图（宽度 + 最大高度） |
| `\figcap{n}{text}` | 📝 图注 "图 n: text"（编号不会换行） |
| `\paperfigure{file}{label}{caption}{takeaway}` | 📄 论文图专页内容；外层 frame 用 `[plain,c]` |
| `\equationderivation{conditions}{aligned rows}{meaning}{takeaway}` | 🧮 方程推导页内容 |
| `\baselinecomparison{condition}{metric}{baseline}{paper}{delta}{takeaway}` | 📊 基线比较页内容 |
| `\begin{callout}[title] ... \end{callout}` | 📦 要点框（橙色 alertblock） |
| `\theadrow` / `\altrow` / `\thc{...}` | 📋 表头行 / 交替行 / 表头单元 |
| `\zonetext` `\zonefig` `\zonehalf` | 📐 列宽 (0.55 / 0.42 / 0.48) |
| `\tightgap` / `\deckgap` | ↔️ 统一垂直间距 |

三个语义宏只负责 `frame` 内部内容，不会创建嵌套页面。由
`paper_presentation.json` 生成页面时，分别使用 `kind: "figure"`、
`kind: "equation"`、`kind: "comparison"`；论文图页还必须设置
`frame_options: "plain,c"`。完整示例见
[`paper-to-beamer/references/semantic-frame-macros.md`](../paper-to-beamer/references/semantic-frame-macros.md)。

### 📑 章节分隔页带一句话摘要

每个 `\section` 自动生成分隔页（第 N 部分 + 标题 + 分隔线）。在 `\section` **之前**设置 `\secblurb` 可为该 Section 添加论文一句话概括：

```latex
\renewcommand{\secblurb}{这一节用一句话概括本文在该部分的核心思想。}
\section{方法}
```

### 🏷️ 图注前缀

默认 `图`；全局修改：`\setfigureprefix{Figure}`。

---

## ⚙️ 自定义 | Customization

```latex
% 作者信息宏（已定义，不自动渲染 — 自行放置）：
\setcreditauthor{Your Name}
\setcreditgithub{github.com/you}
\setcreditemail{you@example.com}
```

---

## 📦 依赖 | Requirements

- **XeLaTeX**（CJK 需要 `ctexbeamer`）；推荐 `latexmk`
- TeX Live / MiKTeX 含 `beamer`, `ctex`, `booktabs`, `colortbl`, `graphicx`, `amsmath`
- 无需系统安装主题 — `latexmkrc` 自动处理路径

---

## 📜 许可 | License

[MIT](LICENSE) © 2026 杨昊波 (Haobo Yang)

