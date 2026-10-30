import os
import sys
import subprocess
import time
import csv
from datetime import datetime
import cv2
import numpy as np

# ============================== 設定 ==============================
ADB_DEVICE = "127.0.0.1:5555"   # 改成 BlueStacks 設定 > 進階 裡顯示的連接埠

START_DELAY = 3          # 執行後等幾秒再開始
ENTER_DELAY = 2          # 點 PLAY / 再試一次 後進入關卡需要的秒數
JUMP_SECONDS = 70        # 每次跳幾秒（每秒點一次）
TOTAL_RUNS = 20          # 一輪最多跑幾次（次數有限制的日子會在次數用完時提早結束）
JUMP_POS = (205, 908)    # 跳鍵座標（1920x1080）
THRESHOLD = 0.8          # 模板比對門檻

RESULT_DELAY = 9         # 按終止後，等幾秒再開始找結果畫面的確定
LOADING_TIMEOUT = 90     # 畫面出現「Loading...」時，最多等幾秒（遊戲偶爾載入很慢）
POPUP_DELAY = 5          # 按確定後，等幾秒再檢查彈窗
MAX_OPEN = 20            # 最多開幾個瓶蓋小熊（保險上限）
CONFIRM2_POS = (959, 945) # 第二段「獎勵結果」畫面的確定（1920x1080；按鈕比第一段大，位置固定）
CARD_HALF_WIDTH = 190    # 一張瓶蓋卡約 390 px 寬，半寬用來排除保留卡的「打開」
CLOSE_X = (1860, 52)     # 獎勵頁／自選畫面右上角的 X（兩個畫面位置相同）
SWIPE_FROM = (1700, 450) # 瓶蓋列表上「按住往左拖動」的起點（1920x1080）
SWIPE_TO = (920, 450)    # 拖動終點（約拖過兩張卡）
SWIPE_MS = 700           # 拖動花的時間（毫秒），太快會滑過頭
MAX_SWIPES = 8           # 一次開蓋流程最多拖動幾次（保險上限）
MOVE_DIFF = 20           # 拖動前後畫面差異超過這個值，才算列表真的移動了

CYCLE_DELAY = 5          # 一輪（含填充、開蓋）結束後，等幾秒再按 PLAY 開始下一輪
TOTAL_CYCLES = 0         # 0 = 不停重複（Ctrl+C 停止）；填數字 = 只重複那麼多輪

REFILL_BTN = (1294, 768) # 「餅乾體力耗盡」彈窗裡綠色的鑽石恢復按鈕（1920x1080）
MAX_REFILLS = 2888       # 這次掛機最多用鑽石填充幾次（每次花鑽，費用以遊戲顯示為準）

DESTROY_MODE = "skip"    # "ask"＝開始時詢問；或寫死："skip" 不破壞 / "yes" 破壞 / "test" 測試
REFILL_MODE = "yes"      # "ask"＝開始時詢問；或寫死："skip" 不填充 / "yes" 填充
refills_done = 0         # 目前已填充幾次（程式自己計數，不用改）

# 自動尋找 BlueStacks 內建的 adb（也可用環境變數 ADB_PATH 指定）
CANDIDATES = [
    r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
    r"C:\Program Files\BlueStacks_nxt_cn\HD-Adb.exe",
    r"C:\Program Files\BlueStacks\HD-Adb.exe",
    r"C:\Program Files (x86)\BlueStacks_nxt\HD-Adb.exe",
]
ADB_PATH = os.environ.get("ADB_PATH") or next((p for p in CANDIDATES if os.path.exists(p)), None)
if ADB_PATH is None:
    raise SystemExit("找不到 HD-Adb.exe，請到 BlueStacks 安裝資料夾找，然後手動填入 ADB_PATH")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # 這支程式所在的資料夾（模板圖要放這裡）

# 程式會用到的模板圖（缺任何一張，開始時就會一次列出來）
REQUIRED_TEMPLATES = [
    "play.png", "pause.png", "stop.png", "retry.png", "yes.png",
    "ok_result.png", "ok_reward.png", "close_x.png",
    "rewards_btn.png", "bear_tab.png", "open_btn.png", "keep_cap.png",
    "ok_cap.png", "pick_title.png", "exhausted_title.png",
]
DESTROY_TEMPLATES = ["timed_cap.png", "selected_check.png"]   # 只有「破壞／測試」模式才需要


# ============================== 基本函式 ==============================
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


def find_all(screen, template_path, threshold=THRESHOLD):
    """回傳畫面上所有符合的中心座標（由相似度高到低，去除重疊）"""
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


