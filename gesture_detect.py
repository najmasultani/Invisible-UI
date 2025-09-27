# gesture_detect.py
import time
from collections import deque
from math import hypot
import platform
import cv2
import mediapipe as mp

# OPTIONAL: enable real keypress for PowerPoint / Google Slides start/stop
try:
    import pyautogui
except Exception:
    pyautogui = None

IS_MAC = platform.system() == "Darwin"

W, H = 640, 360

mp_hands = mp.solutions.hands
mp_draw  = mp.solutions.drawing_utils
mp_style = mp.solutions.drawing_styles

# ---- timing ----
HOLD_MS = 250
COOL_MS = 800
_last_name = None
_start_t = 0.0
_last_fire_t = 0.0

SWIPE_WINDOW_MS = 160
SWIPE_MIN_DX = 0.14
SWIPE_COOL_MS = 500
_last_swipe_fire = 0.0

paused = False
hist = deque(maxlen=30)  # (t, x, y) fingertip for swipes

# ---- helpers ----
def _d(a, b): return hypot(a.x - b.x, a.y - b.y)
def _hand_size(lm): return _d(lm[0], lm[9]) + 1e-6

def _extended(lm, tip_id, pip_id, thr=0.35):
    wrist = lm[0]
    return (_d(lm[tip_id], wrist) - _d(lm[pip_id], wrist)) > (thr * _hand_size(lm))

def stable_emit(name, now):
    global _last_name, _start_t, _last_fire_t
    if not name:
        _last_name, _start_t = None, 0.0
        return None
    if name != _last_name:
        _last_name, _start_t = name, now
        return None
    if (now - _start_t) >= HOLD_MS/1000.0 and (now - _last_fire_t) >= COOL_MS/1000.0:
        _last_fire_t = now
        return name
    return None

# ---- gesture classifiers ----
def is_fist(lm):
    # none of index/middle/ring/pinky extended
    return sum([_extended(lm,8,6), _extended(lm,12,10),
                _extended(lm,16,14), _extended(lm,20,18)]) == 0

def is_peace(lm):
    idx, mid = _extended(lm,8,6), _extended(lm,12,10)
    ring, pink = _extended(lm,16,14), _extended(lm,20,18)
    return idx and mid and not (ring or pink)

def is_three(lm):
    # index + middle + ring extended; pinky curled
    idx, mid, ring = _extended(lm,8,6), _extended(lm,12,10), _extended(lm,16,14)
    return idx and mid and ring and not _extended(lm,20,18)

def is_rock(lm):
    # 🤘 index + pinky extended, middle+ring curled
    idx  = _extended(lm,8,6)
    pink = _extended(lm,20,18)
    mid  = _extended(lm,12,10)
    ring = _extended(lm,16,14)
    return idx and pink and not (mid or ring)

def is_shaka(lm):
    # 🤙 thumb + pinky extended, others curled
    thumb = _extended(lm,4,2)
    pink  = _extended(lm,20,18)
    idx   = _extended(lm,8,6)
    mid   = _extended(lm,12,10)
    ring  = _extended(lm,16,14)
    return thumb and pink and not (idx or mid or ring)

def is_open(lm):
    # ✋ all fingers extended (ignore thumb robustness)
    return all(_extended(lm,t,p) for t,p in [(8,6),(12,10),(16,14),(20,18)])

def is_ok(lm):
    # 👌 index + thumb tips close (circle), middle/ring/pinky extended (for separation)
    thumb_tip, index_tip = lm[4], lm[8]
    close = _d(thumb_tip, index_tip) < 0.035
    mid_ext  = _extended(lm,12,10)
    ring_ext = _extended(lm,16,14)
    pink_ext = _extended(lm,20,18)
    return close and (mid_ext and ring_ext and pink_ext)

def classify(lm):
    # Order matters: quit first, then pause, then uniques
    if is_peace(lm): return "peace"     # quit
    if is_fist(lm):  return "fist"      # pause/resume
    if is_rock(lm):  return "rock"      # scroll up
    if is_shaka(lm): return "shaka"     # scroll down
    if is_ok(lm):    return "ok"        # start slideshow
    if is_open(lm):  return "open"      # stop slideshow
    if is_three(lm): return "three"     # L/R navigation via swipe
    return None

