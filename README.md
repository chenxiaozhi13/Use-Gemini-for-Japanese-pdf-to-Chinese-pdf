AI-Powered PDF Translator & Re-renderer

This project uses the Google Gemini API to automatically translate Japanese math exam PDFs—complete with their original images—into high-quality, layout-matched Chinese PDFs.

✨ Core Features

🚀 High-Concurrency Engine: Processes dozens of files simultaneously by leveraging Python's multiprocessing capabilities, maximizing speed and efficiency.

🔑 Multi-API Key Strategy: The system rotates through a pool of API keys. This provides two major advantages:

Fault Tolerance: If one key is rate-limited, blocked, or fails, the system automatically switches to healthy keys, ensuring the process continues without interruption.

Increased Throughput: It allows us to bypass the rate limit of a single key, enabling a much higher number of parallel tasks.

🧠 Dynamic Load Balancing (No More Bottlenecks!): This is our secret sauce for preventing process pile-ups. The system doesn't assign tasks randomly; it uses a dynamic scoring algorithm:

It constantly calculates a "busyness score" for each API key.

This score considers active load (current running jobs), long-term pressure (queued tasks), and failure history.

New tasks are always assigned to the key with the lowest score. This ensures work is distributed intelligently and prevents tasks from getting stuck behind a slow or failing process.

🛠️ Self-Healing Workflow: If a task fails, it's automatically retried. If an API key is consistently causing problems, the system sidelines it. Just run the script once, and it will work tirelessly to complete the job.

⚙️ How It Works

The process is fully automated and image-aware:

Japanese PDF ➡️ minerU Extracts Images ➡️ (PDF Text + All Images) ➡️ Gemini API (Performs OCR, Translation, and LaTeX Layout) ➡️ Final, High-Fidelity Chinese PDF

This workflow ensures that questions with diagrams, graphs, and figures are perfectly understood and reproduced in the final document.

⚠️ Journey & Key Learnings (Notes & Considerations)

Problem: System crashes on startup due to resource overload.

Solution: We implemented a "smooth startup" that gradually launches processes, preventing system instability.

Problem: Simple task distribution was slow and created bottlenecks.

Solution: Our dynamic scoring and load-balancing algorithm ensures that the workload is always spread efficiently across all available resources.

Problem: Failed tasks were sometimes skipped permanently.

Solution: We designed a more robust "success check" that is virtually bug-proof, ensuring every task is either completed or correctly marked for retry.

❗️Crucial System Note: This script is powerful but resource-intensive. On Windows, each process can require about 1GB of virtual memory (Page File). Ensure your system's page file is adequately sized to avoid crashes.

🛠️ Tools & Technologies Used

Python 3

Google Gemini 2.5 Pro API KEY (more than one)

minerU (For PDF image extraction)

LaTeX (XeLaTeX for CJK font support)

Python's multiprocessing library

---

## Service-Based Architecture (NEW)

The application has been refactored into a modern, scalable web service with three main components:
1.  **FastAPI Web Server**: Handles HTTP requests, file uploads, and queuing tasks.
2.  **Celery Worker**: Executes the long-running PDF processing tasks in the background.
3.  **Redis Broker**: A message broker that manages the queue of tasks between the web server and the workers.

### Prerequisites (Service Mode)

- Python 3.10+
- [Redis](https://redis.io/docs/getting-started/): You must have a Redis server running locally.
- **A CJK Font**: The PDF reconstruction requires a TrueType Font that supports Chinese characters (e.g., Noto Sans CJK, WenQuanYi, SimSun). The application is configured to look for a font at `/usr/share/fonts/truetype/wqy/wqy-microhei.ttc`. Please ensure a font exists at this path or update the path in `src/worker.py`.

### Installation

1.  Clone the repository.
2.  Install the Python dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Running the Application (Service Mode)

You need to run three separate processes in three different terminals.

**1. Start Redis**

If you have Redis installed via a package manager, you can usually start it with:
```bash
redis-server
```
Ensure Redis is running on its default port (6379).

**2. Start the Celery Worker**

In a new terminal, navigate to the project root and run the following command to start the Celery worker process. The worker will listen for tasks on the Redis queue.
```bash
celery -A tasks.celery_app worker --loglevel=info
```

**3. Start the FastAPI Server**

In a third terminal, navigate to the project root and run the following command to start the FastAPI web server using Uvicorn.
```bash
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

### How to Use the API

1.  Navigate to the interactive API documentation at `http://127.0.0.1:8000/docs`.
2.  Use the `/upload` endpoint to upload a PDF file.
3.  The API will return a `task_id`. This confirms that your task has been queued for processing by the Celery worker.
