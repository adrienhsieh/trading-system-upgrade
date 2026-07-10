import cv2
import pytesseract

# 請將這裡改成您圖片真實的絕對路徑
image_path = r"D:\\SourceCode\\Web\\Python\\trading-system-full\\captcha_debug\\test_captcha.png"
img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

if img is None:
    print(f"錯誤：無法讀取圖片，請檢查路徑是否正確：{image_path}")
else:
    # 現在 img 是有效的 numpy array，Tesseract 才能處理
    text = pytesseract.image_to_string(img, config='--psm 7')
    print(f"辨識結果: {text}")