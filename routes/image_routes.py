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
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import RequestEntityTooLarge

from services.image_service import (
    OUTPUT_EXTENSIONS,
    SUPPORTED_IMAGE_FORMATS,
    ImageProcessingError,
    compress_image,
    convert_image,
    crop_rotate_image,
    pencil_sketch,
    resize_image,
)
from services.file_storage import get_session_owner_id

image_bp = Blueprint("image", __name__)
DOWNLOAD_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
IMAGE_OPERATIONS = {
    "compress-image": {
        "title": "Compress image",
        "description": "Choose a quality level to reduce an image file while keeping its dimensions.",
        "button": "Compress image",
        "quality": True,
        "format": False,
        "crop": False,
    },
    "convert-image": {
        "title": "Convert image",
        "description": "Convert JPG, PNG, or WebP images to another format.",
        "button": "Convert image",
        "quality": False,
        "format": True,
        "crop": False,
    },
    "pencil-sketch": {
        "title": "Pencil sketch",
        "description": "Create a pencil-style sketch from a JPG, PNG, or WebP image.",
        "button": "Create sketch",
        "quality": False,
        "format": False,
        "crop": False,
    },
    "crop-rotate-image": {
        "title": "Crop and rotate",
        "description": "Crop a rectangle using pixel coordinates, then rotate the result.",
        "button": "Crop and rotate",
        "quality": False,
        "format": False,
        "crop": True,
    },
}


def _render_image_operation(
    operation: str,
    *,
    error: str | None = None,
    result: dict[str, str | int] | None = None,
    status: int = 200,
):
    return (
        render_template(
            "image/operation.html",
            operation=IMAGE_OPERATIONS[operation],
            operation_id=operation,
            error=error,
            result=result,
            max_upload_mb=current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
        ),
        status,
    )


def _image_output(output_format: str) -> tuple[UUID, Path, str]:
    result_id = uuid4()
    extension = OUTPUT_EXTENSIONS[output_format]
    owner_id = get_session_owner_id(create=True)
    output_path = (
        Path(current_app.config["OUTPUT_FOLDER"])
        / owner_id
        / f"{result_id.hex}{extension}"
    )
    return result_id, output_path, extension


def _image_result(
    operation: str,
    result_id: UUID,
    extension: str,
    size: tuple[int, int],
) -> dict[str, str | int]:
    session[f"last_{operation}_result"] = {
        "id": result_id.hex,
        "extension": extension,
        "operation": operation,
    }
    return {
        "width": size[0],
        "height": size[1],
        "download_url": url_for(
            "image.download_image_operation",
            operation=operation,
            result_id=result_id,
        ),
        "download_name": f"processed-image{extension}",
    }


def _render_resize_page(
    *,
    error: str | None = None,
    result: dict[str, int | str] | None = None,
    width: str | int = 800,
    height: str | int = 600,
    maintain_aspect: bool = True,
    status: int = 200,
):
    return (
        render_template(
            "image/resize.html",
            error=error,
            result=result,
            width=width,
            height=height,
            maintain_aspect=maintain_aspect,
            max_dimension=current_app.config["MAX_IMAGE_DIMENSION"],
            max_upload_mb=current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
        ),
        status,
    )


@image_bp.route("/tools/resize-image", methods=["GET", "POST"])
def resize_image_page():
    if request.method == "GET":
        return _render_resize_page()

    uploaded_file = request.files.get("image")
    if uploaded_file is None or not uploaded_file.filename:
        return _render_resize_page(
            error="Choose an image file before resizing.",
            status=400,
        )

    extension = PurePosixPath(uploaded_file.filename.replace("\\", "/")).suffix.lower()
    expected_format = SUPPORTED_IMAGE_FORMATS.get(extension)
    if expected_format is None:
        return _render_resize_page(
            error="Choose a JPG, PNG, or WebP image.",
            status=400,
        )

    try:
        width = int(request.form.get("width", ""))
        height = int(request.form.get("height", ""))
    except (TypeError, ValueError):
        return _render_resize_page(
            error="Enter a whole number for both width and height.",
            status=400,
        )

    max_dimension = current_app.config["MAX_IMAGE_DIMENSION"]
    if not (1 <= width <= max_dimension and 1 <= height <= max_dimension):
        return _render_resize_page(
            error=f"Width and height must each be between 1 and {max_dimension} pixels.",
            width=width,
            height=height,
            status=400,
        )

    maintain_aspect = request.form.get("maintain_aspect") == "on"
    result_id = uuid4()
    output_extension = OUTPUT_EXTENSIONS[expected_format]
    owner_id = get_session_owner_id(create=True)
    output_path = (
        Path(current_app.config["OUTPUT_FOLDER"])
        / owner_id
        / f"{result_id.hex}{output_extension}"
    )

    try:
        output_width, output_height = resize_image(
            uploaded_file.stream,
            output_path,
            width,
            height,
            maintain_aspect,
            expected_format,
        )
    except ImageProcessingError as error:
        return _render_resize_page(
            error=str(error),
            width=width,
            height=height,
            maintain_aspect=maintain_aspect,
            status=400,
        )
    except OSError:
        current_app.logger.exception("Could not save the resized image.")
        return _render_resize_page(
            error="The image could not be saved. Please try again.",
            width=width,
            height=height,
            maintain_aspect=maintain_aspect,
            status=500,
        )

    session["last_resize_result"] = {
        "id": result_id.hex,
        "extension": output_extension,
    }
    return _render_resize_page(
        result={
            "width": output_width,
            "height": output_height,
            "download_url": url_for(
                "image.download_resized_image",
                result_id=result_id,
            ),
        },
        width=width,
        height=height,
        maintain_aspect=maintain_aspect,
    )


