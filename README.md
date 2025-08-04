好的，没有问题。

这是根据您的最新要求更新的一份简洁、美观且清晰的英文 README.md。

🤖 AI-Powered PDF Translator & Re-renderer

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
