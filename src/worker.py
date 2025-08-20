import logging
import shutil
import subprocess
import os
import json
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

def _get_translation_with_layout(structured_content, api_key):
    """
    Sends structured text content to the Gemini API for translation.

    Args:
        structured_content (list): A list of dictionaries from _parse_pdf_with_coordinates.
        api_key (str): The API key to use for this call.

    Returns:
        list or None: A list of dictionaries with translated text, or None on failure.
    """
    if not structured_content:
        return []

    logging.info(f"Sending {len(structured_content)} text blocks for layout-aware translation.")

    # Configure the API for this specific call
    genai.configure(api_key=api_key)

    try:
        json_input = json.dumps(structured_content, indent=2)

        # The prompt is a combination of the system prompt and the data
        prompt = config.LAYOUT_AWARE_TRANSLATE_PROMPT + "\n\n" + json_input

        model = genai.GenerativeModel(model_name="gemini-2.5-pro")
        response = model.generate_content(prompt, request_options={"timeout": 900})

        # Clean the response from the model
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[len("```json"):].strip()
        if raw_text.endswith("```"):
            raw_text = raw_text[:-len("```")].strip()

        # Parse the JSON response
        translated_content = json.loads(raw_text)
        return translated_content

    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON response from API: {e}")
        logging.debug(f"Raw response was: {raw_text}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during translation API call: {e}")
        # Re-raising is an option, but for now, we'll return None to signal failure
        return None

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
        logging.warning(f"{log_prefix} PDF parsing yielded no text blocks. The PDF might be image-based or empty. Task will be marked as successful.")
        return True # Nothing to translate, so we consider it a success.

    # --- 2. Get layout-aware translation ---
    translated_content = _get_translation_with_layout(structured_content, api_key)

    if translated_content is None:
        logging.error(f"{log_prefix} Layout-aware translation failed.")
        return False # Signal a controllable failure to the scheduler

    # --- 3. Log results ---
    logging.success(f"{log_prefix} Successfully received translated layout data.")
    logging.info(f"{log_prefix} Translated {len(translated_content)} text blocks. First block: {translated_content[0] if translated_content else 'N/A'}")

    # For now, the task is complete after successful translation and logging.
    # The LaTeX generation will be a separate step.
    # We can save the translated content to a file for inspection.
    translated_json_path = task_output_dir / "translated_layout.json"
    with open(translated_json_path, 'w', encoding='utf-8') as f:
        json.dump(translated_content, f, ensure_ascii=False, indent=2)
    logging.info(f"{log_prefix} Translated data saved to {translated_json_path}")

    return True
