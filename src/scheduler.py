import logging
import multiprocessing
import time
import collections
from . import config, worker, task_manager

def get_least_busy_key(api_key_status):
    """
    Finds the best API key to use for the next task based on a "busy score".

    The score is calculated based on the number of active processes and
    a weighted penalty for past failures. Keys at their maximum concurrency
    are ineligible.

    Args:
        api_key_status (dict): A dictionary tracking the status of each API key.
            Example: {'key1': {'active': 2, 'failures': 1}, ...}

    Returns:
        str or None: The API key with the lowest busy score, or None if all
                     keys are at their maximum capacity.
    """
    lowest_score = float('inf')
    best_key = None

    for key, stats in api_key_status.items():
        if stats['active'] >= config.MAX_CONCURRENT_PER_KEY:
            continue  # Skip keys that are at max capacity

        # Calculate the busy score
        score = stats['active'] + (stats['failures'] * config.FAILURE_PENALTY_WEIGHT)

        if score < lowest_score:
            lowest_score = score
            best_key = key
        # If scores are equal, we can just stick with the first one found

    return best_key

def _process_wrapper(file_path, api_key, results_queue):
    """
    A wrapper function to run the worker process and report results.
    This function is the target for each multiprocessing.Process. It ensures
    that any outcome (success, controllable failure, or critical exception)
    is caught and put into the shared results queue.
    """
    try:
        success = worker.process_task(file_path, api_key)
        # 'success' can be True or False (for controllable failures)
        results_queue.put({'task': file_path, 'key': api_key, 'status': success})
    except Exception as e:
        # A critical, unexpected error occurred in the worker
        results_queue.put({'task': file_path, 'key': api_key, 'status': 'CRITICAL_FAILURE', 'error': str(e)})

def run_orchestration(tasks_to_process: list[str]):
    """
    The main orchestration loop to manage and distribute file-based tasks to worker processes.
    """
    logging.info(f"Orchestrator starting with {len(tasks_to_process)} tasks to process.")

    # --- Initialization ---
    api_key_status = {key: {'active': 0, 'failures': 0} for key in config.API_KEYS}
    tasks_queue = collections.deque(tasks_to_process)

    manager = multiprocessing.Manager()
    results_queue = manager.Queue()
    active_processes = []

    successful_tasks = []
    failed_tasks = []

    # --- Main Loop ---
    # Continue as long as there are tasks to start or processes still running
    while tasks_queue or active_processes:

        # --- 1. Check for and process results from finished workers ---
        while not results_queue.empty():
            result = results_queue.get()
            key = result['key']
            task_info = result['task']

            # Find and remove the finished process from our tracking list
            finished_process = None
            for p_info in active_processes:
                if p_info['task'] == task_info and p_info['key'] == key:
                    finished_process = p_info
                    break
            if finished_process:
                active_processes.remove(finished_process)
                finished_process['process'].join() # Clean up the process

            # Update API key status
            api_key_status[key]['active'] -= 1

            # Log outcome and update failure counts
            if result['status'] == True:
                logging.success(f"Task {result['task']} completed successfully.")
                successful_tasks.append(result['task'])
            elif result['status'] == False:
                logging.warning(f"Task {result['task']} failed with a controllable error.")
                api_key_status[key]['failures'] += 1
                failed_tasks.append(result['task'])
            else: # CRITICAL_FAILURE
                logging.error(f"Task {result['task']} failed with a critical error: {result['error']}")
                api_key_status[key]['failures'] += 1 # Penalize heavily
                failed_tasks.append(result['task'])

        # --- 2. Launch new workers if there are free slots ---
        can_launch = len(active_processes) < config.TARGET_TOTAL_CONCURRENCY and tasks_queue
        if can_launch:
            best_key = get_least_busy_key(api_key_status)

            if best_key:
                task_path = tasks_queue.popleft()

                p = multiprocessing.Process(
                    target=_process_wrapper,
                    args=(task_path, best_key, results_queue)
                )

                active_processes.append({
                    'process': p,
                    'task': task_path,
                    'key': best_key
                })
                api_key_status[best_key]['active'] += 1

                p.start()

                logging.info(f"Launched task for {task_path} with key ...{best_key[-4:]}")

                # Smooth start mechanism
                time.sleep(config.PROCESS_START_DELAY)

        # Prevent busy-waiting if the loop is active but no actions can be taken
        time.sleep(0.1)

    # --- Shutdown ---
    logging.info("All tasks have been processed. Scheduler shutting down.")
    logging.info("-" * 50)
    logging.success(f"Total successful tasks: {len(successful_tasks)}")
    logging.error(f"Total failed tasks: {len(failed_tasks)}")
    if failed_tasks:
        logging.info("Failed task list:")
        for task_path in failed_tasks:
            logging.info(f"  - {task_path}")
    logging.info("-" * 50)
