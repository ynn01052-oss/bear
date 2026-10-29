import cv2

img = cv2.imread("screen.png")

# 估計的 PLAY 按鈕範圍：[y1:y2, x1:x2]
crop = img[880:1030, 1340:1860]
cv2.imwrite("play.png", crop)
print("已輸出 play.png，尺寸：", crop.shape[1], "x", crop.shape[0])