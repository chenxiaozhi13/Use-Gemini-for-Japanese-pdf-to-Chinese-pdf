# ====================================================================================================
#
#                                     All-in-One 高并发智能编排器
#
# ====================================================================================================
#
# 作者: (您可以在这里写上您的名字或ID)
# 版本: 4.1 (内容修复 & 饱和式攻击模式)
# 描述: 本脚本是一个专为计算密集型和API密集型任务设计的、功能完备的多进程并发处理器。
#       它将原始的渲染逻辑与一个高级的、健壮的并发调度系统完美融合在一个文件中。
#
# ----------------------------------------------------------------------------------------------------
#                                         【v4.1 核心修复】
# ----------------------------------------------------------------------------------------------------
# - 修复了之前版本中遗漏了 LATEX_PREAMBLE 和 ai_prompt 完整内容的严重错误。
#   本版本是功能完整、可直接运行的最终版。
#
# ----------------------------------------------------------------------------------------------------
#                                         【核心功能：饱和式攻击模式】
# ----------------------------------------------------------------------------------------------------
# 1. 集中火力 (Concentrated Firepower):
#    脚本【逐个】处理待办任务。对于每一个待办任务，它会启动一个“攻坚小组”，
#    让【所有API Key】同时、并行地处理这【同一个任务】。
#
# 2. 协作式竞争与提前退出 (Collaborative Competition & Early Exit):
#    所有进程竞争第一个成功编译出PDF。一旦有进程成功，它会升起一个全局“成功信号旗”，
#    所有其他进程检测到信号后会立即停止工作并退出，避免资源浪费。
#
# 3. 隔离工作区与成果移交 (Isolated Workspace & Result Promotion):
#    每个进程在隔离的临时目录中工作。“胜利者”进程负责将自己的成果正式移交到最终的输出目录。
# ====================================================================================================

import multiprocessing
import sys
import os
import shutil
import subprocess
from pathlib import Path
import time
import collections
import queue
import random
import google.generativeai as genai

# --- 1. 全局配置 ---
API_KEYS = [
    'AIzaSyDcdby4fSAJdtuC7H7N-1n4EXh__ZJ9Hu'
]

# --- 路径配置 ---
CURRENT_WORKING_DIR = Path.cwd()
BASE_DIR = CURRENT_WORKING_DIR / "结果2"
OUTPUT_DIR = BASE_DIR / "latex_output_final"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# --- LaTeX模板与AI指令 ---
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

# --- 核心业务逻辑 ---
def get_all_tasks():
    """生成所有可能任务的列表。"""
    tasks = []
    doc_types = ["问题", "解答"]
    for year in range(2021, 2025):
        for exam_type in ["1A", "2B"]:
            for q_num in range(1, 6):
                for doc_type in doc_types:
                    tasks.append((str(year), exam_type, str(q_num), doc_type))
    for q_num in range(1, 5):
        for doc_type in doc_types:
            tasks.append(("2025", "1A", str(q_num), doc_type))
    for q_num in range(1, 8):
        for doc_type in doc_types:
            tasks.append(("2025", "2BC", str(q_num), doc_type))
    return tasks