@image_bp.get("/tools/resize-image/<uuid:result_id>/download")
def download_resized_image(result_id: UUID):
    result = session.get("last_resize_result")
    if not isinstance(result, dict) or result.get("id") != result_id.hex:
        abort(404)

    owner_id = get_session_owner_id(create=False)
    extension = result.get("extension")
    if owner_id is None or extension not in DOWNLOAD_MIME_TYPES:
        abort(404)

    output_path = (
        Path(current_app.config["OUTPUT_FOLDER"])
        / owner_id
        / f"{result_id.hex}{extension}"
    )
    if not output_path.is_file():
        abort(404)

    return send_file(
        output_path,
        as_attachment=True,
        download_name=f"resized-image{extension}",
        mimetype=DOWNLOAD_MIME_TYPES[extension],
    )


@image_bp.errorhandler(RequestEntityTooLarge)
def handle_upload_too_large(_error: RequestEntityTooLarge):
    if request.endpoint in {
        "image.compress_image_page",
        "image.convert_image_page",
        "image.pencil_sketch_page",
        "image.crop_rotate_image_page",
    }:
        operation = {
            "image.compress_image_page": "compress-image",
            "image.convert_image_page": "convert-image",
            "image.pencil_sketch_page": "pencil-sketch",
            "image.crop_rotate_image_page": "crop-rotate-image",
        }[request.endpoint]
        return _render_image_operation(
            operation,
            error=(
                "The image is too large. "
                f"The maximum upload size is "
                f"{current_app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB."
            ),
            status=413,
        )
    return _render_resize_page(
        error=(
            "The image is too large. "
            f"The maximum upload size is "
            f"{current_app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB."
        ),
        status=413,
    )


def _uploaded_image() -> tuple[FileStorage | None, str | None]:
    uploaded_file = request.files.get("image")
    if uploaded_file is None or not uploaded_file.filename:
        return None, None
    extension = PurePosixPath(
        uploaded_file.filename.replace("\\", "/")
    ).suffix.lower()
    return uploaded_file, SUPPORTED_IMAGE_FORMATS.get(extension)


def _validated_image_upload() -> tuple[FileStorage, str]:
    uploaded_file, expected_format = _uploaded_image()
    if uploaded_file is None:
        raise ImageProcessingError("Choose an image file before processing.")
    if expected_format is None:
        raise ImageProcessingError("Choose a JPG, PNG, or WebP image.")
    return uploaded_file, expected_format


