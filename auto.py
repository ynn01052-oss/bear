import os
import subprocess
import time
import csv
from datetime import datetime
import cv2
import numpy as np
import sys

ADB_DEVICE = "127.0.0.1:5555"   # 改成 BlueStacks 設定 > 進階 裡顯示的連接埠

START_DELAY = 3          # 執行後等幾秒再開始
ENTER_DELAY = 2          # 點 PLAY / 再試一次 後進入關卡需要的秒數
JUMP_SECONDS = 70        # 每次跳幾秒（每秒點一次）
TOTAL_RUNS = 15           # 總共跑幾次，最後一次按「終止」
JUMP_POS = (205, 908)    # 跳鍵座標（1920x1080）
THRESHOLD = 0.8          # 模板比對門檻
RESULT_DELAY = 5         # 按終止後，等幾秒再按結果畫面的確定
POPUP_DELAY = 5          # 按確定後，等幾秒再檢查彈窗
OPEN_DELAY = 3 
MAX_OPEN = 20            # 最多開幾個瓶蓋小熊（保險上限）
CAP_BACK_DELAY = 3       # 按確定後，等幾秒回到瓶蓋列表
CARD_HALF_WIDTH = 190    # 一張瓶蓋卡約 390 px 寬，半寬用來排除保留卡的「打開」
DESTROY_MODE = "skip"     # "ask"＝開始時詢問；也可直接寫死："skip" 不破壞 / "yes" 破壞 / "test" 測試
CLOSE_X = (1860, 52)     # 獎勵頁／自選畫面右上角的 X（兩個畫面位置相同）
CYCLE_DELAY = 5          # 一輪收尾完後，等幾秒再按 PLAY 開始下一輪
TOTAL_CYCLES = 30         # 0 = 不停重複（Ctrl+C 停止）；填數字 = 只重複那麼多輪

# 自動尋找 BlueStacks 內建的 adb
CANDIDATES = [
    r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
    r"C:\Program Files\BlueStacks_nxt_cn\HD-Adb.exe",
    r"C:\Program Files\BlueStacks\HD-Adb.exe",
    r"C:\Program Files (x86)\BlueStacks_nxt\HD-Adb.exe",
]
ADB_PATH = next((p for p in CANDIDATES if os.path.exists(p)), None)
if ADB_PATH is None:
    raise SystemExit("找不到 HD-Adb.exe，請到 BlueStacks 安裝資料夾找，然後手動填入 ADB_PATH")

def adb(*args):
    r = subprocess.run([ADB_PATH, "-s", ADB_DEVICE, *args], capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"adb 失敗：{r.stderr.decode(errors='ignore').strip()}")
    return r.stdout

def screencap():
    data = adb("exec-out", "screencap", "-p")
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

