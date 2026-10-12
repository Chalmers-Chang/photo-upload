import io
from pathlib import Path

from PIL import Image, ImageOps

from config import appsetting
from config import msg

# 3cm on a 96dpi screen ≈ 113px
THUMB_EDGE = round(3 / 2.54 * 96)

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass


def _rgb_image(upload):
    data = upload.read()
    if not data:
        raise ValueError(msg.empty_file)
    edge = appsetting.jpeg_max_edge
    img = Image.open(io.BytesIO(data))
    if (img.format or "").upper() == "JPEG":
        img.draft("RGB", (edge, edge))
    return ImageOps.exif_transpose(img).convert("RGB")


def _write_jpeg(img: Image.Image, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=80)


def save_jpeg(upload, dest: Path):
    img = _rgb_image(upload)
    img.thumbnail((appsetting.jpeg_max_edge, appsetting.jpeg_max_edge), Image.Resampling.BILINEAR)
    _write_jpeg(img, dest)


def save_mark(upload, dest: Path):
    data = upload.read()
    if not data:
        raise ValueError(msg.empty_file)
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode == "P":
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    elif img.mode in ("RGBA", "LA"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")
    img.thumbnail(
        (appsetting.jpeg_max_edge, appsetting.jpeg_max_edge),
        Image.Resampling.BILINEAR,
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")


def save_jpeg_and_thumb(upload, dest: Path, thumb_dest: Path):
    img = _rgb_image(upload)
    fitted = img.copy()
    fitted.thumbnail((appsetting.jpeg_max_edge, appsetting.jpeg_max_edge), Image.Resampling.BILINEAR)
    _write_jpeg(fitted, dest)
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    thumb = img.crop((left, top, left + side, top + side))
    thumb = thumb.resize((THUMB_EDGE, THUMB_EDGE), Image.Resampling.BILINEAR)
    _write_jpeg(thumb, thumb_dest)
