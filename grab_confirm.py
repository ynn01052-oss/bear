import subprocess
import cv2
from auto import screencap, ADB_PATH, ADB_DEVICE

subprocess.run([ADB_PATH, "connect", ADB_DEVICE], capture_output=True)

img = screencap()
cv2.imwrite("confirm.png", img)
cv2.imwrite("yes.png", img[650:750, 990:1370])   # 「是」按鈕
print("已輸出 confirm.png、yes.png")