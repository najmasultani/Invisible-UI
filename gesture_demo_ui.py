# gesture_demo_no_ui.py
import time
from math import hypot
import threading

import cv2
import mediapipe as mp
import tkinter as tk
from PIL import Image, ImageTk  # safe preview in Tk

# For sending keys to Google Slides in the browser
try:
    import pyautogui
except Exception:
    pyautogui = None  # we'll warn in the UI if not installed

IS_MAC = platform.system() == "Darwin"

# ---------- Camera / MP settings ----------
W, H = 640, 360
MIN_DET, MIN_TRK = 0.6, 0.6

# Stabilizer for static gestures
HOLD_MS, COOL_MS = 250, 800
_last_name, _start_t, _last_fire_t = None, 0.0, 0.0

# ---------- Finger helpers ----------
def _d(a, b): return hypot(a.x - b.x, a.y - b.y)
def _hand_size(lm): return _d(lm[0], lm[9]) + 1e-6

def _extended(lm, tip, pip, thr=0.35):
    """Finger extended if tip is farther from wrist than its PIP joint by a threshold proportion of hand size."""
    wrist = lm[0]
    return (_d(lm[tip], wrist) - _d(lm[pip], wrist)) > (thr * _hand_size(lm))

# ---- gesture classifiers (no fist / no three-finger) ----
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
    # 👌 index+thumb tips close (circle) AND other fingers extended
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
    if is_peace(lm):      return "peace"       # quit
    if is_thumb_up(lm):   return "thumb_up"    # next
    if is_thumb_down(lm): return "thumb_down"  # previous
    if is_rock(lm):       return "rock"        # scroll up / ArrowUp
    if is_shaka(lm):      return "shaka"       # scroll down / ArrowDown
    if is_ok(lm):         return "ok"          # start slideshow
    if is_open(lm):       return "open"        # stop slideshow
    return None

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

# ---------- UI App ----------
class DemoApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Gesture Demo (gesture-only)")
        self.root.geometry("980x640")
        self.root.configure(bg="white")  # light background

        # quick quit keybinds
        self.root.bind("q", lambda e: self.quit())
        self.root.bind("<Escape>", lambda e: self.quit())

        self.paused = False
        self.sections = ["Inbox", "Notes", "Tasks", "Calendar"]
        self.section_index = 0

        # for preview/frame exchange across threads
        self.latest_bgr = None
        self._tkimg = None  # keep a ref so ImageTk isn't GC'd
        self.name = None    # current static gesture name

def is_ok(lm):
    # 👌 index+thumb tips close; other fingers extended
    thumb_tip, index_tip = lm[4], lm[8]
    close = _d(thumb_tip, index_tip) < 0.035
    mid_ext  = _extended(lm,12,10)
    ring_ext = _extended(lm,16,14)
    pink_ext = _extended(lm,20,18)
    return close and (mid_ext and ring_ext and pink_ext)

        self.running = True
        self.cap, self.hands = None, None

        t = threading.Thread(target=self.camera_loop, daemon=True)
        t.start()

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

        self.chip = tk.Label(top, text="LIVE", fg="white", bg="#2e7d32", padx=10, pady=6)
        self.chip.pack(side="right", padx=8)

        # Camera preview box (top-right)
        self.preview = tk.Label(self.root, bd=1, relief="solid", bg="white")
        # Place it under the top bar to the right
        self.preview.place(x=self.root.winfo_reqwidth()-PREVIEW_SIZE[0]-20, y=56,
                           width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1])

        # Body split: left sections, right content
        body = tk.Frame(self.root, bg="white")
        body.pack(side="top", fill="both", expand=True)

        # Left: sections list
        left = tk.Frame(body, width=200, bg="white")
        left.pack(side="left", fill="y")
        tk.Label(left, text="Sections", font=("Arial", 12, "bold"),
                 fg="#111", bg="white").pack(anchor="w", padx=12, pady=(12, 0))

# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser(description="Gesture control for Google Slides (no UI).")
    parser.add_argument("--no-preview", action="store_true",
                        help="Run without showing the camera window.")
    args = parser.parse_args()

        # Right: scrollable content
        right = tk.Frame(body, bg="white")
        right.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(right, bg="white", highlightthickness=0)
        self.scroll_y = tk.Scrollbar(right, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll_y.set)
        self.scroll_y.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.content = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        # Populate visible, dark text on white bg
        for i in range(60):
            tk.Label(
                self.content,
                text=f"Line {i+1}: Lorem ipsum dolor sit amet…",
                bg="white", fg="#111111", anchor="w"
            ).pack(fill="x", padx=16, pady=3)

        self.content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        hint = tk.Label(
            self.root,
            text="Fist=Pause/Resume • Peace=Quit • Point + Swipe L/R=Change Section • Three + Swipe U/D=Scroll",
            fg="#333333", bg="white"
        )
        hint.pack(side="bottom", fill="x", pady=8)

    # ----- HUD update -----
    def tick_hud(self):
        sec = self.sections[self.section_index]
        self.status.config(text=f"PAUSED={self.paused} | Section: {sec} | static: {self.name or '-'}")
        self.chip.config(text="PAUSED" if self.paused else "LIVE",
                         bg="#c62828" if self.paused else "#2e7d32")
        if self.running:
            self.root.after(120, self.tick_hud)

    # ----- Actions (UI only, no OS keys) -----
    def next_section(self):
        self.section_index = (self.section_index + 1) % len(self.sections)
        self.listbox.select_clear(0, "end")
        self.listbox.select_set(self.section_index)

    def prev_section(self):
        self.section_index = (self.section_index - 1) % len(self.sections)
        self.listbox.select_clear(0, "end")
        self.listbox.select_set(self.section_index)

    def scroll_up(self):   self.canvas.yview_scroll(-3, "units")
    def scroll_down(self): self.canvas.yview_scroll(3,  "units")

    def toggle_pause(self):
        self.paused = not self.paused
        print(f"[STATE] PAUSED={self.paused}")

    def quit(self):
        print("[STATE] Quit via peace sign")
        self.running = False
        try:
            if self.cap: self.cap.release()
        except Exception:
            pass
        self.root.after(100, self.root.destroy)

    # ----- Camera / Gesture Thread -----
    def camera_loop(self):
        global _last_swipe_fire
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
        if not cap.isOpened():
            print("Could not open webcam")
            self.root.after(0, self.quit)
            return

        hands = mp.solutions.hands.Hands(
            static_image_mode=False, max_num_hands=1, model_complexity=1,
            min_detection_confidence=MIN_DET, min_tracking_confidence=MIN_TRK
        )

        drawer = mp.solutions.drawing_utils
        style = mp.solutions.drawing_styles

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

            # Keep a copy for preview BEFORE drawing, so HUD stays readable
            self.latest_bgr = frame.copy()

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = hands.process(rgb)
            now = time.time()

            name = None
            idx_xy = None

            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0].landmark
                name = classify(lm)
                idx_xy = (lm[8].x, lm[8].y)

                # draw landmarks on the preview copy (optional)
                # (we won't show this via OpenCV; preview is handled in Tk)
                pass

        fired = stable_emit(name, now)

            if fired == "fist":
                self.root.after(0, self.toggle_pause)
            elif fired == "peace":
                self.root.after(0, self.quit)
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

            if idx_xy:
                hist.append((now, idx_xy[0], idx_xy[1]))

            # swipes when not paused
            if not self.paused and len(hist) >= 2:
                t_cut = now - SWIPE_WINDOW_MS/1000.0
                old = None
                for t, x, y in hist:
                    if t >= t_cut:
                        old = (t, x, y); break
                if old and (now - _last_swipe_fire) >= SWIPE_COOL_MS/1000.0:
                    _, x0, y0 = old
                    _, x1, y1 = hist[-1]
                    dx, dy = x1 - x0, y1 - y0

                    # horizontal with POINT
                    if name == "point" and abs(dx) >= SWIPE_MIN_DX and abs(dx) > abs(dy):
                        if dx > 0:
                            print("[SWIPE] RIGHT → NEXT_SECTION")
                            self.root.after(0, self.next_section)
                        else:
                            print("[SWIPE] LEFT → PREV_SECTION")
                            self.root.after(0, self.prev_section)
                        _last_swipe_fire = now

                    # vertical with THREE
                    elif name == "three" and abs(dy) >= SWIPE_MIN_DY and abs(dy) > abs(dx):
                        if dy < 0:
                            print("[SWIPE] UP → SCROLL_UP")
                            self.root.after(0, self.scroll_up)
                        else:
                            print("[SWIPE] DOWN → SCROLL_DOWN")
                            self.root.after(0, self.scroll_down)
                        _last_swipe_fire = now

        try:
            hands.close()
        except Exception:
            pass
        try:
            cap.release()
        except Exception:
            pass

    # ----- Preview in Tk (main thread) -----
    def render_preview(self):
        if self.latest_bgr is not None:
            # Convert latest frame BGR -> RGB
            rgb = cv2.cvtColor(self.latest_bgr, cv2.COLOR_BGR2RGB)
            # Draw a small HUD onto the preview image
            hud = f"{self.name or '-'} | {'PAUSED' if self.paused else 'LIVE'}"
            cv2.putText(rgb, hud, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 180, 0), 1)

            img = Image.fromarray(rgb).resize(PREVIEW_SIZE)
            self._tkimg = ImageTk.PhotoImage(img)
            self.preview.config(image=self._tkimg)

        if self.running:
            self.root.after(PREVIEW_FPS_MS, self.render_preview)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    main()