# ---- slides helpers (optional OS control) ----
def start_slideshow():
    # PowerPoint: F5 ; Google Slides: Cmd/Ctrl+Enter also works
    if not pyautogui:
        print("[ACTION] START SLIDESHOW (simulate)")
        return
    try:
        # try PowerPoint-style
        pyautogui.press("f5")
        print("[ACTION] Sent F5 (PowerPoint start).")
    except Exception:
        pass
    try:
        # try Google Slides shortcut
        if IS_MAC:
            pyautogui.keyDown("command"); pyautogui.press("enter"); pyautogui.keyUp("command")
        else:
            pyautogui.keyDown("ctrl"); pyautogui.press("enter"); pyautogui.keyUp("ctrl")
        print("[ACTION] Sent Present (Slides).")
    except Exception:
        pass

def stop_slideshow():
    if not pyautogui:
        print("[ACTION] STOP SLIDESHOW (simulate)")
        return
    try:
        pyautogui.press("esc")
        print("[ACTION] Sent Esc (exit slideshow).")
    except Exception:
        pass

# ---- main loop ----
def main():
    global paused, _last_swipe_fire

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam")

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        model_complexity=1,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6,
    )

    print("Gestures:")
    print("- Fist: toggle PAUSE/RESUME")
    print("- Peace ✌️: QUIT")
    print("- Rock 🤘: SCROLL UP")
    print("- Shaka 🤙: SCROLL DOWN")
    print("- Three (idx+mid+ring) + swipe L/R: NEXT/PREV SECTION")
    print("- OK sign 👌: START SLIDESHOW (F5 / Present)")
    print("- Open palm ✋: STOP SLIDESHOW (Esc)")
    print("Press 'q' to quit as well.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = hands.process(rgb)

        name = None
        idx_xy = None
        now = time.time()

        if res.multi_hand_landmarks:
            lm = res.multi_hand_landmarks[0].landmark
            name = classify(lm)
            idx_xy = (lm[8].x, lm[8].y)

            mp_draw.draw_landmarks(
                frame, res.multi_hand_landmarks[0],
                mp_hands.HAND_CONNECTIONS,
                mp_style.get_default_hand_landmarks_style(),
                mp_style.get_default_hand_connections_style()
            )

        # static gestures
        fired = stable_emit(name, now)
        if fired:
            if fired == "fist":
                paused = not paused
                print(f"[STATE] PAUSED={paused}")
            elif fired == "peace":
                print("[STATE] QUIT requested.")
                hands.close(); cap.release(); cv2.destroyAllWindows()
                return
            elif fired == "rock":
                print("[GESTURE] ROCK 🤘 → SCROLL UP")
            elif fired == "shaka":
                print("[GESTURE] SHAKA 🤙 → SCROLL DOWN")
            elif fired == "ok":
                print("[GESTURE] OK 👌 → START SLIDESHOW")
                start_slideshow()
            elif fired == "open":
                print("[GESTURE] OPEN ✋ → STOP SLIDESHOW")
                stop_slideshow()

        # swipe history for three-finger navigation
        if idx_xy:
            hist.append((now, idx_xy[0], idx_xy[1]))

        if not paused and len(hist) >= 2:
            t_cut = now - SWIPE_WINDOW_MS/1000.0
            old = None
            for t, x, y in hist:
                if t >= t_cut:
                    old = (t, x, y); break
            if old and (now - _last_swipe_fire) >= SWIPE_COOL_MS/1000.0:
                _, x0, y0 = old
                _, x1, y1 = hist[-1]
                dx, dy = x1 - x0, y1 - y0

                # Three-finger left/right = prev/next section
                if name == "three" and abs(dx) >= SWIPE_MIN_DX and abs(dx) > abs(dy):
                    if dx > 0:
                        print("[SWIPE] THREE → NEXT SECTION")
                    else:
                        print("[SWIPE] THREE → PREVIOUS SECTION")
                    _last_swipe_fire = now

        # HUD
        hud = f"{name or '-'} | PAUSED={paused}"
        cv2.putText(frame, hud, (10, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.imshow("Gestures (q to quit)", frame)
        if (cv2.waitKey(1) & 0xFF) == ord('q'):
            break

    hands.close()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