def wait_loading_done(timeout=None, interval=0.5):
    """畫面上有「Loading...」就等它消失；沒在載入（或沒有 loading.png）就立刻返回"""
    if not os.path.exists("loading.png"):
        return
    timeout = LOADING_TIMEOUT if timeout is None else timeout
    start = time.time()
    seen = False
    while time.time() - start < timeout:
        score, _ = find_template(screencap(), "loading.png")
        if score < 0.7:                              # 看不到 Loading 了
            if seen:
                print(f"  載入完成（等了 {time.time() - start:.0f} 秒）")
            return
        seen = True
        time.sleep(interval)
    print(f"  Loading 超過 {timeout} 秒還沒結束，繼續往下做")


def click_template(template, timeout=10):
    """等模板出現並點擊；找不到就停止程式，避免亂點"""
    score, pos = wait_for(template, timeout=timeout)
    print(f"  {template} 相似度：{score:.3f}")
    if pos is None:
        cv2.imwrite("stuck.png", screencap())
        raise SystemExit(f"找不到 {template}，已存下 stuck.png 並停止")
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


# ============================== 開始前的選擇 ==============================
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
    print(f"破壞限時瓶蓋小熊：{label}")


def choose_refill_mode():
    """開始時選擇：餅乾次數用完時，要不要用鑽石填充"""
    global REFILL_MODE

    # 命令列優先：python auto.py --refill / --no-refill
    if "--refill" in sys.argv:
        REFILL_MODE = "yes"
    elif "--no-refill" in sys.argv:
        REFILL_MODE = "skip"

    if REFILL_MODE == "ask":
        print("餅乾次數用完時要怎麼處理？")
        print("  1 = 不填充（次數用完就收尾、開完蓋後結束）")
        print(f"  2 = 用鑽石填充（每次花鑽，這次最多填充 {MAX_REFILLS} 次）")
        while True:
            ans = input("請輸入 1 / 2：").strip()
            if ans in ("1", "2"):
                REFILL_MODE = {"1": "skip", "2": "yes"}[ans]
                break
            print("請輸入 1 或 2")

    label = {"skip": "不填充", "yes": f"填充（最多 {MAX_REFILLS} 次）"}[REFILL_MODE]
    print(f"次數用完時：{label}")


# ============================== 收尾、填充、開蓋 ==============================
def finish_screens():
    """終止之後的收尾：結果畫面 → 獎勵彈窗（可能有）→ 驚喜獎勵（可能有）"""
    time.sleep(RESULT_DELAY)
    wait_loading_done()                              # 結果畫面載入可能很慢，先等它載完
    click_template("ok_result.png", timeout=20)      # 遊戲結果：確定（一定有）

    time.sleep(POPUP_DELAY)
    if click_if_present("ok_reward.png", timeout=2): # 黃金寶箱獎勵：有就按確定
        time.sleep(3)                                # 等切回主畫面
    click_if_present("close_x.png", timeout=4)       # 驚喜獎勵：有就按 X


def refill_stamina(popup_open=False):
    """用鑽石恢復次數。成功回傳 True；設定不填充或已達上限回傳 False。
    popup_open=True 表示「餅乾體力耗盡」彈窗已經開著（不用再按 PLAY）"""
    global refills_done
    if REFILL_MODE != "yes" or refills_done >= MAX_REFILLS:
        return False

    if not popup_open:
        click_template("play.png", timeout=10)       # 次數是 0 時按 PLAY 會跳出彈窗
        score, pos = wait_for("exhausted_title.png", timeout=8)
        print(f"  exhausted_title.png 相似度：{score:.3f}")
        if pos is None:
            cv2.imwrite("stuck.png", screencap())
            raise SystemExit("沒看到『餅乾體力耗盡』彈窗，已存下 stuck.png")

    tap(*REFILL_BTN)                                 # 綠色鑽石按鈕：立即恢復 10 次
    time.sleep(2)

    score, _ = find_template(screencap(), "exhausted_title.png")
    if score >= THRESHOLD:
        cv2.imwrite("stuck.png", screencap())
        raise SystemExit("按了恢復但彈窗還在（可能鑽石不足），已存下 stuck.png")

    refills_done += 1
    print(f"  已用鑽石恢復次數（第 {refills_done}/{MAX_REFILLS} 次）")
    return True


def card_view(screen):
    """取瓶蓋卡片區域（縮小成灰階），用來比較拖動前後有沒有移動"""
    g = cv2.cvtColor(screen[200:1030, 780:1900], cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (0, 0), fx=0.25, fy=0.25).astype(int)


