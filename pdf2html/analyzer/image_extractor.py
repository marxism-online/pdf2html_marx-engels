from __future__ import annotations

import io
import math

from pdfminer.layout import LTFigure
from pdfminer.layout import LTImage
from PIL import Image


def extract_illustration_image(layout: object) -> bytes | None:
    for obj in layout:
        if isinstance(obj, LTFigure):
            for sub in obj:
                if isinstance(sub, LTImage):
                    return _ltimage_to_jpeg(sub)
    return None


def _ltimage_to_jpeg(ltimage: LTImage) -> bytes | None:
    attrs = ltimage.stream.attrs
    w = int(attrs.get("Width", 0))
    h = int(attrs.get("Height", 0))
    if not w or not h:
        return None

    filt_str = str(attrs.get("Filter", ""))
    if "DCTDecode" in filt_str:
        return ltimage.stream.get_data()

    data = ltimage.stream.get_data()
    row_bytes = math.ceil(w / 8)
    if len(data) == row_bytes * h:
        img = Image.frombytes("1", (w, h), data, "raw", "1")
    else:
        img = Image.frombytes("L", (w, h), data)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
