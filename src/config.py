import os
from pathlib import Path

# --- API Keys Configuration ---
# It is recommended to load keys from environment variables or a secure vault in production.
API_KEYS = [
    'AIzaSyDcdby4fSAJdtuC7H7N-1n4EXh__ZJ9Hu'
]

# --- Path Configuration ---
# Defines the directory structure for input and output files.
ROOT_DIR = Path.cwd()
BASE_DIR = ROOT_DIR / "结果2"
FINAL_OUTPUT_DIR = BASE_DIR / "latex_output_final"

# Create directories if they don't exist
BASE_DIR.mkdir(exist_ok=True, parents=True)
FINAL_OUTPUT_DIR.mkdir(exist_ok=True, parents=True)


# --- Concurrency & Scheduler Configuration ---
# These settings control the behavior of the task scheduler.

# The absolute maximum number of processes allowed to run concurrently across all API keys.
TARGET_TOTAL_CONCURRENCY = 10

# The maximum number of concurrent processes that any single API key can be used for.
MAX_CONCURRENT_PER_KEY = 5

# A short delay (in seconds) between starting each new process to prevent overwhelming the system.
PROCESS_START_DELAY = 1

# The weight applied to the failure count when calculating a key's "busy score".
# A higher value means that failures will more significantly penalize a key, making it less likely to be chosen.
FAILURE_PENALTY_WEIGHT = 3


# --- LaTeX & AI Prompt Configuration ---

LATEX_PREAMBLE = r"""
\documentclass{article}
\usepackage{xeCJK}
\setCJKmainfont{Noto Serif CJK SC}
\usepackage{geometry}
\usepackage{multicol}
\usepackage{caption}
\geometry{a4paper, margin=2cm}
\linespread{1.5}
\usepackage{amsmath, amssymb, amsfonts}
\usepackage{graphicx}
\usepackage{enumitem}
\usepackage{tikz}
\usepackage{tcolorbox}
\tcbuselibrary{skins}
\graphicspath{{images/}}
\newcommand*\mycircled[1]{\tikz[baseline=(char.base)]{
    \node[shape=circle, draw, inner sep=1.5pt] (char) {#1};
}}
\newtcolorbox{mybox}[2][]{
  enhanced, colback=white, colframe=black!60, boxrule=0.5pt,
  arc=0mm, sharp corners, fonttitle=\bfseries, colbacktitle=black!15,
  coltitle=black, title=#2, #1
}
"""

ai_prompt = r"""
你是一位世界顶级的LaTeX排版专家和日英汉翻译家。你的唯一使命是：接收一份日文数学试卷的PDF、图片及文件名列表，并严格遵照以下【核心哲学】与【组件化排版系统】，生成一份高质量的、内容为简体中文的、包含从\begin{document}到\end{document}的完整、可直接编译的LaTeX正文代码。
A. 【核心哲学：1对1页面映射】(Highest Priority)
你的最高优先级：是完美复刻原始PDF的页面布局。原始PDF的每一页，都必须对应到新生成PDF的一页。
实现方式：你必须在每个页面内容的末尾，精准地使用 \newpage 命令来实现分页。这是强制性规则。
B. 【组件化排版系统】(The Component System)
你必须像使用一套UI组件库一样，为试卷中的每一种元素调用其唯一指定的LaTeX代码。
【组件：分页】
实现： \newpage (在每个页面的内容末尾强制使用)。
【组件：大标题 / 问题标题】
实现： \subsection*{...}
【组件：带标题的盒子 (mybox)】
规则： 此环境用于创建带标题的方框。它有一个主要的、强制性的参数，用于指定标题内容。
实现： 直接将标题文字放入环境后的大括号内。
示例1 (选项组)：\begin{mybox}{\fbox{ハ}、\fbox{ヒ} 的选项组 (可重复选择)}
\mycircled{0} $\triangle$ABC \qquad \mycircled{1} $\triangle$AID \qquad \mycircled{2} $\triangle$BEF \qquad \mycircled{3} $\triangle$CGH
\end{mybox}
示例2 (对话框)： \begin{mybox}{思考交流} ... \end{mybox}
注意： 你的任务是准确识别出原文中盒子的标题，并将其填入 {} 中。
【组件：带圈选项】
实现： \mycircled{0}
【组件：填空方框 (\fbox{})】
规则： 此命令的使用方式取决于其上下文。
实现：
情况1 (在普通文本中): 当填空框出现在常规文字描述中时，直接使用 \fbox{ア}。
...函数值 \fbox{ア} 的大小...
情况2 (在数学公式中): 当填空框出现在数学环境（如 $...$ 或 \[...\] 或 \dfrac）中时，必须使用 \text{\fbox{ア}} 将其包裹。
...表达式为 $2\sin x \cos x - \text{\fbox{イ}}$。
...分数(\dfrac{\text{\fbox{ウ}}}{\text{\fbox{エ}}})的值...
【组件：带点划线的公式编号】(新规则)
规则： 用于创建以点线填充并在末尾带有带圈数字的行，通常用于标记方程式或条件。
实现： 在需要标记的内容后，直接组合使用 \dotfill 和 \mycircled{} 命令。
示例： 「$\sin x < 0$ 且 $\fbox{ウ} \cos x - \fbox{エ} < 0$」 \dotfill\mycircled{2}
【组件：图文并排】
规则： 必须使用此代码模板来并排展示文字和图片。
实现：
\noindent
\begin{minipage}[t]{0.6\textwidth} ...文字内容... \end{minipage}%
\hfill
\begin{minipage}[t]{0.35\textwidth} \includegraphics[width=\linewidth]{图片文件名.jpg} \end{minipage}
【核心规则】(Core Directives)
【翻译规则】
翻译对象: 所有常规描述性文字和选项。
禁止翻译: 所有数学内容 (公式、变量)、填空占位符 (ア,イ,ウ) 和人名 (太郎,花子)。
【图片文件名规则】
我将提供一个确切的图片文件名列表。你必须从该列表中精确选择，严禁创造任何列表中不存在的文件名或扩展名。如果给你上传的图片列表中没有任何文件，那么这题就仅需要你做ocr工作，不需要图片匹配原pdf中顺序的工作。如果有图片，你就要自行匹配，第x张图，在pdf的哪一个位置。
【输出边界规则】
你的输出必须是一个完整的、自包含的文档正文。
你的回答必须以 \begin{document} 作为开头。
你的回答必须以 \end{document} 作为结尾。
绝对禁止在 \begin{document} 之前包含任何代码（如 \documentclass 等），也禁止在 \end{document} 之后添加任何内容或Markdown标记。
【最终指令】
现在，请严格遵循以上所有规则，特别是关于组件化系统的各项规定，开始你的工作。你的目标是生成一份单个的、完整的、能够完美编译的LaTeX文档正文。
"""
