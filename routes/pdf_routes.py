from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from flask import (
    Blueprint,
    abort,
    current_app,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge

from services.file_storage import get_session_owner_id
from services.pdf_service import (
    PdfConversionError,
    PdfProcessingError,
    convert_pdf_to_docx,
    convert_docx_to_pdf,
    compress_pdf,
    extract_pdf_pages,
    images_to_pdf,
    merge_pdfs,
    rotate_pdf,
    split_pdf,
)

pdf_bp = Blueprint("pdf", __name__)
MAX_PDF_FILES = 20
MAX_IMAGE_FILES = 20

PDF_OPERATIONS = {
    "split-pdf": {
        "title": "Split PDF",
        "description": "Choose page ranges to save as separate PDF files in a ZIP archive.",
        "button": "Split PDF",
        "accept": ".pdf,application/pdf",
        "ranges": True,
        "rotation": False,
    },
    "compress-pdf": {
        "title": "Compress PDF",
        "description": "Optimize PDF content streams and remove duplicate objects where possible.",
        "button": "Compress PDF",
        "accept": ".pdf,application/pdf",
        "ranges": False,
        "rotation": False,
    },
    "extract-pdf-pages": {
        "title": "Extract PDF pages",
        "description": "Save selected pages and ranges as a new PDF.",
        "button": "Extract pages",
        "accept": ".pdf,application/pdf",
        "ranges": True,
        "rotation": False,
    },
    "rotate-pdf": {
        "title": "Rotate PDF",
        "description": "Rotate all pages or selected pages by 90, 180, or 270 degrees.",
        "button": "Rotate PDF",
        "accept": ".pdf,application/pdf",
        "ranges": True,
        "rotation": True,
    },
    "images-to-pdf": {
        "title": "Images to PDF",
        "description": "Combine JPG, PNG, or WebP images into a PDF, one image per page.",
        "button": "Create PDF",
        "accept": ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp",
        "ranges": False,
        "rotation": False,
    },
    "word-to-pdf": {
        "title": "Word to PDF",
        "description": "Convert a DOCX document to PDF using a locally installed copy of Microsoft Word.",
        "button": "Convert to PDF",
        "accept": ".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "ranges": False,
        "rotation": False,
    },
}

PDF_DOWNLOADS = {
    "split-pdf": ("zip", "application/zip", "split-pdf.zip"),
    "compress-pdf": ("pdf", "application/pdf", "compressed.pdf"),
    "extract-pdf-pages": ("pdf", "application/pdf", "extracted-pages.pdf"),
    "rotate-pdf": ("pdf", "application/pdf", "rotated.pdf"),
    "images-to-pdf": ("pdf", "application/pdf", "images.pdf"),
    "word-to-pdf": ("pdf", "application/pdf", "converted.pdf"),
}


def _render_pdf_operation(
    operation: str,
    *,
    error: str | None = None,
    result: dict[str, str] | None = None,
    status: int = 200,
):
    return (
        render_template(
            "pdf/operation.html",
            operation=PDF_OPERATIONS[operation],
            operation_id=operation,
            error=error,
            result=result,
            max_upload_mb=current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
            max_pdf_files=MAX_PDF_FILES,
            max_image_files=MAX_IMAGE_FILES,
        ),
        status,
    )


def _pdf_output(operation: str) -> tuple[UUID, Path]:
    result_id = uuid4()
    owner_id = get_session_owner_id(create=True)
    extension = PDF_DOWNLOADS[operation][0]
    output_path = (
        Path(current_app.config["OUTPUT_FOLDER"])
        / owner_id
        / f"{result_id.hex}.{extension}"
    )
    return result_id, output_path


def _pdf_result(operation: str, result_id: UUID) -> dict[str, str]:
    session[f"last_{operation}_result"] = {"id": result_id.hex}
    return {
        "download_url": url_for(
            "pdf.download_pdf_operation",
            operation=operation,
            result_id=result_id,
        ),
        "download_name": PDF_DOWNLOADS[operation][2],
    }


def _valid_pdf_upload(uploaded_file) -> bool:
    return bool(uploaded_file and uploaded_file.filename) and (
        PurePosixPath(uploaded_file.filename.replace("\\", "/")).suffix.lower()
        == ".pdf"
    )


def _render_merge_page(
    *,
    error: str | None = None,
    result: dict[str, int | str] | None = None,
    status: int = 200,
):
    return (
        render_template(
            "pdf/merge.html",
            error=error,
            result=result,
            max_upload_mb=current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
            max_pdf_files=MAX_PDF_FILES,
        ),
        status,
    )


def _render_pdf_to_word_page(
    *,
    error: str | None = None,
    result: dict[str, int | str] | None = None,
    status: int = 200,
):
    return (
        render_template(
            "pdf/to_word.html",
            error=error,
            result=result,
            max_upload_mb=current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
        ),
        status,
    )


@pdf_bp.route("/tools/merge-pdf", methods=["GET", "POST"])
def merge_pdf_page():
    if request.method == "GET":
        return _render_merge_page()

    pdf_files = request.files.getlist("pdfs")
    if len(pdf_files) < 2:
        return _render_merge_page(
            error="Choose at least two PDF files to merge.",
            status=400,
        )
    if len(pdf_files) > MAX_PDF_FILES:
        return _render_merge_page(
            error=f"Choose no more than {MAX_PDF_FILES} PDF files.",
            status=400,
        )
    if any(not pdf_file.filename for pdf_file in pdf_files):
        return _render_merge_page(
            error="Every selected file must have a filename.",
            status=400,
        )
    has_unsupported_extension = any(
        Path(pdf_file.filename.replace("\\", "/")).suffix.lower() != ".pdf"
        for pdf_file in pdf_files
    )
    if has_unsupported_extension:
        return _render_merge_page(
            error="Choose PDF files only.",
            status=400,
        )

    result_id = uuid4()
    owner_id = get_session_owner_id(create=True)
    output_path = (
        Path(current_app.config["OUTPUT_FOLDER"])
        / owner_id
        / f"{result_id.hex}.pdf"
    )

    try:
        page_count = merge_pdfs(
            [pdf_file.stream for pdf_file in pdf_files],
            output_path,
        )
    except PdfProcessingError as error:
        return _render_merge_page(error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save the merged PDF.")
        return _render_merge_page(
            error="The merged PDF could not be saved. Please try again.",
            status=500,
        )

    session["last_pdf_merge_result"] = {"id": result_id.hex}
    return _render_merge_page(
        result={
            "page_count": page_count,
            "download_url": url_for(
                "pdf.download_merged_pdf",
                result_id=result_id,
            ),
        }
    )


@pdf_bp.route("/tools/pdf-to-word", methods=["GET", "POST"])
def pdf_to_word_page():
    if request.method == "GET":
        return _render_pdf_to_word_page()

    uploaded_file = request.files.get("pdf")
    if uploaded_file is None or not uploaded_file.filename:
        return _render_pdf_to_word_page(
            error="Choose a PDF file before converting.",
            status=400,
        )

    extension = Path(uploaded_file.filename.replace("\\", "/")).suffix.lower()
    if extension != ".pdf":
        return _render_pdf_to_word_page(
            error="Choose a PDF file.",
            status=400,
        )

    result_id = uuid4()
    owner_id = get_session_owner_id(create=True)
    output_path = (
        Path(current_app.config["OUTPUT_FOLDER"])
        / owner_id
        / f"{result_id.hex}.docx"
    )

    try:
        page_count = convert_pdf_to_docx(uploaded_file.stream, output_path)
    except PdfConversionError:
        current_app.logger.exception("PDF-to-Word conversion failed.")
        return _render_pdf_to_word_page(
            error=(
                "This PDF could not be converted to Word. "
                "Scanned PDFs need OCR to produce editable text."
            ),
            status=422,
        )
    except PdfProcessingError as error:
        return _render_pdf_to_word_page(error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save the converted Word document.")
        return _render_pdf_to_word_page(
            error="The Word document could not be saved. Please try again.",
            status=500,
        )

    session["last_pdf_to_word_result"] = {"id": result_id.hex}
    return _render_pdf_to_word_page(
        result={
            "page_count": page_count,
            "download_url": url_for(
                "pdf.download_pdf_to_word",
                result_id=result_id,
            ),
        }
    )


@pdf_bp.get("/tools/pdf-to-word/<uuid:result_id>/download")
def download_pdf_to_word(result_id: UUID):
    result = session.get("last_pdf_to_word_result")
    if not isinstance(result, dict) or result.get("id") != result_id.hex:
        abort(404)

    owner_id = get_session_owner_id(create=False)
    if owner_id is None:
        abort(404)

    output_path = (
        Path(current_app.config["OUTPUT_FOLDER"])
        / owner_id
        / f"{result_id.hex}.docx"
    )
    if not output_path.is_file():
        abort(404)

    return send_file(
        output_path,
        as_attachment=True,
        download_name="converted.docx",
        mimetype=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )


@pdf_bp.get("/tools/merge-pdf/<uuid:result_id>/download")
def download_merged_pdf(result_id: UUID):
    result = session.get("last_pdf_merge_result")
    if not isinstance(result, dict) or result.get("id") != result_id.hex:
        abort(404)

    owner_id = get_session_owner_id(create=False)
    if owner_id is None:
        abort(404)

    output_path = (
        Path(current_app.config["OUTPUT_FOLDER"])
        / owner_id
        / f"{result_id.hex}.pdf"
    )
    if not output_path.is_file():
        abort(404)

    return send_file(
        output_path,
        as_attachment=True,
        download_name="merged.pdf",
        mimetype="application/pdf",
    )


@pdf_bp.errorhandler(RequestEntityTooLarge)
def handle_upload_too_large(_error: RequestEntityTooLarge):
    max_upload_mb = current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    if request.endpoint == "pdf.pdf_to_word_page":
        return _render_pdf_to_word_page(
            error=(
                "The PDF is too large. "
                f"The maximum upload size is {max_upload_mb} MB."
            ),
            status=413,
        )
    if request.endpoint in {
        "pdf.split_pdf_page",
        "pdf.compress_pdf_page",
        "pdf.extract_pdf_pages_page",
        "pdf.rotate_pdf_page",
        "pdf.images_to_pdf_page",
        "pdf.word_to_pdf_page",
    }:
        operation = {
            "pdf.split_pdf_page": "split-pdf",
            "pdf.compress_pdf_page": "compress-pdf",
            "pdf.extract_pdf_pages_page": "extract-pdf-pages",
            "pdf.rotate_pdf_page": "rotate-pdf",
            "pdf.images_to_pdf_page": "images-to-pdf",
            "pdf.word_to_pdf_page": "word-to-pdf",
        }[request.endpoint]
        return _render_pdf_operation(
            operation,
            error=(
                "The selected files are too large. "
                f"The maximum total upload size is {max_upload_mb} MB."
            ),
            status=413,
        )

    return _render_merge_page(
        error=(
            "The selected PDFs are too large. "
            f"The maximum total upload size is {max_upload_mb} MB."
        ),
        status=413,
    )


@pdf_bp.route("/tools/split-pdf", methods=["GET", "POST"])
def split_pdf_page():
    operation = "split-pdf"
    if request.method == "GET":
        return _render_pdf_operation(operation)
    uploaded_file = request.files.get("pdf")
    if not _valid_pdf_upload(uploaded_file):
        return _render_pdf_operation(
            operation,
            error="Choose a PDF file before splitting.",
            status=400,
        )
    page_ranges = request.form.get("page_ranges", "")
    result_id, output_path = _pdf_output(operation)
    try:
        page_count, output_count = split_pdf(
            uploaded_file.stream,
            output_path,
            page_ranges,
        )
    except PdfProcessingError as error:
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(operation, error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save split PDF files.")
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(
            operation,
            error="The split PDFs could not be saved. Please try again.",
            status=500,
        )
    result = _pdf_result(operation, result_id)
    result["message"] = (
        f"Split {page_count} PDF "
        f"{'page' if page_count == 1 else 'pages'} into {output_count} files."
    )
    return _render_pdf_operation(operation, result=result)


@pdf_bp.route("/tools/compress-pdf", methods=["GET", "POST"])
def compress_pdf_page():
    operation = "compress-pdf"
    if request.method == "GET":
        return _render_pdf_operation(operation)
    uploaded_file = request.files.get("pdf")
    if not _valid_pdf_upload(uploaded_file):
        return _render_pdf_operation(
            operation,
            error="Choose a PDF file before compressing.",
            status=400,
        )
    result_id, output_path = _pdf_output(operation)
    try:
        page_count, input_size, output_size = compress_pdf(
            uploaded_file.stream,
            output_path,
        )
    except PdfProcessingError as error:
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(operation, error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save the compressed PDF.")
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(
            operation,
            error="The compressed PDF could not be saved. Please try again.",
            status=500,
        )
    saved_size = max(input_size - output_size, 0)
    message = (
        f"Processed {page_count} pages. "
        f"Original: {input_size // 1024} KB; optimized: {output_size // 1024} KB."
    )
    if saved_size:
        message += f" Saved {saved_size // 1024} KB."
    else:
        message += " Lossless compression could not make the file smaller."
    result = _pdf_result(operation, result_id)
    result["message"] = message
    return _render_pdf_operation(operation, result=result)


@pdf_bp.route("/tools/extract-pdf-pages", methods=["GET", "POST"])
def extract_pdf_pages_page():
    operation = "extract-pdf-pages"
    if request.method == "GET":
        return _render_pdf_operation(operation)
    uploaded_file = request.files.get("pdf")
    if not _valid_pdf_upload(uploaded_file):
        return _render_pdf_operation(
            operation,
            error="Choose a PDF file before extracting pages.",
            status=400,
        )
    result_id, output_path = _pdf_output(operation)
    try:
        page_count = extract_pdf_pages(
            uploaded_file.stream,
            output_path,
            request.form.get("page_ranges", ""),
        )
    except PdfProcessingError as error:
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(operation, error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save the extracted PDF pages.")
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(
            operation,
            error="The extracted pages could not be saved. Please try again.",
            status=500,
        )
    result = _pdf_result(operation, result_id)
    result["message"] = f"Extracted {page_count} PDF pages."
    return _render_pdf_operation(operation, result=result)


@pdf_bp.route("/tools/rotate-pdf", methods=["GET", "POST"])
def rotate_pdf_page():
    operation = "rotate-pdf"
    if request.method == "GET":
        return _render_pdf_operation(operation)
    uploaded_file = request.files.get("pdf")
    if not _valid_pdf_upload(uploaded_file):
        return _render_pdf_operation(
            operation,
            error="Choose a PDF file before rotating.",
            status=400,
        )
    try:
        rotation = int(request.form.get("rotation", ""))
    except (TypeError, ValueError):
        return _render_pdf_operation(
            operation,
            error="Choose a valid rotation.",
            status=400,
        )
    result_id, output_path = _pdf_output(operation)
    try:
        page_count = rotate_pdf(
            uploaded_file.stream,
            output_path,
            request.form.get("page_ranges", ""),
            rotation,
        )
    except PdfProcessingError as error:
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(operation, error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save the rotated PDF.")
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(
            operation,
            error="The rotated PDF could not be saved. Please try again.",
            status=500,
        )
    result = _pdf_result(operation, result_id)
    result["message"] = f"Rotated pages in a {page_count}-page PDF."
    return _render_pdf_operation(operation, result=result)


@pdf_bp.route("/tools/images-to-pdf", methods=["GET", "POST"])
def images_to_pdf_page():
    operation = "images-to-pdf"
    if request.method == "GET":
        return _render_pdf_operation(operation)
    image_files = request.files.getlist("images")
    if not image_files or any(not image.filename for image in image_files):
        return _render_pdf_operation(
            operation,
            error="Choose at least one image to convert.",
            status=400,
        )
    if len(image_files) > MAX_IMAGE_FILES:
        return _render_pdf_operation(
            operation,
            error=f"Choose no more than {MAX_IMAGE_FILES} images.",
            status=400,
        )
    supported_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    if any(
        PurePosixPath(image.filename.replace("\\", "/")).suffix.lower()
        not in supported_extensions
        for image in image_files
    ):
        return _render_pdf_operation(
            operation,
            error="Choose JPG, PNG, or WebP images only.",
            status=400,
        )
    result_id, output_path = _pdf_output(operation)
    try:
        page_count = images_to_pdf(
            [image.stream for image in image_files],
            output_path,
        )
    except PdfProcessingError as error:
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(operation, error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save the images as a PDF.")
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(
            operation,
            error="The PDF could not be saved. Please try again.",
            status=500,
        )
    result = _pdf_result(operation, result_id)
    result["message"] = f"Created a PDF with {page_count} image pages."
    return _render_pdf_operation(operation, result=result)


@pdf_bp.route("/tools/word-to-pdf", methods=["GET", "POST"])
def word_to_pdf_page():
    operation = "word-to-pdf"
    if request.method == "GET":
        return _render_pdf_operation(operation)
    uploaded_file = request.files.get("document")
    if uploaded_file is None or not uploaded_file.filename:
        return _render_pdf_operation(
            operation,
            error="Choose a Word document before converting.",
            status=400,
        )
    extension = PurePosixPath(
        uploaded_file.filename.replace("\\", "/")
    ).suffix.lower()
    if extension != ".docx":
        return _render_pdf_operation(
            operation,
            error="Choose a DOCX Word document.",
            status=400,
        )
    result_id, output_path = _pdf_output(operation)
    try:
        page_count = convert_docx_to_pdf(uploaded_file.stream, output_path)
    except PdfConversionError:
        current_app.logger.exception("Word-to-PDF conversion failed.")
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(
            operation,
            error=(
                "Microsoft Word could not convert this document. "
                "Check that the DOCX file is valid and Word is available."
            ),
            status=422,
        )
    except PdfProcessingError as error:
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(operation, error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save the converted PDF.")
        output_path.unlink(missing_ok=True)
        return _render_pdf_operation(
            operation,
            error="The PDF could not be saved. Please try again.",
            status=500,
        )
    result = _pdf_result(operation, result_id)
    result["message"] = (
        f"Converted {page_count} Word "
        f"{'page' if page_count == 1 else 'pages'} to PDF."
    )
    return _render_pdf_operation(operation, result=result)


@pdf_bp.get("/tools/pdf-download/<operation>/<uuid:result_id>")
def download_pdf_operation(operation: str, result_id: UUID):
    download = PDF_DOWNLOADS.get(operation)
    if download is None:
        abort(404)
    result = session.get(f"last_{operation}_result")
    if not isinstance(result, dict) or result.get("id") != result_id.hex:
        abort(404)
    owner_id = get_session_owner_id(create=False)
    if owner_id is None:
        abort(404)
    extension, mimetype, download_name = download
    output_path = (
        Path(current_app.config["OUTPUT_FOLDER"])
        / owner_id
        / f"{result_id.hex}.{extension}"
    )
    if not output_path.is_file():
        abort(404)
    return send_file(
        output_path,
        as_attachment=True,
        download_name=download_name,
        mimetype=mimetype,
    )
