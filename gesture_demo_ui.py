# gesture_demo_no_ui.py
import time
from math import hypot
import platform
import argparse

import cv2
import mediapipe as mp

# OPTIONAL: send real keypresses to the active window (Slides/PowerPoint)
try:
    import pyautogui
except Exception:
    pyautogui = None

IS_MAC = platform.system() == "Darwin"

# ---------- Camera / MP settings ----------
W, H = 640, 360
MIN_DET, MIN_TRK = 0.6, 0.6

# Stabilizer for static gestures
HOLD_MS, COOL_MS = 250, 800
_last_name, _start_t, _last_fire_t = None, 0.0, 0.0

# ---------- Helpers ----------
def _d(a, b): return hypot(a.x - b.x, a.y - b.y)
def _hand_size(lm): return _d(lm[0], lm[9]) + 1e-6

def _extended(lm, tip, pip, thr=0.35):
    """Finger extended if tip is farther from wrist than its PIP joint by a threshold proportion of hand size."""
    wrist = lm[0]
    return (_d(lm[tip], wrist) - _d(lm[pip], wrist)) > (thr * _hand_size(lm))

def stable_emit(name, now):
    """Emit gesture only when held steadily and not on cooldown."""
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

# ---------- Gesture classifiers ----------
def is_peace(lm):
    idx, mid = _extended(lm,8,6), _extended(lm,12,10)
    ring, pink = _extended(lm,16,14), _extended(lm,20,18)
    return idx and mid and not (ring or pink)

def is_rock(lm):
    # 🤘 index + pinky extended; middle+ring curled
    idx  = _extended(lm,8,6)
    pink = _extended(lm,20,18)
    mid  = _extended(lm,12,10)
    ring = _extended(lm,16,14)
    return idx and pink and not (mid or ring)

def is_shaka(lm):
    # 🤙 thumb + pinky extended; others curled
    thumb = _extended(lm,4,2)
    pink  = _extended(lm,20,18)
    idx   = _extended(lm,8,6)
    mid   = _extended(lm,12,10)
    ring  = _extended(lm,16,14)
    return thumb and pink and not (idx or mid or ring)

def is_open(lm):
    # ✋ all four fingers extended (ignore thumb for robustness)
    return all(_extended(lm,t,p) for t,p in [(8,6),(12,10),(16,14),(20,18)])

def is_ok(lm):
    # 👌 index+thumb tips close; other fingers extended
    thumb_tip, index_tip = lm[4], lm[8]
    close = _d(thumb_tip, index_tip) < 0.035
    mid_ext  = _extended(lm,12,10)
    ring_ext = _extended(lm,16,14)
    pink_ext = _extended(lm,20,18)
    return close and (mid_ext and ring_ext and pink_ext)

def is_thumb_up(lm):
    # 👍 thumb extended; others curled; thumb pointing UP (tip y << base y)
    thumb_ext = _extended(lm,4,2)
    others_curled = sum([_extended(lm,8,6), _extended(lm,12,10),
                         _extended(lm,16,14), _extended(lm,20,18)]) == 0
    up = (lm[4].y + 0.02) < lm[2].y  # y increases downward
    return thumb_ext and others_curled and up

def is_thumb_down(lm):
    # 👎 thumb extended; others curled; thumb pointing DOWN (tip y >> base y)
    thumb_ext = _extended(lm,4,2)
    others_curled = sum([_extended(lm,8,6), _extended(lm,12,10),
                         _extended(lm,16,14), _extended(lm,20,18)]) == 0
    down = (lm[4].y - 0.02) > lm[2].y
    return thumb_ext and others_curled and down

def classify(lm):
    # Order matters: quit → thumbs → rock/shaka → ok/open
    if is_peace(lm):      return "peace"
    if is_thumb_up(lm):   return "thumb_up"
    if is_thumb_down(lm): return "thumb_down"
    if is_rock(lm):       return "rock"
    if is_shaka(lm):      return "shaka"
    if is_ok(lm):         return "ok"
    if is_open(lm):       return "open"
    return None

