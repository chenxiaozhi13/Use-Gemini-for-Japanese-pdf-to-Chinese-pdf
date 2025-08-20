import logging
import shutil
import subprocess
import os
import json
import collections
import concurrent.futures
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

def _translate_page_chunk(page_data, api_key):
    """Translates a single page's worth of text blocks."""
    try:
        # Configure the generative AI library for this thread
        genai.configure(api_key=api_key)

        json_input = json.dumps(page_data, indent=2)
        prompt = config.LAYOUT_AWARE_TRANSLATE_PROMPT + "\n\n" + json_input

        model = genai.GenerativeModel(model_name="gemini-2.5-pro")
        response = model.generate_content(prompt, request_options={"timeout": 900})

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[len("```json"):].strip()
        if raw_text.endswith("```"):
            raw_text = raw_text[:-len("```")].strip()

        return json.loads(raw_text)
    except Exception as e:
        logging.error(f"Error translating page chunk: {e}")
        return None # Signal failure for this chunk

def _get_translation_with_layout(structured_content, api_key):
    """
    Sends structured text content to the Gemini API for translation concurrently by page.

    Args:
        structured_content (list): A list of dictionaries from _parse_pdf_with_coordinates.
        api_key (str): The API key to use for all concurrent calls.

    Returns:
        list or None: A list of dictionaries with translated text, or None on failure.
    """
    if not structured_content:
        return []

    # Group data by page
    blocks_by_page = collections.defaultdict(list)
    for block in structured_content:
        blocks_by_page[block['page']].append(block)

    logging.info(f"Submitting {len(blocks_by_page)} pages for concurrent translation.")

    all_translated_blocks = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Submit a translation task for each page
        future_to_page = {executor.submit(_translate_page_chunk, page_data, api_key): page
                          for page, page_data in blocks_by_page.items()}

        for future in concurrent.futures.as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                translated_page_blocks = future.result()
                if translated_page_blocks is None:
                    logging.error(f"Translation failed for page {page_num}. Aborting document.")
                    return None # A single page failure fails the whole document
                all_translated_blocks.extend(translated_page_blocks)
            except Exception as exc:
                logging.error(f"Page {page_num} generated an exception: {exc}")
                return None # Exception also fails the whole document

    # Sort all blocks by page number to ensure original order
    all_translated_blocks.sort(key=lambda x: x['page'])
    return all_translated_blocks

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

def process_task(source_pdf_path, api_key):
    """
    Processes a single PDF file task.

    This function encapsulates the core logic for handling one PDF task. It parses the file,
    sends the content for translation, and rebuilds the translated PDF.

    Args:
        source_pdf_path (str): The absolute path to the source PDF file.
        api_key (str): The Google AI API key to use for this task.

    Returns:
        bool: True on success, False on a controllable failure.

    Raises:
        Exception: For critical, non-retriable errors (e.g., API failures).
    """
    source_pdf_path = Path(source_pdf_path)
    task_id = source_pdf_path.stem
    pid = os.getpid()
    log_prefix = f"[{task_id}][PID {pid}]"

    logging.info(f"{log_prefix} Starting processing with key ...{api_key[-4:]}")

    # Configure the generative AI library with the specific key for this process
    genai.configure(api_key=api_key)

    # Define paths
    task_output_dir = config.FINAL_OUTPUT_DIR / task_id
    task_output_dir.mkdir(exist_ok=True, parents=True)

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
