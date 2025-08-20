import logging
import multiprocessing
from src import logger, task_manager, scheduler, config

def main():
    """
    The main entry point for the application.
    """
    # 1. Initialize the logger
    logger.setup_logger()

    # 2. Ensure the output directory exists
    config.FINAL_OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

    # 3. Get all possible tasks and filter out completed ones
    logging.info("Scanning for all possible tasks...")
    all_possible_tasks = task_manager.get_all_tasks()

    tasks_to_run = []
    for task_info in all_possible_tasks:
        if not task_manager.is_task_truly_complete(task_info):
            tasks_to_run.append(task_info)

    completed_count = len(all_possible_tasks) - len(tasks_to_run)

    logging.info(f"Found {len(all_possible_tasks)} total possible tasks.")
    logging.success(f"{completed_count} tasks are already complete.")

    # 4. Run the scheduler if there are tasks to process
    if not tasks_to_run:
        logging.success("All tasks are already complete. Nothing to do.")
        return

    logging.info(f"Starting scheduler for {len(tasks_to_run)} pending tasks.")

    try:
        scheduler.run_scheduler(tasks_to_run)
    except Exception as e:
        logging.critical(f"A fatal error occurred during scheduler execution: {e}")
    finally:
        logging.info("Application finished.")

if __name__ == "__main__":
    # Set start method to 'spawn' for cross-platform compatibility and safety
    multiprocessing.set_start_method('spawn', force=True)
    main()
