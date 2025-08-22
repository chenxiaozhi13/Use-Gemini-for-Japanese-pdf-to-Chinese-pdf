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

@celery_app.task(bind=True, name='tasks.process_pdf_task')
def process_pdf_task(self, file_path: str):
    """
    A Celery task that orchestrates the processing of a single PDF file.

    This function is the main entry point for our asynchronous backend processing.
    It is triggered by the FastAPI endpoint and runs in a Celery worker.

    Args:
        file_path (str): The absolute path to the PDF file to be processed.

    Returns:
        str: The absolute path to the generated PDF on success, or a descriptive
             error message string on failure.
    """
    logger.setup_logger()
    logger.logging.info(f"Celery task {self.request.id} received for file: {file_path}")

    try:
        # Call the main orchestration logic from our scheduler module
        result_path = scheduler.run_orchestration([file_path])

        if result_path:
            logger.logging.success(f"Orchestration for {self.request.id} completed successfully. Result: {result_path}")
            return result_path
        else:
            logger.logging.error(f"Orchestration for {self.request.id} failed with a controllable error.")
            # This is a failure case we want to report to the user.
            # We raise an exception, and Celery will store the exception message as the task's result.
            raise Exception("PDF processing failed. Check worker logs for details.")

    except Exception as e:
        logger.logging.error(f"A critical exception occurred in task {self.request.id} for file {file_path}: {e}", exc_info=True)
        # Re-raise the exception. Celery will catch it and store it as the task result.
        # This makes the failure and its reason visible in the status check.
        raise e
