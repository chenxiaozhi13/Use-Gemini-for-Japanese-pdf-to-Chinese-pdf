import logging
import shutil
import subprocess
import os
import json
import google.generativeai as genai
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer
from reportlab.pdfgen import canvas
from reportlab.pdfbase import ttfonts, pdfmetrics
from . import config
from . import task_manager

def _parse_pdf_with_coordinates(pdf_path):
    """
    Parses a PDF to extract text blocks and page dimensions using pdfminer.six.

    Args:
        pdf_path (str or Path): The path to the PDF file.

    Returns:
        tuple: A tuple containing:
               - list: A list of text block dictionaries.
               - list: A list of page dimension tuples (width, height).
               Returns ([], []) on failure.
    """
    text_blocks = []
    page_dimensions = []
    try:
        for page_layout in extract_pages(pdf_path):
            page_dimensions.append((page_layout.width, page_layout.height))
            page_index = page_layout.pageid - 1  # pdfminer pageid is 1-based
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    text = element.get_text().strip()
                    if text:  # Only add non-empty text blocks
                        text_blocks.append({
                            'page': page_index,
                            'text': text,
                            'coords': element.bbox
                        })
        logging.info(f"Successfully parsed {pdf_path} and found {len(text_blocks)} text blocks across {len(page_dimensions)} pages.")
    except Exception as e:
        logging.error(f"Failed to parse PDF {pdf_path} with pdfminer.six: {e}")
        return [], []  # Return empty lists to allow process to potentially continue
    return text_blocks, page_dimensions

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

def _rebuild_pdf_from_layout(translated_layout, page_dimensions, output_path):
    """
    Reconstructs a PDF from translated layout data using reportlab.

    Args:
        translated_layout (list): The list of translated text block dictionaries.
        page_dimensions (list): A list of (width, height) tuples for each page.
        output_path (Path): The path to save the newly generated PDF.

    Returns:
        bool: True on success, False on failure.
    """
    logging.info(f"Rebuilding PDF at {output_path}...")

    # --- CRITICAL: Font Registration ---
    # ReportLab needs a TrueType font file that supports CJK characters.
    # The path below is a placeholder. A CJK font (e.g., Noto Sans CJK SC,
    # WenQuanYi, SimSun) MUST be available at this path in the execution
    # environment for the PDF to render correctly.
    cjk_font_path = '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc'
    font_name = 'CJK-Regular'

    try:
        pdfmetrics.registerFont(ttfonts.TTFont(font_name, cjk_font_path))
    except Exception as e:
        logging.error(f"CRITICAL: Could not register CJK font from '{cjk_font_path}'. Error: {e}")
        logging.error("Cannot proceed without a CJK font. Please install a suitable font and update the path in `_rebuild_pdf_from_layout`.")
        return False

    # Group text blocks by page number for easier processing
    blocks_by_page = {}
    for block in translated_layout:
        page_num = block['page']
        if page_num not in blocks_by_page:
            blocks_by_page[page_num] = []
        blocks_by_page[page_num].append(block)

    try:
        c = canvas.Canvas(str(output_path))
        for i, (width, height) in enumerate(page_dimensions):
            c.setPageSize((width, height))

            if i in blocks_by_page:
                for block in blocks_by_page[i]:
                    x0, y0, x1, y1 = block['coords']
                    text = block['text']

                    # Estimate font size based on bounding box height
                    font_size = y1 - y0

                    c.setFont(font_name, font_size)
                    c.drawString(x0, y0, text)

            c.showPage() # Finalize the current page and move to the next

        c.save()
        logging.success(f"Successfully rebuilt PDF: {output_path}")
        return True
    except Exception as e:
        logging.error(f"An error occurred during PDF reconstruction with reportlab: {e}")
        return False

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
    structured_content, page_dimensions = _parse_pdf_with_coordinates(source_pdf_path)
    if not structured_content:
        logging.warning(f"{log_prefix} PDF parsing yielded no text blocks. The PDF might be image-based or empty. Task will be marked as successful.")
        return True # Nothing to translate, so we consider it a success.

    # --- 2. Get layout-aware translation ---
    translated_content = _get_translation_with_layout(structured_content, api_key)

    if translated_content is None:
        logging.error(f"{log_prefix} Layout-aware translation failed.")
        return False # Signal a controllable failure to the scheduler

    # --- 3. Rebuild PDF from translated layout ---
    output_pdf_path = task_output_dir / f"{task_id}_translated.pdf"

    rebuild_success = _rebuild_pdf_from_layout(
        translated_layout=translated_content,
        page_dimensions=page_dimensions,
        output_path=output_pdf_path
    )

    # The success of the entire task now depends on the PDF reconstruction
    return rebuild_success
