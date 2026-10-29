import cv2
from auto import screencap   # 沿用 auto.py 的截圖函式

img = screencap()
cv2.imwrite("pause_menu.png", img)
cv2.imwrite("retry.png", img[715:795, 760:1160])   # 再試一次
cv2.imwrite("stop.png",  img[550:635, 760:1160])   # 終止
print("已輸出 pause_menu.png、retry.png、stop.png")
