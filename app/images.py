"""공통 이미지 전처리. 주제별 해상도 설정은 long_edge로 받습니다."""
import base64
import io
import warnings

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError


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
