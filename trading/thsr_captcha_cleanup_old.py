"""
trading/thsr_captcha_cleanup.py — 驗證碼圖片清晰化（僅供人眼辨識使用）

高鐵訂票頁面的驗證碼圖片本身混雜雜訊與一條干擾曲線，肉眼不容易看清楚。
這個模組單純把圖片「去噪 + 去除干擾曲線」，回傳一張黑白分明、方便使用者
自己讀取後手動輸入的乾淨圖片 —— 完全不做文字辨識／自動解碼，
驗證碼最終還是由使用者本人看圖手動輸入。

演算法沿用使用者提供的 pre_process.py 概念（多項式回歸描繪干擾曲線後，
在該位置做局部反相以抹除曲線），只是把輸入來源從「檔案路徑」
改為「記憶體中的圖片位元組」，以配合網頁版即時抓取驗證碼圖片的流程。
"""
import io

import cv2
import numpy as np
from PIL import Image
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import LinearRegression


import io
import logging
from PIL import Image

logger = logging.getLogger("trading.thsr_captcha_cleanup")

def clean_captcha_image(img_bytes: bytes, remove_curve: bool = True) -> bytes:
    """
    清洗高鐵驗證碼圖片，將其轉為高對比的黑白圖像，並有效濾除干擾線與背景。
    
    :param img_bytes: 從高鐵官網下載的原始圖片 bytes 數據
    :param remove_curve: 是否啟用去干擾線邏輯 (保留此參數以相容 thsr.py 的呼叫)
    :return: 處理後的 PNG 圖片 bytes 數據
    """
    try:
        # 1. 讀取圖片 bytes 並轉換成 Pillow Image 物件
        img = Image.open(io.BytesIO(img_bytes))
        img = img.convert("RGB")
        width, height = img.size
        
        # 2. 建立一個全新的單色（L 模式）圖像，預設底色全白 (255)
        new_img = Image.new("L", (width, height), 255)
        
        # 3. 雙層迴圈走訪像素進行閾值二值化過濾
        # 高鐵文字部分顏色通常極深，而干擾線或背景色彩相對明亮
        for y in range(height):
            for x in range(width):
                r, g, b = img.getpixel((x, y))
                
                # 色彩閾值判斷 (Thresholding)
                # 當 R, G, B 三色皆低於 130 時，代表該像素顏色非常深（極高機率是文字本身）
                if r < 130 and g < 130 and b < 130:
                    new_img.putpixel((x, y), 0)  # 設為黑色 (0)
                else:
                    new_img.putpixel((x, y), 255) # 設為白色 (255)
                    
        # 4. 將處理完畢的黑白影像寫回 bytes 緩衝區
        out_buffer = io.BytesIO()
        new_img.save(out_buffer, format="PNG")  # 轉為網頁相容性最佳的 PNG 格式
        return out_buffer.getvalue()

    except Exception as e:
        # 🛡️ 關鍵安全容錯機制：
        # 如果因為環境缺乏 Pillow 或圖片格式毀損，絕不崩潰，而是記錄日誌並直接回傳「原始高鐵圖 bytes」
        # 這樣可以確保即使淨化失敗，使用者仍然看得到原本的高鐵圖，流程完全不中斷！
        logger.error(f"⚠️ 驗證碼圖片淨化失敗，已降級回傳原始高鐵圖片！錯誤原因: {e}", exc_info=True)
        return img_bytes

#def clean_captcha_image(raw_bytes: bytes, remove_curve: bool = True) -> bytes:
#    """
#    去噪並（可選）移除干擾曲線，回傳清理後的 PNG 圖片位元組。
#
#    Args:
#        raw_bytes: 原始驗證碼圖片位元組（例如直接從 THSR 官網抓下來的 response.content）。
#        remove_curve: 是否嘗試移除橫貫圖片的干擾曲線。
#
#    Returns:
#        bytes: 清理後的 PNG 圖片位元組，供前端直接顯示給使用者看。
#    """
#    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
#    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
#    if img is None:
#        # 無法解碼時，原圖直接回傳，讓使用者至少看得到原始圖片
#        return raw_bytes
#
#    h, w, _ = img.shape
#    dst = cv2.fastNlMeansDenoisingColored(img, None, 30, 30, 7, 21)
#    _, thresh = cv2.threshold(dst, 127, 255, cv2.THRESH_BINARY_INV)
#    imgarr = cv2.cvtColor(thresh, cv2.COLOR_BGR2GRAY)
#
#    if not remove_curve:
#        result = Image.fromarray(255 - imgarr)  # 反相回「白底黑字」，方便閱讀
#        return _to_png_bytes(result)
#
#    try:
#        result_arr = _remove_curve(imgarr, thresh, w)
#        result = Image.fromarray(255 - result_arr)
#    except Exception:
#        # 曲線移除失敗（例如圖片樣式跟預期不同）時，退回僅去噪的版本，不讓整個功能掛掉
#        result = Image.fromarray(255 - imgarr)
#
#    return _to_png_bytes(result)


def _remove_curve(imgarr: np.ndarray, thresh: np.ndarray, w: int) -> np.ndarray:
    """以二次多項式回歸描繪干擾曲線的軌跡，並在該軌跡位置做局部反相以抹除曲線。"""
    work = imgarr.copy()
    work[:, 5:w - 5] = 0
    ys, xs = np.where(work == 255)
    if len(xs) < 10:
        raise ValueError("偵測到的曲線像素過少，可能沒有干擾曲線")

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
