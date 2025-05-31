import base64
from PIL import Image
from IPython.display import display
from io import BytesIO
from pathlib import Path

project_root = Path(__file__).parents[2]


def get_base64_data(file_path):
    # 이미지를 한 번만 열기
    img = Image.open(file_path)
    width, height = img.size
    print(f"이미지 크기: {width}x{height}, 토큰 수:{(width * height) / 750}")
    # display(img)

    # BytesIO를 사용하여 이미지를 바이트로 변환
    buffer = BytesIO()
    img.save(buffer, format=img.format or "JPEG")  # 원본 포맷 유지 또는 JPEG 기본값
    base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return base64_data
