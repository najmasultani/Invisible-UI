# gesture_detect.py
import time
from math import hypot
import cv2
import mediapipe as mp

W, H = 640, 360

mp_hands = mp.solutions.hands
mp_draw  = mp.solutions.drawing_utils
mp_style = mp.solutions.drawing_styles

# ---- simple stabilizer (hold + cooldown) ----
HOLD_MS = 250      # must hold the same gesture this long
COOL_MS = 800      # time after firing before another fire
_last_name = None
_start_t = 0.0
_last_fire_t = 0.0

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
def dist(a, b):
    return hypot(a.x - b.x, a.y - b.y)

def classify(lm):
    """
    Very simple heuristics:
    - pinch: thumb tip (4) close to index tip (8)
    - open_palm: fingers splayed (tips far from bases)
    Tweak thresholds if needed based on your camera framing.
    """
    # pinch threshold: tighten/loosen this number if needed
    is_pinch = dist(lm[4], lm[8]) < 0.035

    # crude 'open' check: several tip-to-base distances are large
    is_open = (
        dist(lm[4],  lm[17]) > 0.20 and  # thumb tip to pinky base
        dist(lm[8],  lm[5])  > 0.10 and  # index tip to index base
        dist(lm[12], lm[9])  > 0.10 and  # middle tip to base
        dist(lm[16], lm[13]) > 0.10      # ring tip to base
    )

    if is_pinch:
        return "pinch"
    if is_open:
        return "open_palm"
    return None

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

    print("Show pinch/open-palm. Stable detections will print in the console. Press 'q' to quit.")
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = hands.process(rgb)

        name = None
        if res.multi_hand_landmarks:
            lm = res.multi_hand_landmarks[0].landmark
            name = classify(lm)

            # (optional) draw landmarks
            mp_draw.draw_landmarks(
                frame, res.multi_hand_landmarks[0],
                mp_hands.HAND_CONNECTIONS,
                mp_style.get_default_hand_landmarks_style(),
                mp_style.get_default_hand_connections_style()
            )

        now = time.time()
        stable = stable_emit(name, now)
        if stable:
            print(f"[STABLE] {stable} @ {now:.2f}")

        # on-screen hint
        cv2.putText(frame, f"raw: {name or '-'}", (10, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
        cv2.imshow("Gestures (q to quit)", frame)
        if (cv2.waitKey(1) & 0xFF) == ord('q'):
            break

    hands.close()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
