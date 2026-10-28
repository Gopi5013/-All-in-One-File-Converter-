import gc
import re
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Sequence
from uuid import uuid4

from pdf2docx import Converter
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError


class PdfProcessingError(ValueError):
    pass


class PdfConversionError(PdfProcessingError):
    pass


def _read_pdf(source: BinaryIO) -> PdfReader:
    try:
        reader = PdfReader(source, strict=True)
        if reader.is_encrypted:
            raise PdfProcessingError("Password-protected PDFs cannot be processed.")
        if not reader.pages:
            raise PdfProcessingError("The selected PDF has no pages.")
        return reader
    except PdfProcessingError:
        raise
    except (PdfReadError, OSError, ValueError) as error:
        raise PdfProcessingError(
            "The selected file is not a valid, readable PDF."
        ) from error


def parse_page_ranges(value: str, page_count: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    seen_pages: set[int] = set()
    parts = value.split(",")
    if not value.strip() or any(not part.strip() for part in parts):
        raise PdfProcessingError("Enter page numbers or ranges, such as 1-3, 5.")

    for part in parts:
        match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", part)
        if match is None:
            raise PdfProcessingError(
                "Enter page numbers or ranges, such as 1-3, 5."
            )
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first < 1 or last < first or last > page_count:
            raise PdfProcessingError(
                f"Page ranges must be between 1 and {page_count}."
            )
        pages = set(range(first, last + 1))
        if seen_pages.intersection(pages):
            raise PdfProcessingError("Page ranges cannot include a page more than once.")
        seen_pages.update(pages)
        ranges.append((first, last))

    return ranges


def _write_pages(reader: PdfReader, pages: Sequence[int]) -> bytes:
    writer = PdfWriter()
    try:
        for page_number in pages:
            writer.add_page(reader.pages[page_number])
        output = BytesIO()
        writer.write(output)
        return output.getvalue()
    finally:
        writer.close()


def split_pdf(
    source: BinaryIO,
    destination: Path,
    page_ranges: str,
) -> tuple[int, int]:
    reader = _read_pdf(source)
    ranges = parse_page_ranges(page_ranges, len(reader.pages))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for first, last in ranges:
            pages = range(first - 1, last)
            archive.writestr(
                f"pages-{first}-{last}.pdf",
                _write_pages(reader, pages),
            )
    selected_page_count = sum(last - first + 1 for first, last in ranges)
    return selected_page_count, len(ranges)


def extract_pdf_pages(
    source: BinaryIO,
    destination: Path,
    page_ranges: str,
) -> int:
    reader = _read_pdf(source)
    ranges = parse_page_ranges(page_ranges, len(reader.pages))
    selected_pages = [
        page_number
        for first, last in ranges
        for page_number in range(first - 1, last)
    ]
    writer = PdfWriter()
    try:
        for page_number in selected_pages:
            writer.add_page(reader.pages[page_number])
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as output_file:
            writer.write(output_file)
    finally:
        writer.close()
    return len(selected_pages)


def compress_pdf(source: BinaryIO, destination: Path) -> tuple[int, int, int]:
    reader = _read_pdf(source)
    writer = PdfWriter()
    try:
        writer.append(reader)
        for page in writer.pages:
            page.compress_content_streams()
        writer.compress_identical_objects(
            remove_duplicates=True,
            remove_unreferenced=True,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as output_file:
            writer.write(output_file)
    except (PdfReadError, OSError, ValueError) as error:
        raise PdfProcessingError("The selected PDF could not be compressed.") from error
    finally:
        writer.close()
    source.seek(0, 2)
    input_size = source.tell()
    output_size = destination.stat().st_size
    return len(reader.pages), input_size, output_size


def rotate_pdf(
    source: BinaryIO,
    destination: Path,
    page_ranges: str,
    rotation: int,
) -> int:
    if rotation not in (90, 180, 270):
        raise PdfProcessingError("Choose a rotation of 90, 180, or 270 degrees.")
    reader = _read_pdf(source)
    ranges = (
        parse_page_ranges(page_ranges, len(reader.pages))
        if page_ranges.strip()
        else [(1, len(reader.pages))]
    )
    selected_pages = {
        page_number
        for first, last in ranges
        for page_number in range(first - 1, last)
    }
    writer = PdfWriter()
    try:
        writer.append(reader)
        for page_number in selected_pages:
            writer.pages[page_number].rotate(rotation)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as output_file:
            writer.write(output_file)
    except (PdfReadError, OSError, ValueError) as error:
        raise PdfProcessingError("The selected PDF could not be rotated.") from error
    finally:
        writer.close()
    return len(reader.pages)


def merge_pdfs(
    sources: Sequence[BinaryIO],
    destination: Path,
) -> int:
    writer = PdfWriter()
    total_pages = 0

    try:
        for source in sources:
            reader = PdfReader(source, strict=True)
            if reader.is_encrypted:
                raise PdfProcessingError(
                    "Password-protected PDFs cannot be merged."
                )
            page_count = len(reader.pages)
            if page_count == 0:
                raise PdfProcessingError("Each PDF must contain at least one page.")
            writer.append(reader)
            total_pages += page_count

        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as output_file:
            writer.write(output_file)
    except PdfProcessingError:
        raise
    except (PdfReadError, OSError, ValueError) as error:
        raise PdfProcessingError(
            "One of the selected files is not a valid, readable PDF."
        ) from error
    finally:
        writer.close()

    return total_pages


def convert_pdf_to_docx(source: BinaryIO, destination: Path) -> int:
    pdf_data = source.read()
    if not pdf_data:
        raise PdfProcessingError("The selected PDF is empty.")

    try:
        reader = PdfReader(BytesIO(pdf_data), strict=True)
        if reader.is_encrypted:
            raise PdfProcessingError(
                "Password-protected PDFs cannot be converted."
            )
        page_count = len(reader.pages)
        if page_count == 0:
            raise PdfProcessingError("The selected PDF has no pages.")
    except PdfProcessingError:
        raise
    except (PdfReadError, OSError, ValueError) as error:
        raise PdfProcessingError(
            "The selected file is not a valid, readable PDF."
        ) from error

    with tempfile.TemporaryDirectory(prefix="document-tools-pdf-") as temp_dir:
        temp_folder = Path(temp_dir)
        source_path = temp_folder / "source.pdf"
        docx_path = temp_folder / "converted.docx"
        source_path.write_bytes(pdf_data)

        try:
            converter = Converter(str(source_path))
            try:
                converter.convert(str(docx_path))
            finally:
                converter.close()
        except Exception as error:
            raise PdfConversionError(
                "This PDF could not be converted to Word. "
                "Scanned PDFs need OCR to produce editable text."
            ) from error

        if (
            not docx_path.is_file()
            or docx_path.stat().st_size == 0
            or not zipfile.is_zipfile(docx_path)
        ):
            raise PdfConversionError(
                "The converter did not produce a valid Word document."
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_destination = destination.with_name(
            f".{destination.name}.{uuid4().hex}.tmp"
        )
        try:
            shutil.copyfile(docx_path, temporary_destination)
            temporary_destination.replace(destination)
        finally:
            temporary_destination.unlink(missing_ok=True)

    return page_count


def convert_docx_to_pdf(source: BinaryIO, destination: Path) -> int:
    document_data = source.read()
    if not document_data:
        raise PdfProcessingError("The selected Word document is empty.")

    try:
        from docx import Document
        from docx.opc.exceptions import PackageNotFoundError

        Document(BytesIO(document_data))
    except (OSError, ValueError, zipfile.BadZipFile, PackageNotFoundError) as error:
        raise PdfProcessingError(
            "The selected file is not a valid, readable Word document."
        ) from error

    try:
        import pythoncom
        import pywintypes
        import win32com.client
    except ImportError as error:
        raise PdfConversionError(
            "Microsoft Word automation is unavailable on this server."
        ) from error

    with tempfile.TemporaryDirectory(prefix="document-tools-word-") as temp_dir:
        temp_folder = Path(temp_dir)
        source_path = temp_folder / "source.docx"
        pdf_path = temp_folder / "converted.pdf"
        source_path.write_bytes(document_data)

        word = None
        document = None
        conversion_error = None
        pythoncom.CoInitialize()
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            word.AutomationSecurity = 3
            word.Options.UpdateLinksAtOpen = False
            document = word.Documents.Open(
                FileName=str(source_path),
                ConfirmConversions=False,
                ReadOnly=True,
                AddToRecentFiles=False,
                NoEncodingDialog=True,
                OpenAndRepair=False,
            )
            document.SaveAs2(
                FileName=str(pdf_path),
                FileFormat=17,
                AddToRecentFiles=False,
            )
        except pywintypes.com_error as error:
            conversion_error = error
        finally:
            try:
                if document is not None:
                    document.Close(SaveChanges=0)
            except pywintypes.com_error as error:
                conversion_error = conversion_error or error
            finally:
                document = None
                try:
                    if word is not None:
                        word.Quit(SaveChanges=0)
                except pywintypes.com_error as error:
                    conversion_error = conversion_error or error
                finally:
                    word = None
                    gc.collect()
                    pythoncom.CoUninitialize()
        if conversion_error is not None:
            raise PdfConversionError(
                "Microsoft Word could not convert this document to PDF."
            ) from conversion_error

        try:
            reader = PdfReader(str(pdf_path), strict=True)
            page_count = len(reader.pages)
            reader.close()
            if page_count == 0:
                raise PdfConversionError(
                    "Microsoft Word produced a PDF without any pages."
                )
        except (PdfReadError, OSError, ValueError) as error:
            raise PdfConversionError(
                "Microsoft Word did not produce a valid PDF."
            ) from error

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_destination = destination.with_name(
            f".{destination.name}.{uuid4().hex}.tmp"
        )
        try:
            shutil.copyfile(pdf_path, temporary_destination)
            temporary_destination.replace(destination)
        finally:
            temporary_destination.unlink(missing_ok=True)

    return page_count


def images_to_pdf(sources: Sequence[BinaryIO], destination: Path) -> int:
    if not sources:
        raise PdfProcessingError("Choose at least one image to convert.")

    from PIL import Image, ImageOps, UnidentifiedImageError
    from services.image_service import MAX_IMAGE_PIXELS

    pages = []
    total_pixels = 0
    try:
        for source in sources:
            with Image.open(source) as image:
                if image.format not in ("JPEG", "PNG", "WEBP"):
                    raise PdfProcessingError("Choose JPG, PNG, or WebP images only.")
                total_pixels += image.width * image.height
                if total_pixels > MAX_IMAGE_PIXELS:
                    raise PdfProcessingError(
                        "The combined image dimensions are too large to process safely."
                    )
                oriented = ImageOps.exif_transpose(image)
                try:
                    rgb_image = oriented.convert("RGB")
                    try:
                        rgb_image.load()
                        pages.append(rgb_image.copy())
                    finally:
                        rgb_image.close()
                finally:
                    if oriented is not image:
                        oriented.close()
    except PdfProcessingError:
        for page in pages:
            page.close()
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError) as error:
        for page in pages:
            page.close()
        raise PdfProcessingError(
            "One of the selected files is not a valid supported image."
        ) from error

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pages[0].save(
            destination,
            format="PDF",
            save_all=True,
            append_images=pages[1:],
            resolution=150,
        )
    except OSError as error:
        raise PdfProcessingError("The selected images could not be saved as a PDF.") from error
    finally:
        for page in pages:
            page.close()
    return len(pages)
