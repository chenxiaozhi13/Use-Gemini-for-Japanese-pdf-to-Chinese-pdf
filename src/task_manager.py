from pathlib import Path
from . import config

def get_all_tasks():
    """
    Generates a list of all possible tasks based on predefined rules.
    A task is represented by a tuple: (year, exam_type, question_num, doc_type).
    """
    tasks = []
    doc_types = ["问题", "解答"]

    # Years 2021-2024
    for year in range(2021, 2025):
        for exam_type in ["1A", "2B"]:
            for q_num in range(1, 6):
                for doc_type in doc_types:
                    tasks.append((str(year), exam_type, str(q_num), doc_type))

    # Year 2025, type 1A
    for q_num in range(1, 5):
        for doc_type in doc_types:
            tasks.append(("2025", "1A", str(q_num), doc_type))

    # Year 2025, type 2BC
    for q_num in range(1, 8):
        for doc_type in doc_types:
            tasks.append(("2025", "2BC", str(q_num), doc_type))

    return tasks

def get_task_id(task_info):
    """
    Generates a standardized task ID string from a task_info tuple.
    Example: ('2021', '1A', '1', '问题') -> '2021-1A_第1問_问题'
    """
    year, exam_type, q_num, doc_type = task_info
    return f"{year}-{exam_type}_第{q_num}問_{doc_type}"

def is_task_truly_complete(task_info):
    """
    Implements the "ultimate status check" for a given task.

    A task is considered truly complete only if the original source PDF
    has been successfully copied into that task's specific output directory.
    This serves as a definitive success marker.

    Args:
        task_info (tuple): The task identifier tuple.

    Returns:
        bool: True if the task is complete, False otherwise.
    """
    task_id = get_task_id(task_info)
    source_pdf_filename = f"{task_id}.pdf"

    # The success marker is the original PDF copied into the task's final output folder
    expected_success_marker_path = config.FINAL_OUTPUT_DIR / task_id / source_pdf_filename

    return expected_success_marker_path.exists() and expected_success_marker_path.is_file()
