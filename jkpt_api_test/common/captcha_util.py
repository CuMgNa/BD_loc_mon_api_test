# common/captcha_util.py
import random
import time

import ddddocr


def generate_captcha_id() -> str:
    """生成18位 captchaId（毫秒时间戳 + 5 位随机数）"""
    timestamp = str(int(time.time() * 1000))
    random_5 = str(random.randint(10000, 99999))
    return timestamp + random_5


class CaptchaRecognizer:
    def __init__(self):
        self.ocr = ddddocr.DdddOcr(show_ad=False)

    def recognize(self, image_bytes: bytes) -> str:
        """识别验证码图片，返回验证码字符串"""
        result = self.ocr.classification(image_bytes)
        return result.strip()

    def recognize_from_response(self, response) -> str:
        """直接从 HTTP 响应内容识别验证码"""
        return self.recognize(response.content)