import io
from pathlib import Path

from PIL import Image, ImageOps

from config import appsetting

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass


def save_jpeg(upload, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = upload.read()
    if not data:
        raise ValueError("沒有讀到檔案")
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img.thumbnail((appsetting.jpeg_max_edge, appsetting.jpeg_max_edge))
    img.save(dest, "JPEG", quality=85, optimize=True)
