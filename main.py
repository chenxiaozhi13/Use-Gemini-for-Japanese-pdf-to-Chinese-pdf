import uuid
import shutil
import logging
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from celery.result import AsyncResult
from tasks import celery_app, process_pdf_task

# --- App Initialization ---
app = FastAPI(
    title="Layout-Aware PDF Translation Service",
    description="An API service to translate PDFs while preserving the original layout.",
    version="1.0.0",
)

# --- Directory Setup ---
# Create a directory to store temporary uploads.
# In a production environment, you might use a more robust solution
# like a dedicated file storage service (e.g., S3).
UPLOAD_DIR = Path("temp_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.on_event("startup")
async def startup_event():
    """
    A startup event handler for the FastAPI application.
    This is a good place to initialize resources.
    """
    logging.info("FastAPI application starting up...")
    # You could add other startup logic here, like connecting to a database.
    # For now, we just ensure the upload directory exists.
    UPLOAD_DIR.mkdir(exist_ok=True)
    logging.info(f"Upload directory is set to: {UPLOAD_DIR.resolve()}")


# --- API Endpoints ---

@app.post("/upload", status_code=202)
async def upload_pdf(file: UploadFile = File(...)):
    """
    Accepts a PDF file, saves it, and queues it for processing.

    This endpoint is the entry point for a new translation task. It performs
    the initial validation and file handling, then returns a task ID that

    the client can use to check the status of the processing job later.
    """
    # Ensure the uploaded file is a PDF
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF.")

    # Generate a unique ID for this task
    task_id = str(uuid.uuid4())

    # Create a dedicated directory for this task's files
    task_dir = UPLOAD_DIR / task_id
    task_dir.mkdir()

    file_path = task_dir / file.filename

    try:
        # Save the uploaded file to the designated path
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        # Always close the uploaded file
        file.file.close()

    # --- Trigger Background Task ---
    # Instead of processing here, we queue the task with Celery.
    # We pass the absolute path of the saved file to the task.
    task = process_pdf_task.delay(str(file_path.resolve()))

    # Return the Celery task ID to the client
    return {
        "task_id": task.id,
        "filename": file.filename,
        "status": "queued",
        "detail": "The file has been successfully queued for processing.",
    }

@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """
    Checks the status of a background processing task.
    """
    task_result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": task_result.state,
        "result": None,
    }

    if task_result.state == "SUCCESS":
        response["result"] = task_result.result
    elif task_result.state == "FAILURE":
        # The result of a failed task is the exception that was raised.
        response["result"] = str(task_result.result)

    return response


@app.get("/download/{task_id}")
async def download_result(task_id: str):
    """
    Downloads the processed PDF file if the task was successful.
    """
    task_result = AsyncResult(task_id, app=celery_app)

    if task_result.state != "SUCCESS":
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} is not complete or has failed. Current status: {task_result.state}"
        )

    file_path_str = task_result.result
    if not file_path_str or not isinstance(file_path_str, str):
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} completed but did not return a valid file path."
        )

    file_path = Path(file_path_str)
    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"File not found for task {task_id}. The file may have been moved or deleted."
        )

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type='application/pdf'
    )


# To run this application:
# 1. Make sure you have installed the dependencies: pip install -r requirements.txt
# 2. Run the server: uvicorn main:app --reload
# 3. Open your browser to http://127.0.0.1:8000/docs to see the API documentation.
