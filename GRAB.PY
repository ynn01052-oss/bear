import subprocess, cv2, numpy as np
from auto import screencap   # 沿用 auto.py 的截圖函式

img = screencap()
cv2.imwrite("level.png", img)

# 暫停鈕的估計範圍 [y1:y2, x1:x2]，以 1920x1080 換算
crop = img[25:110, 1805:1895]
cv2.imwrite("pause.png", crop)
print("已輸出 level.png 和 pause.png")