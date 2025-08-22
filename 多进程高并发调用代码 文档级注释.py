# ====================================================================================================
#
#                                     All-in-One 高并发智能编排器
#
# ====================================================================================================
#
# 作者: (您可以在这里写上您的名字或ID)
# 版本: 3.1 (文档级注释稳定版)
# 描述: 本脚本是一个专为计算密集型和API密集型任务设计的、功能完备的多进程并发处理器。
#       它将原始的渲染逻辑与一个高级的、健壮的并发调度系统完美融合在一个文件中。
#
# ----------------------------------------------------------------------------------------------------
#                                         【核心功能与设计哲学】
# ----------------------------------------------------------------------------------------------------
# 此脚本的设计旨在解决一系列在自动化和并发处理中遇到的典型难题，其核心设计包括：
#
# 1. 平滑启动机制 (Smooth Startup Mechanism):
#    - 问题: 一次性启动大量进程(如40个)会导致系统资源瞬间耗尽而崩溃。
#    - 解决: 放弃`multiprocessing.Pool`，改用`multiprocessing.Process`。在主循环中逐个创建
#      进程，并在每次创建后加入`time.sleep()`延迟，将启动压力在时间上拉平。
#
# 2. 终极状态检测 (Ultimate State Detection):
#    - 问题: 简单的检查输出文件(`generated.pdf`)存在漏洞，失败的重试可能会留下旧的成功文件，
#      导致任务被错误地跳过。
#    - 解决: 将成功标记改为检查【原始PDF】是否已被成功复制到最终输出目录。因为复制操作是
#      整个成功流程的最后一步，所以这是判断任务是否【完全成功】的最可靠标志。
#
# 3. 自我修复工作流 (Self-Healing Workflow):
#    - 问题: 单次运行后，失败的任务需要手动重新运行脚本才能重试。
#    - 解决: 引入【任务内重试】和【API失败惩罚】机制。
#      - 任务内重试: 失败的任务会被自动放回待办队列末尾，并有最大重试次数限制，防止死循环。
#      - API失败惩罚: 持续失败的API Key其“失败分”会增加，导致其在智能调度中的优先级急剧下降，
#        从而被自动“冷落”，让健康的API接管工作。
#
# 最终效果：您只需运行一次脚本，它就会像一个永不放弃的机器人管家一样，持续工作，
# 自动绕开被限额的API，不断重试可恢复的失败，直到所有任务都真正成功，或者达到最大
# 重试次数为止。
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

# 您的Google Gemini API密钥列表。程序将从这个列表中选择API Key来执行任务。
# 更多的Key意味着更强的并发能力和容错性。
API_KEYS = [
    'AIzaSyDSsuqAJcBeVKz9AiS4a2-Q_4DZcbDg0V1',
    'AIzaSyDSsuqAJcBeVKz9AiS4a2-Q_4DZcbDg0V2',
    'AIzaSyDSsuqAJcBeVKz9AiS4a2-Q_4DZcbDg0V3',
    'AIzaSyDSsuqAJcBeVKz9AiS4a2-Q_4DZcbDg0V4',
    'AIzaSyDSsuqAJcBeVKz9AiS4a2-Q_4DZcbDg0V5',
    'AIzaSyDSsuqAJcBeVKz9AiS4a2-Q_4DZcbDg0V6',
    'AIzaSyDSsuqAJcBeVKz9AiS4a2-Q_4DZcbDg0V7',
]

# --- 并发与调度配置 ---

# 每个API Key允许的最大并发进程数。这是为了遵守API提供商的速率限制。
MAX_CONCURRENCY_PER_KEY = 4
# 您希望同时运行的总进程数。这个值应小于或等于 (API_KEYS数量 * MAX_CONCURRENCY_PER_KEY)。
# 【重要】每个进程约需1GB分页文件(Windows虚拟内存)，请确保系统资源充足。
TARGET_TOTAL_CONCURRENCY = 60
# 创建新进程之间的延迟时间（秒）。这是实现“平滑启动”以避免系统崩溃的关键。
PROCESS_CREATION_DELAY = 0.5
# 【新增】每个任务的最大重试次数。防止因永久性错误(如源文件损坏)导致的无限循环。
MAX_TASK_RETRIES = 3

# --- 智能调度权重 ---
# 通过调整这些权重，可以改变调度策略的倾向性。
# 即时负载权重：值越高，程序越倾向于将任务分配给当前“无所事事”的Key。
WEIGHT_ACTIVE_TASKS = 3.0
# 长期压力权重：值越高，程序越倾向于帮助那些“名下待办任务总数”多的Key分担压力。
WEIGHT_REMAINING_TASKS = 1.0
# API失败惩罚权重：这个值应该比较高，一次失败就应该让这个Key的优先级显著降低。
WEIGHT_FAILURES = 10.0

