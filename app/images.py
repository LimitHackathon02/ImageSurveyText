"""공통 이미지 전처리. 주제별 해상도 설정은 long_edge로 받습니다."""
import base64
import io
import warnings

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError


async def read_survey_uploads(image, images, config):
    if image is not None and images:
        raise HTTPException(422, "image와 images를 함께 보내지 마세요. 여러 사진은 images 필드를 반복해서 보내세요.")
    uploads = images or ([image] if image is not None else [])
    max_images = config.get("max_images", 1)
    if not 1 <= len(uploads) <= max_images:
        raise HTTPException(422, f"사진은 1~{max_images}장 업로드하세요.")
    per_file = config["max_upload_mb"] * 1024 * 1024
    total_mb = config.get("max_total_upload_mb", config["max_upload_mb"] * max_images)
    remaining = total_mb * 1024 * 1024
    raws = []
    for upload in uploads:
        raw = await upload.read(min(per_file, remaining) + 1)
        if len(raw) > per_file:
            raise HTTPException(413, f"사진 한 장은 {config['max_upload_mb']}MB 이하로 업로드하세요.")
        remaining -= len(raw)
        if remaining < 0:
            raise HTTPException(413, f"사진 전체 용량은 {total_mb}MB 이하로 업로드하세요.")
        raws.append(raw)
    return raws


def image_data_uri(raw: bytes, long_edge: int = 1280) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as original:
                if original.format not in {"PNG", "JPEG", "WEBP", "BMP"}:
                    raise ValueError("지원 형식 아님")
                if original.width < 4 or original.height < 4:
                    raise ValueError("이미지는 가로·세로 4px 이상이어야 합니다.")
                image = ImageOps.exif_transpose(original).convert("RGB")
                image.thumbnail((long_edge, long_edge))
                w, h = image.size
                size = (max(w, (h + 4) // 5, 4), max(h, (w + 4) // 5, 4))
                image = ImageOps.pad(image, size, color="white") if size != image.size else image
                out = io.BytesIO()
                image.save(out, format="JPEG", quality=85)
                return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "유효한 PNG/JPEG/WEBP/BMP 이미지를 사용하세요(최소 4px).") from None
