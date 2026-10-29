import sys
import subprocess
import cv2
from auto import screencap, find_template, ADB_PATH, ADB_DEVICE

name = sys.argv[1] if len(sys.argv) > 1 else "rewards_btn.png"
subprocess.run([ADB_PATH, "connect", ADB_DEVICE], capture_output=True)

screen = screencap()
tpl = cv2.imread(name)
h, w = tpl.shape[:2]
score, (cx, cy) = find_template(screen, name)
print(f"{name} 相似度 {score:.3f}，最像的位置中心：({cx}, {cy})，模板大小 {w}x{h}")

cv2.rectangle(screen, (cx - w // 2, cy - h // 2), (cx + w // 2, cy + h // 2), (0, 0, 255), 4)
cv2.imwrite("debug_match.png", screen)
print("已輸出 debug_match.png（紅框是比對到的位置）")