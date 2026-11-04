"""Turns an uploaded file (PDF, Word, or an image) into text: PyMuPDF for text PDFs, Tesseract OCR for scanned
pages and images, python-docx for Word files."""
import os

import fitz  # PyMuPDF

# Configure Tesseract OCR path (Windows default install location)
TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if os.path.exists(TESSERACT_PATH):
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    except ImportError:
        pass

# Allowed image extensions for OCR
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp'}


def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file using PyMuPDF.

    Handles three cases:
    1. Text-based PDFs — direct text extraction
    2. Scanned/image PDFs — renders pages to images and runs OCR
    3. Mixed PDFs — combines both approaches per page
    """
    text = ""
    doc = fitz.open(pdf_path)

    for page in doc:
        # Try normal text extraction first
        page_text = page.get_text()

        if page_text and len(page_text.strip()) > 20:
            text += page_text
        else:
            # Page has no selectable text — it's likely a scanned image
            # Try OCR using pytesseract
            ocr_text = _ocr_page(page)
            if ocr_text:
                text += ocr_text + "\n"

    doc.close()
    return text


def _ocr_page(page):
    """Run OCR on a single PDF page by rendering it to an image."""
    try:
        import pytesseract
        from PIL import Image
        import io as _io

        # Render the page at high resolution for better OCR accuracy
        pix = page.get_pixmap(dpi=300)
        img_data = pix.tobytes("png")
        img = Image.open(_io.BytesIO(img_data))
        return pytesseract.image_to_string(img)
    except ImportError:
        # pytesseract not installed — try basic extraction as last resort
        try:
            return page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        except Exception:
            return ""
    except Exception:
        return ""


def extract_text_from_image(image_path):
    """Extract text from an image file using pytesseract OCR."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return text
    except ImportError:
        return ""
    except Exception:
        return ""


def _has_tesseract():
    """Check if Tesseract OCR is available on the system."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_text_from_docx(file_path):
    """Extract text from a .docx file using python-docx."""
    try:
        from docx import Document
        doc = Document(file_path)
        return '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return ""


def extract_text(file_path):
    """Extract text from a PDF, Word, or image file, choosing the right method."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.pdf':
        return extract_text_from_pdf(file_path)
    elif ext == '.docx':
        return extract_text_from_docx(file_path)
    elif ext in IMAGE_EXTENSIONS:
        return extract_text_from_image(file_path)
    else:
        return ""