def find_template(screen, template_path):
    tpl = cv2.imread(template_path)
    if tpl is None:
        raise SystemExit(f"讀不到模板圖：{template_path}")
    h, w = tpl.shape[:2]
    res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    return score, (loc[0] + w // 2, loc[1] + h // 2)

def tap(x, y):
    adb("shell", "input", "tap", str(x), str(y))

def wait_for(template, threshold=THRESHOLD, timeout=10, interval=0.3):
    """等模板出現，回傳 (相似度, 座標)；超時座標為 None"""
    start = time.time()
    while True:
        score, pos = find_template(screencap(), template)
        if score >= threshold:
            return score, pos
        if time.time() - start >= timeout:
            return score, None
        time.sleep(interval)

def click_template(template, timeout=10):
    """等模板出現並點擊；找不到就停止程式，避免亂點"""
    score, pos = wait_for(template, timeout=timeout)
    print(f"  {template} 相似度：{score:.3f}")
    if pos is None:
        raise SystemExit(f"找不到 {template}，已停止")
    tap(*pos)

def click_if_present(template, timeout=3):
    """有出現才點，沒出現就略過；回傳有沒有點"""
    score, pos = wait_for(template, timeout=timeout)
    if pos is None:
        print(f"  {template} 沒出現（最高相似度 {score:.3f}），略過")
        return False
    print(f"  {template} 相似度：{score:.3f}，已點擊")
    tap(*pos)
    return True
def find_all(screen, template_path, threshold=THRESHOLD):
    """回傳畫面上所有符合的中心座標（由像似度高到低，去除重疊）"""
    tpl = cv2.imread(template_path)
    if tpl is None:
        raise SystemExit(f"讀不到模板圖：{template_path}")
    h, w = tpl.shape[:2]
    res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(res >= threshold)
    pts = []
    for y, x in sorted(zip(ys, xs), key=lambda p: -res[p[0], p[1]]):
        c = (int(x) + w // 2, int(y) + h // 2)
        if all(abs(c[0] - p[0]) > w // 2 or abs(c[1] - p[1]) > h // 2 for p in pts):
            pts.append(c)
    return pts
def wait_for_any(templates, threshold=THRESHOLD, timeout=20, interval=0.3):
    """等任一模板出現，回傳 (模板名, 相似度, 座標)；超時回傳 (None, 0, None)"""
    start = time.time()
    while True:
        screen = screencap()
        for t in templates:
            score, pos = find_template(screen, t)
            if score >= threshold:
                return t, score, pos
        if time.time() - start >= timeout:
            return None, 0.0, None
        time.sleep(interval)

def click_open_with_wait(timeout=3):
    """按一個「打開」，但跳過所有保留卡那一欄的按鈕；沒有可按的就回傳 False"""
    start = time.time()
    while True:
        screen = screencap()
        opens = find_all(screen, "open_btn.png")
        keeps = find_all(screen, "keep_cap.png")
        opens = [p for p in opens
                 if all(abs(p[0] - k[0]) > CARD_HALF_WIDTH for k in keeps)]
        if opens:
            print(f"  open_btn.png 已點擊 {opens[0]}（保留卡 {len(keeps)} 張）")
            tap(*opens[0])
            return True
        if time.time() - start >= timeout:
            return False
        time.sleep(0.3)
def choose_destroy_mode():
    """開始時選擇：這次掛機要不要破壞限時瓶蓋小熊"""
    global DESTROY_MODE

    # 命令列優先：python auto.py --destroy / --no-destroy
    if "--destroy" in sys.argv:
        DESTROY_MODE = "yes"
    elif "--no-destroy" in sys.argv:
        DESTROY_MODE = "skip"

    if DESTROY_MODE == "ask":
        print("這次掛機要破壞限時瓶蓋小熊嗎？")
        print("  1 = 不破壞（保留，直接略過）")
        print("  2 = 破壞（每張要花鑽石，費用依卡片而定）")
        print("  3 = 測試（選好卡片但不按破壞，然後停止）")
        while True:
            ans = input("請輸入 1 / 2 / 3：").strip()
            if ans in ("1", "2", "3"):
                DESTROY_MODE = {"1": "skip", "2": "yes", "3": "test"}[ans]
                break
            print("請輸入 1、2 或 3")

    label = {"skip": "不破壞", "yes": "破壞", "test": "測試（不按破壞）"}[DESTROY_MODE]
    print(f"本次設定：{label}")

def destroy_timed_cap():
    
    """破壞限時的瓶蓋小熊（藍色卡片：倒數計時＋詳情）"""
    if DESTROY_MODE == "skip":
        print("  本次設定為不破壞，略過")
        return
    
    score, pos = find_template(screencap(), "timed_cap.png")
    print(f"  timed_cap.png 相似度：{score:.3f}")
    if score < THRESHOLD:
        print("  沒有要破壞的限時瓶蓋小熊，略過")
        return
    card_x = pos[0]                      # 該卡片的水平中心

    tap(601, 957)                        # 左下角「破壞瓶蓋小熊」的選擇
    time.sleep(1.5)                      # 進入「請選擇瓶蓋小熊」模式
    tap(card_x, 450)                     # 點要破壞的卡片

    # 確認卡片左上角出現綠色勾勾（已選好）
    score, pos = wait_for("selected_check.png", timeout=5)
    print(f"  selected_check.png 相似度：{score:.3f}")
    if pos is None:
        cv2.imwrite("stuck.png", screencap())
        raise SystemExit("沒進入『已選好卡片』狀態，已存下 stuck.png")

    if DESTROY_MODE == "test":
        raise SystemExit("測試模式：卡片已選好，沒有按破壞（請手動按 X 取消）")

    tap(601, 957)                        # 左下角綠色「破壞」（費用依卡片而定）

    # Loading → 「正在破壞瓶蓋小熊」動畫 → 約 5 秒後出現確定
    score, pos = wait_for("ok_cap.png", timeout=20)
    print(f"  ok_cap.png 相似度：{score:.3f}")
    if pos is None:
        cv2.imwrite("stuck.png", screencap())
        raise SystemExit("等不到破壞完成的確定，已存下 stuck.png")
    tap(*pos)
    time.sleep(CAP_BACK_DELAY)           # 等回到列表
    print("  已破壞限時瓶蓋小熊")

def jump_for(seconds):
    """每秒點一次跳鍵，用起始時間排程避免誤差累積"""
    t0 = time.time()
    for i in range(seconds):
        tap(*JUMP_POS)
        print(f"  跳 {i + 1}/{seconds}", end="\r")
        wait = t0 + i + 1 - time.time()
        if wait > 0:
            time.sleep(wait)
    print()

def finish_screens():
    """終止之後的收尾：結果畫面 → 獎勵彈窗（可能有）→ 驚喜獎勵（可能有）"""
    time.sleep(RESULT_DELAY)
    click_template("ok_result.png")                  # 遊戲結果：確定（一定有）

    time.sleep(POPUP_DELAY)
    if click_if_present("ok_reward.png", timeout=2): # 黃金寶箱獎勵：有就按確定
        time.sleep(3)                                # 等切回主畫面
    click_if_present("close_x.png", timeout=4)       # 驚喜獎勵：有就按 X
def open_caps():
    """從主畫面進入獎勵 → 瓶蓋小熊 → 能開的開掉 → 破壞限時卡 → 回主畫面"""
    time.sleep(2)
    click_template("rewards_btn.png")                # 主畫面左下角：獎勵
    time.sleep(2)
    click_if_present("bear_tab.png", timeout=3)      # 左側：瓶蓋小熊
    time.sleep(1)

    opened = 0
    while opened < MAX_OPEN and click_open_with_wait(timeout=3):
        opened += 1
        print(f"  開第 {opened} 個，等開啟動畫...")

        # 一般瓶蓋 → 動畫後出現確定；5 星自選瓶蓋 → 「請選擇獎勵」畫面
        name, score, pos = wait_for_any(["ok_cap.png", "pick_title.png"], timeout=20)
        print(f"  {name} 相似度：{score:.3f}")
        if name == "ok_cap.png":
            tap(*pos)
            time.sleep(CAP_BACK_DELAY)               # 等回到列表
        elif name == "pick_title.png":
            print("  遇到沒被排除的自選瓶蓋，不選擇，按 X 關閉並停止開瓶蓋")
            tap(*CLOSE_X)
            time.sleep(2)
            break
        else:
            cv2.imwrite("stuck.png", screencap())
            raise SystemExit("等不到確定，也不是自選畫面，已存下 stuck.png")

    print(f"  共開了 {opened} 個瓶蓋小熊")
    destroy_timed_cap()                              # 限時的藍色卡：破壞

    tap(*CLOSE_X)                                    # 關閉獎勵頁，回主畫面
    score, pos = wait_for("rewards_btn.png", timeout=8)
    print(f"  rewards_btn.png 相似度：{score:.3f}，"
          + ("已回到主畫面" if pos else "沒偵測到主畫面，請檢查"))

def run_cycle(cycle):
    """一輪完整流程：點 PLAY → 跑 TOTAL_RUNS 次 → 終止 → 收尾 → 開瓶蓋 → 回主畫面"""
    click_template("play.png", timeout=10)
    print("已點擊 PLAY：", datetime.now().strftime("%H:%M:%S"))

    for run in range(1, TOTAL_RUNS + 1):
        print(f"=== 第 {cycle} 輪｜第 {run}/{TOTAL_RUNS} 次 ===")

        time.sleep(ENTER_DELAY)
        enter_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("  進入關卡時間：", enter_time)

        jump_for(JUMP_SECONDS)

        click_template("pause.png", timeout=0)      # 按暫停
        if run < TOTAL_RUNS:
            click_template("retry.png")             # 再試一次
            click_template("yes.png")               # 確認框按「是」
        else:
            click_template("stop.png")              # 最後一次：終止
            print("已按終止，開始收尾")
            finish_screens()
            open_caps()

        with open("log.csv", "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow([enter_time, run, cycle])

if __name__ == "__main__":
    # 開始前倒數（只有最開頭一次）
    choose_destroy_mode()
    for i in range(START_DELAY, 0, -1):
        print(f"{i} 秒後開始...")
        time.sleep(1)

    subprocess.run([ADB_PATH, "connect", ADB_DEVICE], capture_output=True)

    cycle = 0
    while TOTAL_CYCLES == 0 or cycle < TOTAL_CYCLES:
        cycle += 1
        print(f"########## 第 {cycle} 輪開始 ##########")
        run_cycle(cycle)
        print(f"第 {cycle} 輪完成")

        if TOTAL_CYCLES == 0 or cycle < TOTAL_CYCLES:
            print(f"等 {CYCLE_DELAY} 秒後開始下一輪...")
            time.sleep(CYCLE_DELAY)

    print("全部完成")