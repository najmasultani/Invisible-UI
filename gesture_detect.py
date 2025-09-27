# gesture_detect.py
import time
from math import hypot
import platform
import cv2
import mediapipe as mp

# OPTIONAL: send real keypresses for Google Slides / PowerPoint
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

# ---- helpers ----
def _d(a, b): return hypot(a.x - b.x, a.y - b.y)
def _hand_size(lm): return _d(lm[0], lm[9]) + 1e-6

def _extended(lm, tip_id, pip_id, thr=0.35):
    """A finger is extended if tip is noticeably farther from wrist than its PIP joint."""
    wrist = lm[0]
    return (_d(lm[tip_id], wrist) - _d(lm[pip_id], wrist)) > (thr * _hand_size(lm))

def stable_emit(name, now):
    """Emit gesture only when held steadily for HOLD_MS and cooled down for COOL_MS."""
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
    # 👌 index+thumb tips close (circle) AND the other fingers extended (separates from 'pinch')
    thumb_tip, index_tip = lm[4], lm[8]
    close = _d(thumb_tip, index_tip) < 0.035
    mid_ext  = _extended(lm,12,10)
    ring_ext = _extended(lm,16,14)
    pink_ext = _extended(lm,20,18)
    return close and (mid_ext and ring_ext and pink_ext)

def is_thumb_up(lm):
    # 👍 thumb extended; other fingers curled; thumb pointing UP (tip y << base y)
    thumb_ext = _extended(lm,4,2)
    others_curled = sum([_extended(lm,8,6), _extended(lm,12,10),
                         _extended(lm,16,14), _extended(lm,20,18)]) == 0
    # orientation: y is downwards in MediaPipe; "up" means tip.y much smaller than base.y
    up = (lm[4].y + 0.02) < lm[2].y
    return thumb_ext and others_curled and up

def is_thumb_down(lm):
    # 👎 thumb extended; other fingers curled; thumb pointing DOWN (tip y >> base y)
    thumb_ext = _extended(lm,4,2)
    others_curled = sum([_extended(lm,8,6), _extended(lm,12,10),
                         _extended(lm,16,14), _extended(lm,20,18)]) == 0
    down = (lm[4].y - 0.02) > lm[2].y
    return thumb_ext and others_curled and down

def classify(lm):
    # Order matters: quit → unique actions
    if is_peace(lm):      return "peace"     # quit
    if is_thumb_up(lm):   return "thumb_up"  # next
    if is_thumb_down(lm): return "thumb_down"# previous
    if is_rock(lm):       return "rock"      # scroll up
    if is_shaka(lm):      return "shaka"     # scroll down
    if is_ok(lm):         return "ok"        # start slideshow
    if is_open(lm):       return "open"      # stop slideshow
    return None

# ---- slides helpers (optional OS control) ----
def send_next():
    if not pyautogui:
        print("[ACTION] NEXT (simulate)")
        return
    try:
        pyautogui.press("right")
    except Exception:
        pass

def send_prev():
    if not pyautogui:
        print("[ACTION] PREVIOUS (simulate)")
        return
    try:
        pyautogui.press("left")
    except Exception:
        pass

def start_slideshow():
    if not pyautogui:
        print("[ACTION] START SLIDESHOW (simulate)")
        return
    try:
        # Google Slides: Present
        if IS_MAC:
            pyautogui.keyDown("command"); pyautogui.press("enter"); pyautogui.keyUp("command")
        else:
            pyautogui.keyDown("ctrl"); pyautogui.press("enter"); pyautogui.keyUp("ctrl")
        print("[Slides] Present command sent.")
    except Exception:
        pass
    # PowerPoint fallback (F5) can be added if desired

def stop_slideshow():
    if not pyautogui:
        print("[ACTION] STOP SLIDESHOW (simulate)")
        return
    try:
        pyautogui.press("esc")
        print("[Slides] Esc sent.")
    except Exception:
        pass

# ---- main loop ----
def main():
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
    print("- Peace ✌️ : QUIT")
    print("- Thumbs-Up 👍 : NEXT (Right Arrow)")
    print("- Thumbs-Down 👎 : PREVIOUS (Left Arrow)")
    print("- Rock 🤘 : SCROLL UP")
    print("- Shaka 🤙 : SCROLL DOWN")
    print("- OK 👌 : START SLIDESHOW (Present)")
    print("- Open palm ✋ : STOP SLIDESHOW (Esc)")
    print("Press 'q' to quit as well.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = hands.process(rgb)

        name = None
        now = time.time()

        if res.multi_hand_landmarks:
            lm = res.multi_hand_landmarks[0].landmark
            name = classify(lm)

            # draw landmarks
            mp_draw.draw_landmarks(
                frame, res.multi_hand_landmarks[0],
                mp_hands.HAND_CONNECTIONS,
                mp_style.get_default_hand_landmarks_style(),
                mp_style.get_default_hand_connections_style()
            )

        # static gestures (fire once when held)
        fired = stable_emit(name, now)
        if fired:
            if fired == "peace":
                print("[STATE] QUIT requested.")
                hands.close(); cap.release(); cv2.destroyAllWindows()
                return
            elif fired == "thumb_up":
                print("[GESTURE] 👍 → NEXT")
                send_next()
            elif fired == "thumb_down":
                print("[GESTURE] 👎 → PREVIOUS")
                send_prev()
            elif fired == "rock":
                print("[GESTURE] 🤘 → SCROLL UP")
                # (UI scrolling would happen in your UI app;
                # here we just log the action.)
            elif fired == "shaka":
                print("[GESTURE] 🤙 → SCROLL DOWN")
            elif fired == "ok":
                print("[GESTURE] 👌 → START SLIDESHOW")
                start_slideshow()
            elif fired == "open":
                print("[GESTURE] ✋ → STOP SLIDESHOW")
                stop_slideshow()

        # HUD
        hud = f"{name or '-'}"
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
