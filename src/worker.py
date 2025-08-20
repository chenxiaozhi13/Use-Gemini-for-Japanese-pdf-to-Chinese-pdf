import logging
import shutil
import subprocess
import os
import google.generativeai as genai
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer
from . import config
from . import task_manager

def _parse_pdf_with_coordinates(pdf_path):
    """
    Parses a PDF to extract text blocks with their coordinates using pdfminer.six.

    Args:
        pdf_path (str or Path): The path to the PDF file.

    Returns:
        list: A list of dictionaries, where each dictionary represents a text block
              and contains its page number, text content, and bounding box.
              Example: [{'page': 0, 'text': 'Hello', 'coords': (x0, y0, x1, y1)}, ...]
    """
    text_blocks = []
    try:
        for page_layout in extract_pages(pdf_path):
            page_index = page_layout.pageid - 1 # pdfminer pageid is 1-based
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    text = element.get_text().strip()
                    if text:  # Only add non-empty text blocks
                        text_blocks.append({
                            'page': page_index,
                            'text': text,
                            'coords': element.bbox
                        })
        logging.info(f"Successfully parsed {pdf_path} and found {len(text_blocks)} text blocks.")
    except Exception as e:
        logging.error(f"Failed to parse PDF {pdf_path} with pdfminer.six: {e}")
        return [] # Return empty list to allow process to potentially continue
    return text_blocks

def process_task(task_info, api_key):
    """
    Processes a single task, from calling the AI to compiling the LaTeX document.

    This function encapsulates the core logic for handling one PDF task. It configures the API,
    constructs the prompt, calls the generative model, saves the result, and compiles the PDF.

    Args:
        task_info (tuple): A tuple containing task details (year, exam_type, q_num, doc_type).
        api_key (str): The Google AI API key to use for this task.

    Returns:
        bool: True on success, False on a controllable failure (like a LaTeX compile error).

    Raises:
        Exception: For critical, non-retriable errors (e.g., API failures).
    """
    task_id = task_manager.get_task_id(task_info)
    pid = os.getpid()
    log_prefix = f"[{task_id}][PID {pid}]"

    logging.info(f"{log_prefix} Starting processing with key ...{api_key[-4:]}")

    # Configure the generative AI library with the specific key for this process
    genai.configure(api_key=api_key)

    # Define paths
    task_output_dir = config.FINAL_OUTPUT_DIR / task_id
    task_output_dir.mkdir(exist_ok=True, parents=True)

    source_pdf_path = config.BASE_DIR / f"{task_id}.pdf"
    source_folder_path = config.BASE_DIR / task_id
    source_image_dir = source_folder_path / "images"

    # If the source PDF doesn't exist, there's nothing to process.
    if not source_pdf_path.exists():
        logging.warning(f"{log_prefix} Source PDF not found at {source_pdf_path}. Skipping task.")
        return True # Consider it "successful" as there is no work to be done.

    # --- 1. Parse PDF for text and coordinates ---
    logging.info(f"{log_prefix} Parsing PDF for text and coordinates...")
    structured_content = _parse_pdf_with_coordinates(source_pdf_path)
    if not structured_content:
        logging.warning(f"{log_prefix} PDF parsing yielded no text blocks. The PDF might be image-based or empty. Proceeding without structured data.")
    else:
        logging.info(f"{log_prefix} Successfully extracted {len(structured_content)} text blocks. First block: {structured_content[0]}")

    try:
        # --- 2. Construct the prompt for the API call ---
        prompt_parts = [config.ai_prompt]
        prompt_parts.append(genai.upload_file(path=source_pdf_path))

        # Append images if they exist
        if source_folder_path.exists() and source_image_dir.exists():
            image_files = sorted(list(source_image_dir.glob("*.jpg")))
            if image_files:
                image_list_prompt = "--- 可用图片文件列表 (必须使用) ---\n" + "\n".join([p.name for p in image_files]) + "\n--- 列表结束 ---\n"
                prompt_parts.append(image_list_prompt)
                for image_path in image_files:
                    prompt_parts.append(genai.upload_file(path=image_path))

        # --- 3. Call the Generative AI Model ---
        logging.info(f"{log_prefix} Calling Gemini API with model gemini-2.5-pro...")
        model = genai.GenerativeModel(model_name="gemini-2.5-pro")
        response = model.generate_content(prompt_parts, request_options={"timeout": 600})

        # Clean up the response text
        raw_text = response.text.strip()
        if raw_text.startswith("```latex"):
            raw_text = raw_text[len("```latex"):].strip()
        if raw_text.endswith("```"):
            raw_text = raw_text[:-len("```")].strip()

        final_latex_code = config.LATEX_PREAMBLE + "\n" + raw_text

        # --- 4. Save LaTeX code and copy assets ---
        output_tex_path = task_output_dir / "generated.tex"
        with open(output_tex_path, "w", encoding="utf-8") as f:
            f.write(final_latex_code)
        logging.info(f"{log_prefix} LaTeX code saved to {output_tex_path}")

        # Copy images directory to the output folder
        if source_folder_path.exists() and source_image_dir.exists() and any(source_image_dir.iterdir()):
            target_image_dir = task_output_dir / "images"
            if target_image_dir.exists():
                shutil.rmtree(target_image_dir)
            shutil.copytree(source_image_dir, target_image_dir)

        # --- 5. Compile LaTeX to PDF ---
        logging.info(f"{log_prefix} Starting PDF rendering with XeLaTeX...")
        for i in range(2): # Run twice for references
            process = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", output_tex_path.name],
                cwd=task_output_dir,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            if process.returncode != 0:
                logging.warning(f"{log_prefix} XeLaTeX compilation failed on run {i+1}. Check log: {output_tex_path.with_suffix('.log')}")
                return False # Controllable failure

        # --- 6. Final Verification and Success Marking ---
        if output_tex_path.with_suffix('.pdf').exists():
            # The "ultimate success marker": copy the original PDF to the output dir
            shutil.copy(source_pdf_path, task_output_dir)
            logging.success(f"{log_prefix} Successfully generated PDF and copied success marker.")
            return True
        else:
            logging.warning(f"{log_prefix} PDF file was not generated, even though XeLaTeX reported no errors.")
            return False # Controllable failure

    except Exception as e:
        logging.error(f"{log_prefix} A critical error occurred: {e}")
        raise # Re-raise the exception to be handled by the scheduler as a critical failure