# ---------- Key sending ----------
def send_next():
    if pyautogui is None:
        print("[ACTION] NEXT (simulate)"); return
    pyautogui.press("right")

def send_prev():
    if pyautogui is None:
        print("[ACTION] PREVIOUS (simulate)"); return
    pyautogui.press("left")

def send_arrow_up():
    if pyautogui is None:
        print("[ACTION] ArrowUp (simulate)"); return
    pyautogui.press("up")

def send_arrow_down():
    if pyautogui is None:
        print("[ACTION] ArrowDown (simulate)"); return
    pyautogui.press("down")

def start_slideshow():
    if pyautogui is None:
        print("[ACTION] START SLIDESHOW (simulate)"); return
    if IS_MAC:
        pyautogui.keyDown("command"); pyautogui.press("enter"); pyautogui.keyUp("command")
    else:
        pyautogui.keyDown("ctrl"); pyautogui.press("enter"); pyautogui.keyUp("ctrl")
    print("[Slides] Present command sent.")

def stop_slideshow():
    if pyautogui is None:
        print("[ACTION] STOP SLIDESHOW (simulate)"); return
    pyautogui.press("esc")
    print("[Slides] Esc sent.")

# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser(description="Gesture control for Google Slides (no UI).")
    parser.add_argument("--no-preview", action="store_true",
                        help="Run without showing the camera window.")
    args = parser.parse_args()

    mp_hands = mp.solutions.hands
    mp_draw  = mp.solutions.drawing_utils
    mp_style = mp.solutions.drawing_styles

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam")

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        model_complexity=1,
        min_detection_confidence=MIN_DET,
        min_tracking_confidence=MIN_TRK,
    )

    print("Controls:")
    print("  ✌️  Peace  -> Quit (Esc first)")
    print("  👍  Thumbs-Up -> Next slide")
    print("  👎  Thumbs-Down -> Previous slide")
    print("  🤘  Rock -> ArrowUp")
    print("  🤙  Shaka -> ArrowDown")
    print("  👌  OK -> Start slideshow (Cmd/Ctrl+Enter)")
    print("  ✋  Open -> Stop slideshow (Esc)")
    print("Press 'q' to quit.")

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = hands.process(rgb)
        now = time.time()

        name = None
        if res.multi_hand_landmarks:
            lm = res.multi_hand_landmarks[0].landmark
            name = classify(lm)

            if not args.no_preview:
                mp_draw.draw_landmarks(
                    frame, res.multi_hand_landmarks[0],
                    mp_hands.HAND_CONNECTIONS,
                    mp_style.get_default_hand_landmarks_style(),
                    mp_style.get_default_hand_connections_style()
                )

        fired = stable_emit(name, now)

        if fired:
            if fired == "peace":
                # exit slideshow if presenting, then quit
                stop_slideshow()
                print("[STATE] Quit.")
                break
            elif fired == "thumb_up":
                print("[GESTURE] 👍 -> NEXT"); send_next()
            elif fired == "thumb_down":
                print("[GESTURE] 👎 -> PREVIOUS"); send_prev()
            elif fired == "rock":
                print("[GESTURE] 🤘 -> ArrowUp"); send_arrow_up()
            elif fired == "shaka":
                print("[GESTURE] 🤙 -> ArrowDown"); send_arrow_down()
            elif fired == "ok":
                print("[GESTURE] 👌 -> START slideshow"); start_slideshow()
            elif fired == "open":
                print("[GESTURE] ✋ -> STOP slideshow"); stop_slideshow()

        if not args.no_preview:
            hud = f"{name or '-'}"
            cv2.putText(frame, hud, (10, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
            cv2.imshow("Gesture Control (press q to quit)", frame)
            if (cv2.waitKey(1) & 0xFF) == ord('q'):
                break
        else:
            # tiny sleep to avoid 100% CPU when preview is off
            time.sleep(0.005)

    hands.close()
    cap.release()
    if not args.no_preview:
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
