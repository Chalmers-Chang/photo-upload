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
    edge = appsetting.jpeg_max_edge
    img = Image.open(io.BytesIO(data))
    if (img.format or "").upper() == "JPEG":
        img.draft("RGB", (edge, edge))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img.thumbnail((edge, edge), Image.Resampling.BILINEAR)
    img.save(dest, "JPEG", quality=80)
