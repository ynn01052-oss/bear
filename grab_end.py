"""
裁模板圖用。座標是 1920x1080 的 [y1:y2, x1:x2]。

用法：
  python grab_end.py 名稱              ← 讓遊戲停在對應畫面，會即時用 ADB 截圖後裁出 名稱.png
  python grab_end.py 名稱 stuck.png    ← 從已經存好的截圖（例如程式停下來存的 stuck.png）裁出 名稱.png

裁完請打開 名稱.png 確認內容正確。
"""
import os
import sys
import subprocess
import cv2

# 名稱: (y1, y2, x1, x2)
CROPS = {
    # --- 一輪的主流程 ---
    "play":            (880, 1030, 1340, 1860),  # 主畫面的 PLAY
    "pause":           (25, 110, 1805, 1895),    # 關卡裡的暫停鈕
    "retry":           (715, 795, 760, 1160),    # 暫停選單：再試一次
    "stop":            (550, 635, 760, 1160),    # 暫停選單：終止
    "yes":             (650, 750, 990, 1370),    # 再試一次的確認框：是
    # --- 收尾 ---
    "ok_result":       (925, 1020, 780, 1140),   # 遊戲結果的確定
    "ok_reward":       (850, 1000, 745, 1175),   # 黃金寶箱獎勵的確定
    "close_x":         (175, 258, 1432, 1518),   # 驚喜獎勵的 X
    # --- 次數用完 ---
    "exhausted_title": (626, 705, 858, 1069),    # 「餅乾體力耗盡」彈窗的文字
    # --- 開瓶蓋 ---
    "rewards_btn":     (960, 1015, 122, 228),    # 主畫面左下角「獎勵」兩個字
    "bear_tab":        (740, 785, 50, 180),      # 獎勵頁左側「瓶蓋小熊」文字
    "open_btn":        (925, 985, 830, 1080),    # 「打開」按鈕
    "ok_cap":          (880, 1005, 760, 1160),   # 開瓶蓋／破壞後第一段的確定
    "keep_cap":        (697, 770, 895, 1010),    # 保留卡上的「超級稀有」標籤
    "pick_title":      (45, 105, 745, 1040),     # 「請選擇獎勵」標題文字
    "cap_result_title": (95, 160, 836, 1078),    # 第二段「獎勵結果」標題文字
    # --- 破壞限時卡 ---
    "timed_cap":       (960, 1005, 1280, 1390),  # 限時卡下方的「詳情」
    "selected_check":  (210, 282, 1556, 1644),   # 破壞模式下，選中卡片的綠色勾勾
}

if len(sys.argv) < 2 or sys.argv[1] not in CROPS:
    print("用法：python grab_end.py 名稱 [截圖檔]")
    print("可用的名稱：" + "、".join(CROPS))
    raise SystemExit(1)

name = sys.argv[1]

if len(sys.argv) >= 3:                          # 從截圖檔裁
    img = cv2.imread(sys.argv[2])
    if img is None:
        raise SystemExit(f"讀不到截圖檔：{sys.argv[2]}")
else:                                           # 即時用 ADB 截圖
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    from auto import screencap, ADB_PATH, ADB_DEVICE
    subprocess.run([ADB_PATH, "connect", ADB_DEVICE], capture_output=True)
    img = screencap()
    cv2.imwrite(f"{name}_full.png", img)

h, w = img.shape[:2]
if (w, h) != (1920, 1080):
    print(f"注意：這張截圖是 {w}x{h}，不是 1920x1080，座標會對不上。請用 ADB 截的圖。")

y1, y2, x1, x2 = CROPS[name]
cv2.imwrite(f"{name}.png", img[y1:y2, x1:x2])
print(f"已輸出 {name}.png")
