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


def _open_fit(upload):
    data = upload.read()
    if not data:
        raise ValueError(msg.empty_file)
    edge = appsetting.jpeg_max_edge
    img = Image.open(io.BytesIO(data))
    if (img.format or "").upper() == "JPEG":
        img.draft("RGB", (edge, edge))
    img = ImageOps.exif_transpose(img)
    img.thumbnail((edge, edge), Image.Resampling.BILINEAR, reducing_gap=2.0)
    return img


def _write_jpeg(img: Image.Image, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=80)


def save_jpeg(upload, dest: Path):
    img = _open_fit(upload).convert("RGB")
    _write_jpeg(img, dest)


def save_mark(upload, dest: Path):
    img = _open_fit(upload)
    if img.mode == "P":
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    elif img.mode in ("RGBA", "LA"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")


def save_jpeg_and_thumb(upload, dest: Path, thumb_dest: Path):
    img = _open_fit(upload).convert("RGB")
    _write_jpeg(img, dest)
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    thumb = img.crop((left, top, left + side, top + side))
    thumb = thumb.resize((THUMB_EDGE, THUMB_EDGE), Image.Resampling.BILINEAR)
    _write_jpeg(thumb, thumb_dest)