def swipe_left():
    """在瓶蓋列表上按住往左拖動，露出右邊的卡片；回傳列表有沒有真的移動（沒移動＝到底了）"""
    before = card_view(screencap())
    adb("shell", "input", "swipe",
        str(SWIPE_FROM[0]), str(SWIPE_FROM[1]),
        str(SWIPE_TO[0]), str(SWIPE_TO[1]), str(SWIPE_MS))
    time.sleep(1.5)                                  # 等滑動停下來
    after = card_view(screencap())
    diff = float(np.mean(np.abs(before - after)))
    moved = diff > MOVE_DIFF
    print(f"  往左拖動：畫面差異 {diff:.1f} → " + ("列表有移動" if moved else "沒移動，已到最右邊"))
    return moved


def finish_cap_result():
    """按掉第一段確定之後，一直處理到回到瓶蓋列表為止。
    有些瓶蓋是 打開 → 確定 → 確定：第二段是「獎勵結果」畫面，確定的外觀和第一段不同"""
    time.sleep(1)                                    # 等第一段確定的轉場
    wait_loading_done()
    for _ in range(3):
        names = ["bear_tab.png"]                     # 看得到左側分頁＝回到列表了
        if os.path.exists("cap_result_title.png"):   # 第二段「獎勵結果」標題（有做才會偵測）
            names.append("cap_result_title.png")
        name, score, _pos = wait_for_any(names, timeout=8)
        if name == "bear_tab.png":
            time.sleep(1)                            # 等金幣飛入等動畫結束
            return
        if name == "cap_result_title.png":
            print(f"  第二段「獎勵結果」（相似度 {score:.3f}）→ 按確定")
            time.sleep(1.5)                          # 等確定出現
            tap(*CONFIRM2_POS)
            time.sleep(1)
            continue
        break
    cv2.imwrite("stuck.png", screencap())
    raise SystemExit("開蓋後沒有回到瓶蓋列表，可能出現了新的畫面，已存下 stuck.png")


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


def destroy_timed_cap():
    """破壞畫面上的限時瓶蓋小熊（藍色卡片：倒數計時＋詳情）。有破壞回傳 True，沒有回傳 False"""
    if DESTROY_MODE == "skip":
        print("  本次設定為不破壞，略過")
        return False

    score, pos = find_template(screencap(), "timed_cap.png")
    print(f"  timed_cap.png 相似度：{score:.3f}")
    if score < THRESHOLD:
        print("  這個畫面上沒有要破壞的限時瓶蓋小熊")
        return False
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
    finish_cap_result()                  # 處理確定，直到回到列表
    print("  已破壞限時瓶蓋小熊")
    return True


def open_caps():
    """從主畫面進入獎勵 → 瓶蓋小熊 → 能開的開掉、限時卡依設定破壞，
    這一頁處理完就往左拖動看右邊 → 拖到底 → 回主畫面"""
    time.sleep(2)
    click_template("rewards_btn.png")                # 主畫面左下角：獎勵
    time.sleep(2)
    wait_loading_done()
    click_if_present("bear_tab.png", timeout=3)      # 左側：瓶蓋小熊
    time.sleep(1)

    opened = 0
    swipes = 0
    steps = 0
    while opened < MAX_OPEN and steps < 60:
        steps += 1

        # 1. 這個畫面上能開的先開（保留卡會被排除）
        if click_open_with_wait(timeout=3):
            opened += 1
            print(f"  開第 {opened} 個，等開啟動畫...")

            # 一般瓶蓋 → 動畫後出現確定；5 星自選瓶蓋 → 「請選擇獎勵」畫面
            name, score, pos = wait_for_any(["ok_cap.png", "pick_title.png"], timeout=20)
            print(f"  {name} 相似度：{score:.3f}")
            if name == "ok_cap.png":
                tap(*pos)
                finish_cap_result()                  # 處理一段或兩段確定，直到回到列表
                continue
            elif name == "pick_title.png":
                print("  遇到沒被排除的自選瓶蓋，不選擇，按 X 關閉並停止開瓶蓋")
                tap(*CLOSE_X)
                time.sleep(2)
                break
            else:
                cv2.imwrite("stuck.png", screencap())
                raise SystemExit("等不到確定，也不是自選畫面，已存下 stuck.png")

        # 2. 這個畫面上有限時卡的話，依設定破壞（略過模式會直接回傳 False）
        if destroy_timed_cap():
            continue

        # 3. 這個畫面處理完了 → 往左拖動，看右邊還有沒有卡片
        if swipes >= MAX_SWIPES:
            print("  已達拖動次數上限，停止")
            break
        swipes += 1
        if not swipe_left():
            break

    print(f"  共開了 {opened} 個瓶蓋小熊、拖動 {swipes} 次")

    tap(*CLOSE_X)                                    # 關閉獎勵頁，回主畫面
    score, pos = wait_for("rewards_btn.png", timeout=8)
    print(f"  rewards_btn.png 相似度：{score:.3f}，"
          + ("已回到主畫面" if pos else "沒偵測到主畫面，請檢查"))