# --- 路径配置 ---
CURRENT_WORKING_DIR = Path.cwd()
BASE_DIR = CURRENT_WORKING_DIR / "结果2"
OUTPUT_DIR = BASE_DIR / "latex_output_final"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True) # 确保输出目录存在

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
【组件：带点划线的公式编号】
规则： 用于创建以点线填充并在末尾带有带圈数字的行，通常用于标记方程式或条件。
实现： 在需要标记的内容后，直接组合使用 \dotfill 和 \mycircled{} 命令。
示例： 在箱子A中，3次中恰好抽中1次的概率是 $\dfrac{\text{\fbox{ア}}}{\text{\fbox{イ}}}$ \dotfill \mycircled{1}
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
【底部页码标规则】
对于pdf的第一页，我们使用 \setcounter{page}{0}  ，把我们生成的新pdf的第一页的页码 设置为与原pdf的第一页的页码一致。后续页码就会自动合理地衔接了，后续页码不需要修改。
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

def process_and_render_question(year, exam_type, question_num, doc_type, lock):
    """处理单个试题的核心函数：API调用、文件保存、LaTeX编译。"""
    question_base_name = f"{year}-{exam_type}_第{question_num}問_{doc_type}"
    task_id = question_base_name 
    question_output_dir = OUTPUT_DIR / question_base_name
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
        model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
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
        raise # 重新抛出异常，让上层捕获并打印红色日志

# --- 多进程编排器逻辑 ---

def worker_process(task_info, api_key, lock, result_queue):
    """
    每个子进程的入口函数。
    它负责配置环境、调用核心业务逻辑，并向主进程报告最终结果。
    它会将原始的task_info也放入结果队列，以便主进程进行重试。
    """
    genai.configure(api_key=api_key)
    year, exam_type, q_num, doc_type = task_info
    task_id = f"{year}-{exam_type}_第{q_num}問_{doc_type}"
    pid = os.getpid()
    print(f"[进程 {pid} | Key ...{api_key[-4:]}] 开始处理任务: {task_id}", flush=True)
    try:
        success = process_and_render_question(year, exam_type, q_num, doc_type, lock)
        if success:
            print(f"\033[92m[进程 {pid} | Key ...{api_key[-4:]}] 任务成功: {task_id}\033[0m", flush=True)
            result_queue.put((task_id, True, api_key, pid, task_info))
        else:
            print(f"\033[93m[进程 {pid} | Key ...{api_key[-4:]}] 任务失败 (函数返回False): {task_id}\033[0m", flush=True)
            result_queue.put((task_id, False, api_key, pid, task_info))
    except Exception as e:
        print(f"\033[91m[进程 {pid} | Key ...{api_key[-4:]}] 任务 '{task_id}' 发生严重异常: {e}\033[0m", flush=True)
        result_queue.put((task_id, False, api_key, pid, task_info))


