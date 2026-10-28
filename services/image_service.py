from pathlib import Path
from typing import BinaryIO

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

SUPPORTED_IMAGE_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}

OUTPUT_EXTENSIONS = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}

MAX_IMAGE_PIXELS = 40_000_000


class ImageProcessingError(ValueError):
    pass


def resize_image(
    source: BinaryIO,
    destination: Path,
    width: int,
    height: int,
    maintain_aspect: bool,
    expected_format: str,
) -> tuple[int, int]:
    try:
        with Image.open(source) as probe:
            if probe.format != expected_format:
                raise ImageProcessingError(
                    "The file extension does not match the image content."
                )
            if probe.width * probe.height > MAX_IMAGE_PIXELS:
                raise ImageProcessingError(
                    "The image dimensions are too large to process safely."
                )
            probe.verify()

        source.seek(0)
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original)
            if maintain_aspect:
                resized = ImageOps.contain(
                    image,
                    (width, height),
                    method=Image.Resampling.LANCZOS,
                )
            else:
                resized = image.resize(
                    (width, height),
                    resample=Image.Resampling.LANCZOS,
                )
            resized.load()
    except ImageProcessingError:
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError) as error:
        raise ImageProcessingError(
            "The uploaded file is not a valid supported image."
        ) from error

    if expected_format == "JPEG":
        if resized.mode not in ("RGB", "L"):
            resized = resized.convert("RGB")
    elif resized.mode not in ("RGB", "RGBA", "L", "LA"):
        resized = resized.convert("RGBA" if "A" in resized.getbands() else "RGB")

    destination.parent.mkdir(parents=True, exist_ok=True)
    save_options = {"format": expected_format}
    if expected_format == "JPEG":
        save_options.update(quality=90, optimize=True)
    elif expected_format == "WEBP":
        save_options.update(quality=90, method=6)
    elif expected_format == "PNG":
        save_options.update(optimize=True)

    resized.save(destination, **save_options)
    return resized.size


def _load_supported_image(source: BinaryIO, expected_format: str | None = None) -> Image.Image:
    try:
        with Image.open(source) as probe:
            if expected_format is not None and probe.format != expected_format:
                raise ImageProcessingError(
                    "The file extension does not match the image content."
                )
            if probe.format not in SUPPORTED_IMAGE_FORMATS.values():
                raise ImageProcessingError("Choose a JPG, PNG, or WebP image.")
            if probe.width * probe.height > MAX_IMAGE_PIXELS:
                raise ImageProcessingError(
                    "The image dimensions are too large to process safely."
                )
            probe.verify()

        source.seek(0)
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original)
            image.load()
            return image.copy()
    except ImageProcessingError:
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError) as error:
        raise ImageProcessingError(
            "The uploaded file is not a valid supported image."
        ) from error


def _save_image(
    image: Image.Image,
    destination: Path,
    image_format: str,
    quality: int,
    *,
    lossy_png: bool = False,
) -> None:
    output = image
    temporary_images = []
    try:
        if image_format == "JPEG":
            if image.mode not in ("RGB", "L"):
                output = image.convert("RGB")
        elif image.mode not in ("RGB", "RGBA", "L", "LA"):
            output = image.convert(
                "RGBA" if "A" in image.getbands() else "RGB"
            )
        if output is not image:
            temporary_images.append(output)
        if image_format == "PNG" and lossy_png and quality < 100:
            quantized = output.quantize(
                colors=max(2, round(quality * 256 / 100)),
                method=(
                    Image.Quantize.FASTOCTREE
                    if "A" in output.getbands()
                    else Image.Quantize.MEDIANCUT
                ),
            )
            temporary_images.append(quantized)
            output = quantized
        destination.parent.mkdir(parents=True, exist_ok=True)
        options: dict[str, int | bool | str] = {"format": image_format}
        if image_format in ("JPEG", "WEBP"):
            options.update(quality=quality, optimize=True)
            if image_format == "WEBP":
                options["method"] = 6
        elif image_format == "PNG":
            options.update(
                optimize=True,
                compress_level=9 if lossy_png else 6,
            )
        output.save(destination, **options)
    finally:
        for temporary_image in temporary_images:
            temporary_image.close()


def compress_image(
    source: BinaryIO,
    destination: Path,
    expected_format: str,
    quality: int,
) -> tuple[int, int]:
    if not 1 <= quality <= 100:
        raise ImageProcessingError("Choose a quality between 1 and 100.")
    image = _load_supported_image(source, expected_format)
    try:
        _save_image(
            image,
            destination,
            expected_format,
            quality,
            lossy_png=expected_format == "PNG",
        )
        return image.width, image.height
    except OSError as error:
        raise ImageProcessingError("The image could not be compressed.") from error
    finally:
        image.close()


def convert_image(
    source: BinaryIO,
    destination: Path,
    expected_format: str,
    output_format: str,
) -> tuple[int, int]:
    if output_format not in OUTPUT_EXTENSIONS:
        raise ImageProcessingError("Choose JPG, PNG, or WebP as the output format.")
    image = _load_supported_image(source, expected_format)
    try:
        _save_image(image, destination, output_format, 90)
        return image.width, image.height
    except OSError as error:
        raise ImageProcessingError("The image could not be converted.") from error
    finally:
        image.close()


def pencil_sketch(
    source: BinaryIO,
    destination: Path,
    expected_format: str,
) -> tuple[int, int]:
    image = _load_supported_image(source, expected_format)
    try:
        rgb = image.convert("RGB")
        try:
            rgb_image = np.array(rgb)
        finally:
            rgb.close()
        grayscale = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)
        inverted = 255 - grayscale
        blurred = cv2.GaussianBlur(inverted, (21, 21), 0)
        sketch = cv2.divide(grayscale, 255 - blurred, scale=256)
        output = Image.fromarray(sketch)
        try:
            _save_image(output, destination, "PNG", 100)
        finally:
            output.close()
        return image.width, image.height
    except (cv2.error, OSError, ValueError) as error:
        raise ImageProcessingError("The pencil sketch could not be created.") from error
    finally:
        image.close()


def crop_rotate_image(
    source: BinaryIO,
    destination: Path,
    expected_format: str,
    left: int,
    top: int,
    width: int,
    height: int,
    rotation: int,
) -> tuple[int, int]:
    if rotation not in (0, 90, 180, 270):
        raise ImageProcessingError("Choose a rotation of 0, 90, 180, or 270 degrees.")
    image = _load_supported_image(source, expected_format)
    try:
        if (
            left < 0
            or top < 0
            or width < 1
            or height < 1
            or left + width > image.width
            or top + height > image.height
        ):
            raise ImageProcessingError(
                f"The crop must fit within the image dimensions ({image.width} × {image.height})."
            )
        cropped = image.crop((left, top, left + width, top + height))
        try:
            result = cropped.rotate(-rotation, expand=True)
            try:
                _save_image(result, destination, expected_format, 90)
                return result.size
            finally:
                result.close()
        finally:
            cropped.close()
    except ImageProcessingError:
        raise
    except OSError as error:
        raise ImageProcessingError("The image could not be cropped and rotated.") from error
    finally:
        image.close()
