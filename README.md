# AI-Powered Academic Document Localization Platform

## 1. Project Vision

**AI驱动的学术文档智能本地化平台**

This project provides a robust, scalable web service for translating academic documents (such as mathematical exams) from one language to another while meticulously preserving the original page layout and formatting. It leverages a powerful AI model for translation and a sophisticated PDF reconstruction engine to deliver high-fidelity, production-quality results.

---

## 2. Architecture Overview

The system is designed as a modern, asynchronous web service to handle long-running, computationally intensive tasks efficiently.

- **API Layer (FastAPI)**: A high-performance Python web framework that provides the HTTP interface. It handles file uploads and dispatches tasks to the background processing system.
- **Task Queue (Celery & Redis)**: Celery is a distributed task queue that allows us to execute the PDF processing asynchronously. This ensures the API remains responsive and doesn't block while waiting for a task to complete. Redis serves as the fast, in-memory message broker that mediates between the web server and the Celery workers.
- **Backend Orchestrator (`src` module)**: The core logic of the application lives in the `src` package. It contains a multi-process, multi-threaded engine responsible for the entire PDF processing pipeline:
    1.  **Parsing (`pdfminer.six`)**: Extracts text content and its precise coordinates from the source PDF.
    2.  **Concurrent Translation (Gemini API)**: Translates the text from each page of the document concurrently, maximizing speed.
    3.  **PDF Reconstruction (`reportlab`)**: Rebuilds a new PDF from scratch, placing the translated text at its original coordinates to ensure the layout is perfectly preserved.

---

## 3. API Endpoints Documentation

### 3.1. Upload a PDF for Translation

- **Method**: `POST`
- **Path**: `/upload`
- **Description**: Submits a new PDF file for translation. The service accepts the file, queues it for background processing, and immediately returns a unique `task_id`.
- **`curl` Example**:
  ```bash
  curl -X POST "http://127.0.0.1:8000/upload" \
       -H "accept: application/json" \
       -H "Content-Type: multipart/form-data" \
       -F "file=@/path/to/your/document.pdf"
  ```
- **Success Response (202 Accepted)**:
  ```json
  {
    "task_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
    "filename": "document.pdf",
    "status": "queued",
    "detail": "The file has been successfully queued for processing."
  }
  ```

### 3.2. Check Task Status

- **Method**: `GET`
- **Path**: `/status/{task_id}`
- **Description**: Poll this endpoint with a `task_id` to check the current status of a processing job.
- **`curl` Example**:
  ```bash
  curl -X GET "http://127.0.0.1:8000/status/a1b2c3d4-e5f6-7890-1234-567890abcdef"
  ```
- **Response Examples**:
    - **Pending**:
      ```json
      {
        "task_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
        "status": "PENDING",
        "result": null
      }
      ```
    - **Success**:
      ```json
      {
        "task_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
        "status": "SUCCESS",
        "result": "/app/temp_uploads/document_translated.pdf"
      }
      ```
    - **Failure**:
      ```json
      {
        "task_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
        "status": "FAILURE",
        "result": "PDF processing failed. Check worker logs for details."
      }
      ```

### 3.3. Download Processed File

- **Method**: `GET`
- **Path**: `/download/{task_id}`
- **Description**: Once a task's status is `SUCCESS`, use this endpoint to download the final, translated PDF file.
- **`curl` Example**:
  ```bash
  curl -X GET "http://127.0.0.1:8000/download/a1b2c3d4-e5f6-7890-1234-567890abcdef" \
       --output translated_document.pdf
  ```
- **Success Response**: The endpoint returns the PDF file directly with a `Content-Type: application/pdf` header.
- **Error Response**: If the task is not yet complete or has failed, it will return a 404 Not Found error.

---

## 4. Setup and Deployment Guide

### 4.1. Prerequisites

- Python 3.10+
- [Redis](https://redis.io/docs/getting-started/): You must have a Redis server running locally.
- **A CJK Font**: The PDF reconstruction requires a TrueType Font that supports Chinese characters (e.g., Noto Sans CJK, WenQuanYi, SimSun). The application is configured to look for a font at a standard Linux path. Please ensure a suitable font is installed or update the path in `src/worker.py`.

### 4.2. Installation

1.  Clone this repository.
2.  Install the required Python dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### 4.3. Running the Application

You need to run **three separate processes** in three different terminals for the service to be fully operational.

**Terminal 1: Start Redis**

If you have Redis installed via a package manager (like `apt` or `brew`), you can usually start it with:
```bash
redis-server
```
Ensure Redis is running on its default port (6379).

**Terminal 2: Start the Celery Worker**

Navigate to the project root and run the following command to start the Celery worker. The worker will connect to Redis and wait for tasks to process.
```bash
celery -A tasks.celery_app worker --loglevel=info
```

**Terminal 3: Start the FastAPI Server**

Navigate to the project root and run the following command to start the FastAPI web server.
```bash
uvicorn main:app --reload
```
The API will now be live and accessible at `http://127.0.0.1:8000`. You can access the interactive documentation at `http://127.0.0.1:8000/docs`.
