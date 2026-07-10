"""
trading/thsr_captcha_cleanup.py — 驗證碼圖片清洗與 AI 自動解碼辨識核心
演算法：多項式回歸定位干擾線 -> 局部反相抹除 -> 開運算文字連通處理 -> Tesseract 精準解碼
"""
import io
import logging
import cv2
import numpy as np
import pytesseract
from PIL import Image
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import LinearRegression

logger = logging.getLogger("trading.thsr_captcha_cleanup")

def clean_captcha_image(raw_bytes: bytes, remove_curve: bool = True) -> bytes:
    """
    去噪並移除干擾曲線，回傳清理後最適合人眼與機器辨識的白底黑字 PNG 圖片位元組。
    """
    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return raw_bytes

    h, w, _ = img.shape
    dst = cv2.fastNlMeansDenoisingColored(img, None, 30, 30, 7, 21)
    _, thresh = cv2.threshold(dst, 127, 255, cv2.THRESH_BINARY_INV)
    imgarr = cv2.cvtColor(thresh, cv2.COLOR_BGR2GRAY)

    if not remove_curve:
        result = Image.fromarray(255 - imgarr)
        return _to_png_bytes(result)

    try:
        result_arr = _remove_curve(imgarr, thresh, w)
        result = Image.fromarray(255 - result_arr)
    except Exception as e:
        logger.warning(f"⚠️ 曲線多項式移除失敗，退回基礎去噪版本: {e}")
        result = Image.fromarray(255 - imgarr)

    return _to_png_bytes(result)


def solve_captcha_ai(raw_bytes: bytes) -> str:
    """
    高鐵驗證碼專用 AI 辨識引擎 (去干擾線後直接 OCR 識別)
    """
    try:
        arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return ""

        h, w, _ = img.shape
        dst = cv2.fastNlMeansDenoisingColored(img, None, 30, 30, 7, 21)
        _, thresh = cv2.threshold(dst, 127, 255, cv2.THRESH_BINARY_INV)
        imgarr = cv2.cvtColor(thresh, cv2.COLOR_BGR2GRAY)

        # 1. 執行您的高階多項式回歸去干擾線演算法
        try:
            cleaned_arr = _remove_curve(imgarr, thresh, w)
        except Exception:
            cleaned_arr = imgarr

        # 2. 形態學優化：微量膨脹與開運算，斷開細小噪點並黏合被文字切斷的筆畫
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        processed = cv2.morphologyEx(cleaned_arr, cv2.MORPH_OPEN, kernel)
        
        # 3. 轉為標準白底黑字（Tesseract 最愛的格式）
        final_img = 255 - processed

        # 4. 調用 Tesseract 引擎（限英數 4 碼，單行文字模式 psm 7）
        custom_config = r'--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
        pil_img = Image.fromarray(final_img)
        predicted_text = pytesseract.image_to_string(pil_img, config=custom_config)
        
        # 清洗與過濾非預期字元
        code = "".join(predicted_text.split()).strip()[:4].upper()
        logger.info(f"🤖 [AI 驗證碼核心] 降噪完成！自動解碼值為: {code}")
        return code
    except Exception as e:
        logger.error(f"❌ 驗證碼 AI 辨識失敗: {e}", exc_info=True)
        return ""


def _remove_curve(imgarr: np.ndarray, thresh: np.ndarray, w: int) -> np.ndarray:
    """以二次多項式回歸描繪干擾曲線的軌跡，並在該軌跡位置做局部反相以抹除曲線。"""
    work = imgarr.copy()
    work[:, 5:w - 5] = 0
    ys, xs = np.where(work == 255)
    if len(xs) < 10:
        raise ValueError("偵測到的曲線像素過少")

    X = np.array([xs])
    Y = 47 - ys

    poly_reg = PolynomialFeatures(degree=2)
    X_ = poly_reg.fit_transform(X.T)
    regr = LinearRegression()
    regr.fit(X_, Y)

    X2 = np.array([[i for i in range(0, w)]])
    X2_ = poly_reg.fit_transform(X2.T)

    newimg = cv2.cvtColor(thresh, cv2.COLOR_BGR2GRAY)
    for ele in np.column_stack([regr.predict(X2_).round(0), X2[0]]):
        pos = 47 - int(ele[0])
        col = int(ele[1])
        if 0 <= pos - 2 and pos + 4 <= newimg.shape[0]:
            newimg[pos - 2:pos + 4, col] = 255 - newimg[pos - 2:pos + 4, col]
    return newimg


def _to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
