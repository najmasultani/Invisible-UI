# gesture_detect.py
import time
from collections import deque
from math import hypot
import cv2
import mediapipe as mp

W, H = 640, 360

mp_hands = mp.solutions.hands
mp_draw  = mp.solutions.drawing_utils
mp_style = mp.solutions.drawing_styles

# ---- static gesture stabilizer (hold + cooldown) ----
HOLD_MS = 250      # must hold the same gesture this long
COOL_MS = 800      # time after firing before another fire
_last_name = None
_start_t = 0.0
_last_fire_t = 0.0

# ---- swipe settings (index fingertip movement) ----
SWIPE_WINDOW_MS = 160           # lookback window for displacement
SWIPE_MIN_DX = 0.14             # normalized X displacement for L/R
SWIPE_MIN_DY = 0.14             # normalized Y displacement for U/D
SWIPE_COOL_MS = 500

paused = False
_last_swipe_fire = 0.0

# fingertip history deque for swipe detection
hist = deque(maxlen=30)  # (t, x, y)

def stable_emit(name, now):
    """Return the gesture name only when stable; else None."""
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

# ---- geometry helpers ----
def _d(a, b):
    return hypot(a.x - b.x, a.y - b.y)

def _hand_size(lm):
    # wrist(0) to middle MCP(9) as a scale ref (rotation/scale tolerant)
    return _d(lm[0], lm[9]) + 1e-6

def _extended(lm, tip_id, pip_id):
    # finger "extended" if tip noticeably farther from wrist than PIP joint
    wrist = lm[0]
    size = _hand_size(lm)
    tip_far = _d(lm[tip_id], wrist)
    pip_far = _d(lm[pip_id], wrist)
    return (tip_far - pip_far) > (0.35 * size)  # tweak 0.30–0.40 if needed

# ---- gesture classifiers (sturdier set) ----
def is_fist(lm):
    # none of index/middle/ring/pinky extended (ignore thumb for robustness)
    fingers = [
        _extended(lm, 8, 6),   # index
        _extended(lm, 12,10),  # middle
        _extended(lm, 16,14),  # ring
        _extended(lm, 20,18),  # pinky
    ]
    return sum(fingers) == 0

def is_point(lm):
    # index only extended
    idx  = _extended(lm, 8, 6)
    mid  = _extended(lm, 12,10)
    ring = _extended(lm, 16,14)
    pink = _extended(lm, 20,18)
    return idx and not (mid or ring or pink)

def is_three(lm):
    # index + middle + ring extended; pinky curled
    idx  = _extended(lm, 8, 6)
    mid  = _extended(lm, 12,10)
    ring = _extended(lm, 16,14)
    pink = _extended(lm, 20,18)
    return idx and mid and ring and not pink

def is_peace(lm):
    # index + middle extended, ring + pinky curled
    idx  = _extended(lm, 8, 6)
    mid  = _extended(lm, 12,10)
    ring = _extended(lm, 16,14)
    pink = _extended(lm, 20,18)
    return idx and mid and (not ring) and (not pink)

def classify(lm):
    # order matters (quit shouldn't collide with mode gestures)
    if is_peace(lm): return "peace"   # quit
    if is_fist(lm):  return "fist"    # pause/resume
    if is_point(lm): return "point"   # L/R navigation mode
    if is_three(lm): return "three"   # U/D scroll mode
    return None

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
    print("- Fist: toggle PAUSE/RESUME (movement actions disabled while paused)")
    print("- Peace ✌️ : QUIT")
    print("- Point + Swipe Right/Left: NEXT_SECTION / PREV_SECTION")
    print("- Three fingers + Swipe Up/Down: SCROLL_UP / SCROLL_DOWN")
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
            idx_xy = (lm[8].x, lm[8].y)  # index fingertip for swipes

            # draw landmarks
            mp_draw.draw_landmarks(
                frame, res.multi_hand_landmarks[0],
                mp_hands.HAND_CONNECTIONS,
                mp_style.get_default_hand_landmarks_style(),
                mp_style.get_default_hand_connections_style()
            )

        # ---- static gestures (fire once when held) ----
        fired = stable_emit(name, now)
        if fired:
            if fired == "fist":
                paused = not paused
                print(f"[STATE] PAUSED={paused}")
            elif fired == "peace":
                print("[STATE] QUIT via peace sign.")
                hands.close(); cap.release(); cv2.destroyAllWindows()
                return

        # ---- collect fingertip history for swipe detection ----
        if idx_xy:
            hist.append((now, idx_xy[0], idx_xy[1]))

        # ---- swipes (disabled while paused) ----
        if not paused and len(hist) >= 2:
            # find oldest sample within the swipe window
            t_cut = now - SWIPE_WINDOW_MS/1000.0
            old = None
            for t, x, y in hist:
                if t >= t_cut:
                    old = (t, x, y); break
            if old:
                _, x0, y0 = old
                _, x1, y1 = hist[-1]
                dx, dy = x1 - x0, y1 - y0

                if (now - _last_swipe_fire) >= SWIPE_COOL_MS/1000.0:
                    # When "point" is active -> horizontal navigation (ignore vertical)
                    if name == "point" and abs(dx) >= SWIPE_MIN_DX and abs(dx) > abs(dy):
                        if dx > 0:
                            print("[SWIPE] RIGHT with POINT → NEXT_SECTION")
                        else:
                            print("[SWIPE] LEFT with POINT → PREV_SECTION")
                        _last_swipe_fire = now

                    # When "three" is active -> vertical scrolling (ignore horizontal)
                    elif name == "three" and abs(dy) >= SWIPE_MIN_DY and abs(dy) > abs(dx):
                        if dy < 0:
                            print("[SWIPE] UP with THREE → SCROLL_UP")
                        else:
                            print("[SWIPE] DOWN with THREE → SCROLL_DOWN")
                        _last_swipe_fire = now

        # ---- HUD text ----
        hud1 = f"static: {name or '-'} | PAUSED={paused}"
        cv2.putText(frame, hud1, (10, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

        cv2.imshow("Gestures (q to quit)", frame)
        if (cv2.waitKey(1) & 0xFF) == ord('q'):
            break

    hands.close()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