# ============================== 一輪、主程式 ==============================
def log_run(enter_time, run, cycle):
    with open("log.csv", "a", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow([enter_time, run, cycle])


def run_cycle(cycle):
    """一輪：點 PLAY → 一直跑到 TOTAL_RUNS 次或次數用完 → 終止 → 收尾。
    回傳 True＝這輪是因為『次數用完』而結束"""
    click_template("play.png", timeout=10)
    print("已點擊 PLAY：", datetime.now().strftime("%H:%M:%S"))

    # 如果一開始次數就是 0，PLAY 之後會跳出「餅乾體力耗盡」
    time.sleep(1)
    score, _ = find_template(screencap(), "exhausted_title.png")
    if score >= THRESHOLD:
        print("  開局次數就是 0")
        if not refill_stamina(popup_open=True):
            raise SystemExit("次數用完，且設定不填充（或已達上限），結束")
        click_template("play.png", timeout=10)       # 恢復後重新按 PLAY

    exhausted = False
    for run in range(1, TOTAL_RUNS + 1):
        print(f"=== 第 {cycle} 輪｜第 {run}/{TOTAL_RUNS} 次 ===")

        time.sleep(ENTER_DELAY)
        wait_loading_done()                          # 還在載入就等載完，才開始計時跳
        enter_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("  進入關卡時間：", enter_time)

        jump_for(JUMP_SECONDS)

        click_template("pause.png", timeout=0)       # 按暫停

        # 等暫停選單出現（終止一定有）
        score, pos = wait_for("stop.png", timeout=10)
        if pos is None:
            cv2.imwrite("stuck.png", screencap())
            raise SystemExit("暫停後等不到選單，已存下 stuck.png")

        # 再看有沒有「再試一次」：次數用完時選單只剩 繼續／終止
        score, retry_pos = wait_for("retry.png", timeout=2.5)
        log_run(enter_time, run, cycle)

        if retry_pos is not None and run < TOTAL_RUNS:
            tap(*retry_pos)                          # 再試一次
            click_template("yes.png")                # 確認框按「是」
        else:
            exhausted = retry_pos is None
            if exhausted:
                print("  暫停選單沒有「再試一次」→ 次數已用完")
            click_template("stop.png")               # 終止
            print("已按終止，開始收尾")
            finish_screens()
            break

    return exhausted


def startup():
    """工作目錄切到程式所在資料夾，並檢查模板圖是否齊全"""
    os.chdir(BASE_DIR)
    needed = list(REQUIRED_TEMPLATES)
    if DESTROY_MODE != "skip":
        needed += DESTROY_TEMPLATES
    missing = [t for t in needed if not os.path.exists(t)]
    if missing:
        print(f"模板圖放在這個資料夾：{BASE_DIR}")
        print("缺少這些模板圖：")
        for t in missing:
            print(f"  - {t}")
        raise SystemExit("請先補齊模板圖再執行")


def main():
    # 先決定破壞模式（模板需求依它而定），再檢查檔案，最後問填充
    choose_destroy_mode()
    startup()
    choose_refill_mode()

    # 開始前倒數（只有最開頭一次）
    for i in range(START_DELAY, 0, -1):
        print(f"{i} 秒後開始...")
        time.sleep(1)

    subprocess.run([ADB_PATH, "connect", ADB_DEVICE], capture_output=True)

    cycle = 0
    while TOTAL_CYCLES == 0 or cycle < TOTAL_CYCLES:
        cycle += 1
        print(f"########## 第 {cycle} 輪開始 ##########")
        exhausted = run_cycle(cycle)

        can_continue = True
        if exhausted:
            print("餅乾次數已用完")
            if not refill_stamina():                 # 先填充，再去開蓋
                can_continue = False

        open_caps()

        if not can_continue:
            print("次數用完且未填充（設定不填充，或已達填充上限），結束")
            break

        print(f"第 {cycle} 輪完成")
        if TOTAL_CYCLES == 0 or cycle < TOTAL_CYCLES:
            print(f"等 {CYCLE_DELAY} 秒後開始下一輪...")
            time.sleep(CYCLE_DELAY)

    print("全部完成")


if __name__ == "__main__":
    main()
