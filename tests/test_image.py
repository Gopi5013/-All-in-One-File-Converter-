import re
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app()
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        OUTPUT_FOLDER=tmp_path / "outputs",
    )
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def image_file(size=(120, 60), image_format="PNG"):
    file = BytesIO()
    Image.new("RGB", size, color="navy").save(file, format=image_format)
    file.seek(0)
    return file


def post_resize(
    client,
    file=None,
    filename="sample.png",
    width="50",
    height="50",
    maintain_aspect=True,
):
    form_data = {
        "width": width,
        "height": height,
    }
    if maintain_aspect:
        form_data["maintain_aspect"] = "on"
    if file is not None:
        form_data["image"] = (file, filename)
    return client.post(
        "/tools/resize-image",
        data=form_data,
        content_type="multipart/form-data",
    )


def download_url(response):
    match = re.search(
        r'href="(/tools/resize-image/[^"]+/download)"',
        response.get_data(as_text=True),
    )
    assert match is not None
    return match.group(1)


def operation_download_url(response, operation):
    match = re.search(
        rf'href="(/tools/image-download/{re.escape(operation)}/[^"]+)"',
        response.get_data(as_text=True),
    )
    assert match is not None
    return match.group(1)


def test_resize_preserves_aspect_ratio_and_download_is_session_scoped(client, app):
    response = post_resize(client, file=image_file())

    assert response.status_code == 200
    assert b"Image resized to 50" in response.data
    assert b"25 pixels." in response.data

    url = download_url(response)
    download = client.get(url)
    assert download.status_code == 200
    assert download.mimetype == "image/png"
    assert Image.open(BytesIO(download.data)).size == (50, 25)

    other_client = app.test_client()
    assert other_client.get(url).status_code == 404


def test_resize_can_use_exact_dimensions(client):
    response = post_resize(
        client,
        file=image_file(),
        filename="portrait.png",
        width="25",
        height="40",
        maintain_aspect=False,
    )

    assert response.status_code == 200
    resized = client.get(download_url(response))
    assert Image.open(BytesIO(resized.data)).size == (25, 40)


@pytest.mark.parametrize(
    ("image_format", "filename", "mimetype"),
    [
        ("JPEG", "photo.jpg", "image/jpeg"),
        ("WEBP", "photo.webp", "image/webp"),
    ],
)
def test_resize_supports_jpeg_and_webp(client, image_format, filename, mimetype):
    response = post_resize(
        client,
        file=image_file(image_format=image_format),
        filename=filename,
    )

    assert response.status_code == 200
    download = client.get(download_url(response))
    assert download.mimetype == mimetype
    assert Image.open(BytesIO(download.data)).size == (50, 25)


def test_homepage_marks_resizer_as_available(client):
    response = client.get("/")

    assert response.status_code == 200
    assert re.search(rb"<strong>13</strong>\s+available of 13 tools", response.data)
    assert b'href="/tools/resize-image"' in response.data


def test_unsupported_extension_is_rejected(client):
    response = post_resize(client, file=image_file(), filename="sample.gif")

    assert response.status_code == 400
    assert b"Choose a JPG, PNG, or WebP image." in response.data


def test_file_content_must_match_extension(client):
    response = post_resize(
        client,
        file=image_file(image_format="PNG"),
        filename="sample.jpg",
    )

    assert response.status_code == 400
    assert b"file extension does not match" in response.data


def test_corrupt_image_is_rejected(client):
    response = post_resize(client, file=BytesIO(b"not an image"))

    assert response.status_code == 400
    assert b"not a valid supported image" in response.data


def test_missing_upload_is_rejected(client):
    response = post_resize(client)

    assert response.status_code == 400
    assert b"Choose an image file before resizing." in response.data


def test_oversized_upload_returns_clear_error(app):
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
    client = app.test_client()
    large_file = BytesIO(b"x" * (1024 * 1024 + 1))

    response = post_resize(client, file=large_file)

    assert response.status_code == 413
    assert b"maximum upload size is 1 MB" in response.data