@image_bp.route("/tools/compress-image", methods=["GET", "POST"])
def compress_image_page():
    operation = "compress-image"
    if request.method == "GET":
        return _render_image_operation(operation)
    try:
        uploaded_file, expected_format = _validated_image_upload()
    except ImageProcessingError as error:
        return _render_image_operation(
            operation,
            error=str(error),
            status=400,
        )
    try:
        quality = int(request.form.get("quality", ""))
    except (TypeError, ValueError):
        return _render_image_operation(
            operation,
            error="Enter a whole number for image quality.",
            status=400,
        )
    if not 1 <= quality <= 100:
        return _render_image_operation(
            operation,
            error="Image quality must be between 1 and 100.",
            status=400,
        )
    result_id, output_path, extension = _image_output(expected_format)
    try:
        size = compress_image(
            uploaded_file.stream,
            output_path,
            expected_format,
            quality,
        )
    except ImageProcessingError as error:
        output_path.unlink(missing_ok=True)
        return _render_image_operation(operation, error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save the compressed image.")
        output_path.unlink(missing_ok=True)
        return _render_image_operation(
            operation,
            error="The compressed image could not be saved. Please try again.",
            status=500,
        )
    result = _image_result(operation, result_id, extension, size)
    result["message"] = f"Compressed image at {quality}% quality."
    return _render_image_operation(operation, result=result)


@image_bp.route("/tools/convert-image", methods=["GET", "POST"])
def convert_image_page():
    operation = "convert-image"
    if request.method == "GET":
        return _render_image_operation(operation)
    try:
        uploaded_file, expected_format = _validated_image_upload()
    except ImageProcessingError as error:
        return _render_image_operation(
            operation,
            error=str(error),
            status=400,
        )
    output_format = request.form.get("output_format", "")
    if output_format not in OUTPUT_EXTENSIONS:
        return _render_image_operation(
            operation,
            error="Choose JPG, PNG, or WebP as the output format.",
            status=400,
        )
    result_id, output_path, extension = _image_output(output_format)
    try:
        size = convert_image(
            uploaded_file.stream,
            output_path,
            expected_format,
            output_format,
        )
    except ImageProcessingError as error:
        output_path.unlink(missing_ok=True)
        return _render_image_operation(operation, error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save the converted image.")
        output_path.unlink(missing_ok=True)
        return _render_image_operation(
            operation,
            error="The converted image could not be saved. Please try again.",
            status=500,
        )
    result = _image_result(operation, result_id, extension, size)
    result["message"] = f"Converted the image to {output_format}."
    return _render_image_operation(operation, result=result)


@image_bp.route("/tools/pencil-sketch", methods=["GET", "POST"])
def pencil_sketch_page():
    operation = "pencil-sketch"
    if request.method == "GET":
        return _render_image_operation(operation)
    try:
        uploaded_file, expected_format = _validated_image_upload()
    except ImageProcessingError as error:
        return _render_image_operation(
            operation,
            error=str(error),
            status=400,
        )
    result_id, output_path, extension = _image_output("PNG")
    try:
        size = pencil_sketch(uploaded_file.stream, output_path, expected_format)
    except ImageProcessingError as error:
        output_path.unlink(missing_ok=True)
        return _render_image_operation(operation, error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save the pencil sketch.")
        output_path.unlink(missing_ok=True)
        return _render_image_operation(
            operation,
            error="The pencil sketch could not be saved. Please try again.",
            status=500,
        )
    result = _image_result(operation, result_id, extension, size)
    result["message"] = "Created a pencil-style sketch."
    return _render_image_operation(operation, result=result)


@image_bp.route("/tools/crop-rotate-image", methods=["GET", "POST"])
def crop_rotate_image_page():
    operation = "crop-rotate-image"
    if request.method == "GET":
        return _render_image_operation(operation)
    try:
        uploaded_file, expected_format = _validated_image_upload()
    except ImageProcessingError as error:
        return _render_image_operation(
            operation,
            error=str(error),
            status=400,
        )
    try:
        left = int(request.form.get("left", ""))
        top = int(request.form.get("top", ""))
        width = int(request.form.get("crop_width", ""))
        height = int(request.form.get("crop_height", ""))
        rotation = int(request.form.get("rotation", ""))
    except (TypeError, ValueError):
        return _render_image_operation(
            operation,
            error="Enter whole pixel numbers for the crop and rotation.",
            status=400,
        )
    result_id, output_path, extension = _image_output(expected_format)
    try:
        size = crop_rotate_image(
            uploaded_file.stream,
            output_path,
            expected_format,
            left,
            top,
            width,
            height,
            rotation,
        )
    except ImageProcessingError as error:
        output_path.unlink(missing_ok=True)
        return _render_image_operation(operation, error=str(error), status=400)
    except OSError:
        current_app.logger.exception("Could not save the cropped and rotated image.")
        output_path.unlink(missing_ok=True)
        return _render_image_operation(
            operation,
            error="The edited image could not be saved. Please try again.",
            status=500,
        )
    result = _image_result(operation, result_id, extension, size)
    result["message"] = f"Cropped and rotated image to {size[0]} × {size[1]} pixels."
    return _render_image_operation(operation, result=result)


@image_bp.get("/tools/image-download/<operation>/<uuid:result_id>")
def download_image_operation(operation: str, result_id: UUID):
    if operation not in IMAGE_OPERATIONS:
        abort(404)
    result = session.get(f"last_{operation}_result")
    if (
        not isinstance(result, dict)
        or result.get("id") != result_id.hex
        or result.get("operation") != operation
    ):
        abort(404)
    owner_id = get_session_owner_id(create=False)
    extension = result.get("extension")
    if owner_id is None or extension not in DOWNLOAD_MIME_TYPES:
        abort(404)
    output_path = (
        Path(current_app.config["OUTPUT_FOLDER"])
        / owner_id
        / f"{result_id.hex}{extension}"
    )
    if not output_path.is_file():
        abort(404)
    return send_file(
        output_path,
        as_attachment=True,
        download_name=f"processed-image{extension}",
        mimetype=DOWNLOAD_MIME_TYPES[extension],
    )
