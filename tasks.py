from celery import Celery
from src import scheduler, logger

# --- Celery Configuration ---
# In a production environment, you would want to externalize this configuration.
# For example, loading it from a settings file or environment variables.
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

# Create a Celery application instance
celery_app = Celery(
    'tasks',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Optional: Update Celery configuration with more advanced settings
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],  # Ensure tasks use JSON for serialization
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# --- Celery Task Definition ---

@celery_app.task(name='tasks.process_pdf_task')
def process_pdf_task(file_path: str):
    """
    A Celery task that orchestrates the processing of a single PDF file.

    This function is the main entry point for our asynchronous backend processing.
    It is triggered by the FastAPI endpoint and runs in a Celery worker.

    Args:
        file_path (str): The absolute path to the PDF file to be processed.
    """
    # It's good practice to set up the logger within the task
    # if the worker is running in a separate process.
    logger.setup_logger()

    logger.logging.info(f"Celery task received for file: {file_path}")

    try:
        # Call the main orchestration logic from our scheduler module
        # We pass the single file path in a list as the orchestrator
        # is designed to handle a list of tasks.
        scheduler.run_orchestration([file_path])
        logger.logging.success(f"Orchestration completed for file: {file_path}")
    except Exception as e:
        logger.logging.error(f"An error occurred during orchestration for {file_path}: {e}")
        # Depending on the desired retry policy, you could re-raise the exception
        # raise self.retry(exc=e, countdown=60)

    return f"Processing complete for {file_path}"