@pytest.mark.parametrize(
    ("width", "height"),
    [("0", "50"), ("5001", "50"), ("abc", "50")],
)
def test_invalid_dimensions_are_rejected(client, width, height):
    response = post_resize(
        client,
        file=image_file(),
        width=width,
        height=height,
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "path",
    [
        "/tools/compress-image",
        "/tools/convert-image",
        "/tools/pencil-sketch",
        "/tools/crop-rotate-image",
    ],
)
def test_new_image_tool_pages_are_available(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert b"<form" in response.data


def test_new_image_tool_reports_upload_limit(app):
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
    client = app.test_client()
    response = client.post(
        "/tools/compress-image",
        data={
            "image": (BytesIO(b"x" * (1024 * 1024)), "large.png"),
            "quality": "80",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 413
    assert b"maximum upload size is 1 MB" in response.data


def test_compress_image_preserves_dimensions_and_downloads(client):
    response = client.post(
        "/tools/compress-image",
        data={
            "image": (image_file(), "sample.png"),
            "quality": "60",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    download = client.get(operation_download_url(response, "compress-image"))
    assert download.status_code == 200
    assert Image.open(BytesIO(download.data)).size == (120, 60)


def test_convert_image_changes_png_to_jpeg(client):
    response = client.post(
        "/tools/convert-image",
        data={
            "image": (image_file(), "sample.png"),
            "output_format": "JPEG",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    download = client.get(operation_download_url(response, "convert-image"))
    converted = Image.open(BytesIO(download.data))
    assert download.mimetype == "image/jpeg"
    assert converted.format == "JPEG"
    assert converted.mode == "RGB"


def test_pencil_sketch_returns_a_grayscale_png(client):
    response = client.post(
        "/tools/pencil-sketch",
        data={"image": (image_file(), "sample.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    download = client.get(operation_download_url(response, "pencil-sketch"))
    sketch = Image.open(BytesIO(download.data))
    assert sketch.format == "PNG"
    assert sketch.size == (120, 60)
    assert sketch.mode == "L"


def test_crop_rotate_image_applies_crop_before_rotation(client):
    response = client.post(
        "/tools/crop-rotate-image",
        data={
            "image": (image_file(), "sample.png"),
            "left": "10",
            "top": "5",
            "crop_width": "40",
            "crop_height": "20",
            "rotation": "90",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    download = client.get(operation_download_url(response, "crop-rotate-image"))
    assert Image.open(BytesIO(download.data)).size == (20, 40)


def test_crop_rotate_rejects_crop_outside_image(client):
    response = client.post(
        "/tools/crop-rotate-image",
        data={
            "image": (image_file(), "sample.png"),
            "left": "100",
            "top": "0",
            "crop_width": "40",
            "crop_height": "20",
            "rotation": "0",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert b"The crop must fit within the image dimensions" in response.data


def test_image_tool_downloads_remain_available_after_using_another_tool(client, app):
    sketch = client.post(
        "/tools/pencil-sketch",
        data={"image": (image_file(), "sample.png")},
        content_type="multipart/form-data",
    )
    converted = client.post(
        "/tools/convert-image",
        data={
            "image": (image_file(), "sample.png"),
            "output_format": "WEBP",
        },
        content_type="multipart/form-data",
    )

    sketch_download = client.get(
        operation_download_url(sketch, "pencil-sketch")
    )
    converted_download = client.get(
        operation_download_url(converted, "convert-image")
    )
    assert sketch_download.status_code == 200
    assert converted_download.status_code == 200
    assert (
        app.test_client()
        .get(operation_download_url(converted, "convert-image"))
        .status_code
        == 404
    )


def test_supplied_test_png_works_in_image_tools(client):
    image_path = Path(__file__).resolve().parents[1] / "test.png"
    image_data = image_path.read_bytes()

    resized = post_resize(
        client,
        file=BytesIO(image_data),
        filename="test.png",
        width="800",
        height="600",
    )
    assert resized.status_code == 200
    resized_download = client.get(download_url(resized))
    assert Image.open(BytesIO(resized_download.data)).size == (800, 517)

    sketch = client.post(
        "/tools/pencil-sketch",
        data={"image": (BytesIO(image_data), "test.png")},
        content_type="multipart/form-data",
    )
    assert sketch.status_code == 200
    sketch_download = client.get(operation_download_url(sketch, "pencil-sketch"))
    output = Image.open(BytesIO(sketch_download.data))
    assert output.size == (1492, 965)
    assert output.mode == "L"

    compressed = client.post(
        "/tools/compress-image",
        data={
            "image": (BytesIO(image_data), "test.png"),
            "quality": "55",
        },
        content_type="multipart/form-data",
    )
    assert compressed.status_code == 200
    compressed_download = client.get(
        operation_download_url(compressed, "compress-image")
    )
    assert Image.open(BytesIO(compressed_download.data)).size == (1492, 965)
    assert len(compressed_download.data) < len(image_data)

    converted = client.post(
        "/tools/convert-image",
        data={
            "image": (BytesIO(image_data), "test.png"),
            "output_format": "WEBP",
        },
        content_type="multipart/form-data",
    )
    assert converted.status_code == 200
    converted_download = client.get(
        operation_download_url(converted, "convert-image")
    )
    assert converted_download.mimetype == "image/webp"
    assert Image.open(BytesIO(converted_download.data)).size == (1492, 965)

    cropped = client.post(
        "/tools/crop-rotate-image",
        data={
            "image": (BytesIO(image_data), "test.png"),
            "left": "10",
            "top": "20",
            "crop_width": "100",
            "crop_height": "60",
            "rotation": "90",
        },
        content_type="multipart/form-data",
    )
    assert cropped.status_code == 200
    cropped_download = client.get(
        operation_download_url(cropped, "crop-rotate-image")
    )
    assert Image.open(BytesIO(cropped_download.data)).size == (60, 100)
