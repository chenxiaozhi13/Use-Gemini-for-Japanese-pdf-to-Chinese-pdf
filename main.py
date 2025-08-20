import uuid
import shutil
import logging
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from tasks import process_pdf_task

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

# To run this application:
# 1. Make sure you have installed the dependencies: pip install -r requirements.txt
# 2. Run the server: uvicorn main:app --reload
# 3. Open your browser to http://127.0.0.1:8000/docs to see the API documentation.