def process_and_render_question(year, exam_type, question_num, doc_type, lock, output_dir_override=None):
    """
    处理单个试题的核心函数。
    增加 output_dir_override 参数，允许在指定的临时目录中进行操作。
    """
    question_base_name = f"{year}-{exam_type}_第{question_num}問_{doc_type}"
    task_id = question_base_name 
    
    question_output_dir = output_dir_override if output_dir_override else OUTPUT_DIR / question_base_name
    question_output_dir.mkdir(exist_ok=True)

    source_pdf_path = BASE_DIR / f"{question_base_name}.pdf"
    source_folder_path = BASE_DIR / question_base_name
    source_image_dir = source_folder_path / "images"

    if not source_pdf_path.exists():
        print(f"注意: 源PDF文件未找到，跳过任务 -> {source_pdf_path}", flush=True)
        return True 

    try:
        prompt_parts = [ai_prompt]
        prompt_parts.append(genai.upload_file(path=source_pdf_path))
        if source_folder_path.exists() and source_image_dir.exists():
            image_files = sorted(list(source_image_dir.glob("*.jpg")))
            if image_files:
                image_list_prompt = "--- 可用图片文件列表 (必须使用) ---\n" + "\n".join([p.name for p in image_files]) + "\n--- 列表结束 ---\n"
                prompt_parts.append(image_list_prompt)
                for image_path in image_files:
                    prompt_parts.append(genai.upload_file(path=image_path))
        print(f"[{task_id}] 正在调用Gemini模型...", flush=True)
        model = genai.GenerativeModel(model_name="gemini-2.5-pro")
        response = model.generate_content(prompt_parts, request_options={"timeout": 600})
        raw_text = response.text.strip()
        if raw_text.startswith("```latex"): raw_text = raw_text[len("```latex"):].strip()
        if raw_text.endswith("```"): raw_text = raw_text[:-len("```")].strip()
        final_latex_code = LATEX_PREAMBLE + "\n" + raw_text
        output_tex_path = question_output_dir / "generated.tex"
        with open(output_tex_path, "w", encoding="utf-8") as f: f.write(final_latex_code)
        print(f"[{task_id}] LaTeX代码已保存到: {output_tex_path}", flush=True)
        if source_folder_path.exists() and source_image_dir.exists() and any(source_image_dir.iterdir()):
            target_image_dir = question_output_dir / "images"
            if target_image_dir.exists(): shutil.rmtree(target_image_dir)
            shutil.copytree(source_image_dir, target_image_dir)
        print(f"[{task_id}] 开始自动渲染PDF...", flush=True)
        for i in range(2):
            process = subprocess.run(["xelatex", "-interaction=nonstopmode", output_tex_path.name], cwd=question_output_dir, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            if process.returncode != 0:
                print(f"\033[91m[{task_id}] 错误: XeLaTeX 编译失败！日志见: {output_tex_path.with_suffix('.log')}\033[0m", flush=True)
                return False
        if output_tex_path.with_suffix('.pdf').exists():
            try:
                shutil.copy(source_pdf_path, question_output_dir)
            except Exception as copy_e:
                print(f"\033[93m[{task_id}] 警告: 成功渲染PDF，但复制原始PDF失败: {copy_e}\033[0m", flush=True)
            return True
        else:
            print(f"\033[91m[{task_id}] 错误: PDF文件未生成，即使编译命令没有报错。\033[0m", flush=True)
            return False
    except Exception as e:
        print(f"\033[91m--- [{task_id}] 处理过程中发生严重错误: {e} ---\033[0m", flush=True)
        raise

# --- 饱和式攻击模式的Worker ---

def assault_worker(task_info, api_key, lock, success_event):
    """
    “攻坚小组”的单个成员。
    在隔离的环境中工作，并持续检查全局成功信号。
    """
    pid = os.getpid()
    year, exam_type, q_num, doc_type = task_info
    task_id = f"{year}-{exam_type}_第{q_num}問_{doc_type}"
    
    base_output_dir = OUTPUT_DIR / task_id
    temp_output_dir = base_output_dir / f"temp_worker_{pid}"
    temp_output_dir.mkdir(exist_ok=True, parents=True)
    
    print(f"[攻坚进程 {pid} | Key ...{api_key[-4:]}] 已启动，目标: {task_id}，工作区: {temp_output_dir}")

    try:
        if success_event.is_set():
            print(f"[攻坚进程 {pid}] 检测到任务已由其他进程完成，提前退出。")
            return

        genai.configure(api_key=api_key)
        success = process_and_render_question(year, exam_type, q_num, doc_type, lock, output_dir_override=temp_output_dir)

        with lock:
            if success and not success_event.is_set():
                print(f"\033[92m[攻坚进程 {pid} | Key ...{api_key[-4:]}] 攻坚成功！我是胜利者！正在移交成果...\033[0m")
                success_event.set()
                
                for item in temp_output_dir.iterdir():
                    target_path = base_output_dir / item.name
                    if target_path.exists():
                        if target_path.is_dir():
                            shutil.rmtree(target_path)
                        else:
                            target_path.unlink()
                    shutil.move(str(item), str(base_output_dir))
                print(f"\033[92m[攻坚进程 {pid}] 成果已移交至: {base_output_dir}\033[0m")

    except Exception as e:
        print(f"\033[91m[攻坚进程 {pid} | Key ...{api_key[-4:]}] 遭遇严重错误: {e}\033[0m")
    finally:
        if temp_output_dir.exists():
            shutil.rmtree(temp_output_dir)
        print(f"[攻坚进程 {pid}] 清理并退出。")


if __name__ == "__main__":
    multiprocessing.set_start_method('spawn', force=True)

    # 步骤 1: 准备需要“攻坚”的任务列表
    print("\n--- 正在准备需要攻坚的任务列表 (基于'已复制的源PDF'进行检测) ---")
    all_possible_tasks = get_all_tasks()
    tasks_to_run = []
    completed_count = 0
    for task in all_possible_tasks:
        year, exam_type, q_num, doc_type = task
        task_id_as_dir_name = f"{year}-{exam_type}_第{q_num}問_{doc_type}"
        source_pdf_filename = f"{task_id_as_dir_name}.pdf"
        expected_success_marker_path = OUTPUT_DIR / task_id_as_dir_name / source_pdf_filename
        if expected_success_marker_path.exists() and expected_success_marker_path.is_file():
            completed_count += 1
        else:
            tasks_to_run.append(task)
            
    if not tasks_to_run:
        print(f"\033[92m所有任务均已完全成功，无需执行新任务。\033[0m")
        sys.exit(0)
        
    print(f"总计发现 {len(all_possible_tasks)} 个任务，其中 {completed_count} 个已完全成功。")
    print(f"本次需要攻坚 {len(tasks_to_run)} 个任务。")

    # 步骤 2: 逐个任务进行饱和式攻击
    successful_assaults = []
    failed_assaults = []
    
    for i, task_info in enumerate(tasks_to_run):
        year, exam_type, q_num, doc_type = task_info
        task_id = f"{year}-{exam_type}_第{q_num}問_{doc_type}"
        
        print("\n" + "="*80)
        print(f"  开始对任务 {i+1}/{len(tasks_to_run)} 进行饱和式攻击: 【{task_id}】")
        print("="*80)

        manager = multiprocessing.Manager()
        success_event = manager.Event()
        lock = manager.Lock()
        
        processes = []
        for api_key in API_KEYS:
            p = multiprocessing.Process(target=assault_worker, args=(task_info, api_key, lock, success_event))
            p.start()
            processes.append(p)
            
        for p in processes:
            p.join()

        # 步骤 3: 战果评估
        task_id_as_dir_name = f"{year}-{exam_type}_第{q_num}問_{doc_type}"
        source_pdf_filename = f"{task_id_as_dir_name}.pdf"
        expected_success_marker_path = OUTPUT_DIR / task_id_as_dir_name / source_pdf_filename
        
        if expected_success_marker_path.exists():
            print(f"\033[92m[战果评估] 任务 【{task_id}】 攻坚成功！\033[0m")
            successful_assaults.append(task_id)
        else:
            print(f"\033[91m[战果评估] 任务 【{task_id}】 攻坚失败，所有API尝试均未成功。\033[0m")
            failed_assaults.append(task_id)

    # 步骤 4: 最终总结
    print("\n" + "="*80)
    print("           所有攻坚任务已结束 - 最终摘要")
    print("="*80)
    print(f"\033[92m成功攻克的任务数: {len(successful_assaults)}\033[0m")
    print(f"\033[91m未能攻克的任务数: {len(failed_assaults)}\033[0m")
    if failed_assaults:
        print("\n未能攻克的任务列表:")
        for task_id in failed_assaults:
            print(f"  - {task_id}")
    print("="*80)
    print("\033[92m--- 程序执行结束 ---\033[0m")