if __name__ == "__main__":
    # 在Windows和macOS上，'spawn'是更安全的多进程启动方法，能更好地隔离父子进程
    multiprocessing.set_start_method('spawn', force=True)

    # 步骤 1: 准备任务列表 (采用终极状态检测)
    # -------------------------------------------------
    print("\n--- 正在准备任务列表 (基于'已复制的源PDF'进行检测) ---")
    all_possible_tasks = get_all_tasks()
    tasks_to_run = []
    completed_count = 0
    for task in all_possible_tasks:
        year, exam_type, q_num, doc_type = task
        task_id_as_dir_name = f"{year}-{exam_type}_第{q_num}問_{doc_type}"
        source_pdf_filename = f"{task_id_as_dir_name}.pdf"
        # 这是我们判断任务是否已【完全成功】的唯一标准
        expected_success_marker_path = OUTPUT_DIR / task_id_as_dir_name / source_pdf_filename
        if expected_success_marker_path.exists() and expected_success_marker_path.is_file():
            completed_count += 1
        else:
            tasks_to_run.append(task)
    
    # 使用双端队列(deque)作为任务池，从左侧弹出任务效率更高
    tasks_to_run_total = collections.deque(tasks_to_run)
    initial_task_count = len(tasks_to_run_total)
    
    if not tasks_to_run_total:
        print(f"\033[92m所有任务均已完全成功，无需执行新任务。\033[0m")
        sys.exit(0)
        
    print(f"总计发现 {len(all_possible_tasks)} 个任务，其中 {completed_count} 个已完全成功。")
    print(f"本次需要处理 {initial_task_count} 个新任务。")

    # 步骤 2: 初始化调度器
    # -------------------------------------------------
    manager = multiprocessing.Manager()
    lock = manager.Lock()
    result_queue = manager.Queue()
    # key_status现在包含'failures'计数器，用于API失败惩罚
    key_status = {key: {'active': 0, 'remaining': 0, 'failures': 0} for key in API_KEYS}
    # “虚拟分配”：为每个Key计算一个初始的“长期压力”值
    for i, task in enumerate(tasks_to_run_total):
        key_for_task = API_KEYS[i % len(API_KEYS)]
        key_status[key_for_task]['remaining'] += 1
        
    print("\n--- 任务初始虚拟分配情况 ---")
    for key, status in key_status.items():
        print(f"  - Key ...{key[-4:]}: 待办 {status['remaining']} 个任务")
        
    active_processes = []
    successful_tasks = set()
    permanently_failed_tasks = set()
    # 用于跟踪每个任务的重试次数
    task_retry_counts = collections.defaultdict(int)
    
    print(f"\n--- 开始高级调度（自我修复模式），目标并发数: {TARGET_TOTAL_CONCURRENCY} ---")

    # 步骤 3: 智能编排器主循环
    # -------------------------------------------------
    # 循环条件：只要任务队列中还有任务，或者还有进程在工作，就继续
    while tasks_to_run_total or active_processes:
        
        # A. 尝试分发新任务
        if tasks_to_run_total and len(active_processes) < TARGET_TOTAL_CONCURRENCY:
            
            # 决策模块：基于效能评分选择最佳API Key
            best_key, min_score = None, float('inf')
            candidate_keys = []
            for key, status in key_status.items():
                if status['active'] < MAX_CONCURRENCY_PER_KEY:
                    # 评分算法加入失败惩罚，失败越多的Key得分越高，越不容易被选中
                    score = (status['active'] * WEIGHT_ACTIVE_TASKS) + \
                            (status['remaining'] * WEIGHT_REMAINING_TASKS) + \
                            (status['failures'] * WEIGHT_FAILURES)
                    candidate_keys.append((key, score))
            
            if candidate_keys:
                candidate_keys.sort(key=lambda x: x[1])
                best_key, min_score = candidate_keys[0]
            
            # 执行模块：为选中的Key启动一个新进程
            if best_key:
                task = tasks_to_run_total.popleft()
                p = multiprocessing.Process(target=worker_process, args=(task, best_key, lock, result_queue))
                p.start()
                
                # 更新状态记录
                active_processes.append(p)
                key_status[best_key]['active'] += 1
                
                print(f"[调度器] 选择 Key ...{best_key[-4:]} (得分: {min_score:.2f}) 启动进程 {p.pid}。总进程: {len(active_processes)}/{TARGET_TOTAL_CONCURRENCY}")
                
                # 平滑启动的关键：在启动下一个进程前稍作等待
                time.sleep(PROCESS_CREATION_DELAY)

        # B. 尝试从结果队列中收集并处理结果
        try:
            # 使用非阻塞的get，避免在队列为空时卡住
            task_id, success, api_key, pid, task_info = result_queue.get(timeout=0.1)
            
            # 释放一个活跃槽位
            if api_key in key_status:
                key_status[api_key]['active'] -= 1

            if success:
                successful_tasks.add(task_id)
                # 任务成功，其对应的长期压力也确实减少了
                if api_key in key_status:
                    key_status[api_key]['remaining'] -= 1
            else:
                # 任务失败处理逻辑：重试或宣告永久失败
                if api_key in key_status:
                    key_status[api_key]['failures'] += 1 # 增加API的失败计数
                
                task_retry_counts[task_id] += 1 # 增加任务的重试计数
                
                if task_retry_counts[task_id] < MAX_TASK_RETRIES:
                    # 未达到最大重试次数，重新放回队列末尾
                    tasks_to_run_total.append(task_info)
                    print(f"\033[96m[调度器] 任务 '{task_id}' 失败，已重新排队 (尝试 {task_retry_counts[task_id]}/{MAX_TASK_RETRIES})。API Key ...{api_key[-4:]} 失败计数+1。\033[0m")
                else:
                    # 已达到，宣告永久失败
                    permanently_failed_tasks.add(task_id)
                    # 任务永久失败，其对应的长期压力也确实减少了
                    if api_key in key_status:
                        key_status[api_key]['remaining'] -= 1
                    print(f"\033[91m[调度器] 任务 '{task_id}' 已达到最大重试次数，宣告永久失败。\033[0m")

        except queue.Empty:
            # 队列为空是正常现象，直接进入下一轮循环
            pass

        # C. 清理已结束的进程
        active_processes = [p for p in active_processes if p.is_alive()]
        
        # 短暂休眠，避免主进程CPU空转
        time.sleep(0.1)

    # 步骤 4: 最终结果统计
    # -------------------------------------------------
    print("\n--- 所有任务处理循环已结束 ---")
    print("\n" + "="*50)
    print("           最终任务执行摘要")
    print("="*50)
    print(f"\033[92m成功任务数: {len(successful_tasks)}\033[0m")
    # 失败任务数现在是那些达到最大重试次数的任务
    print(f"\033[91m永久失败任务数: {len(permanently_failed_tasks)}\033[0m")
    if permanently_failed_tasks:
        print("\n永久失败的任务列表 (已达最大重试次数):")
        for task_id in sorted(list(permanently_failed_tasks)):
            print(f"  - {task_id}")
    print("="*50)
    
    if not permanently_failed_tasks and initial_task_count > 0:
        print(f"\033[92m恭喜！所有 {initial_task_count} 个待办任务均已成功完成！\033[0m")
    elif not permanently_failed_tasks and initial_task_count == 0:
        print("\033[92m无需执行新任务。\033[0m")
    else:
        print(f"\033[93m注意：有 {len(permanently_failed_tasks)} 个任务在达到最大重试次数后仍未成功。\033[0m")

    print("\033[92m--- 程序执行结束 ---\033[0m")
