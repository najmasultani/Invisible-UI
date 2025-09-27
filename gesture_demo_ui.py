# gesture_demo_ui.py
import time
from collections import deque
from math import hypot
import threading
import platform

import cv2
import mediapipe as mp
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk  # for safe preview in Tk

# NEW: for sending keys to Google Slides when Slides Mode is ON
try:
    import pyautogui
except Exception:
    pyautogui = None  # we'll warn in the UI if not installed

IS_MAC = platform.system() == "Darwin"

# ---------- App/Preview settings ----------
W, H = 640, 360                  # camera capture size
MIN_DET, MIN_TRK = 0.6, 0.6      # MediaPipe confidences
PREVIEW_SIZE = (180, 135)        # (w, h) camera tile in UI
PREVIEW_FPS_MS = 60              # ~16 fps

# Stabilizer for static gestures
HOLD_MS, COOL_MS = 250, 800
_last_name, _start_t, _last_fire_t = None, 0.0, 0.0

# Swipes (index fingertip displacement in normalized coords)
SWIPE_WINDOW_MS = 160
SWIPE_MIN_DX, SWIPE_MIN_DY = 0.14, 0.14
SWIPE_COOL_MS = 500
_last_swipe_fire = 0.0

# Finger history for swipe detection
hist = deque(maxlen=30)  # (t, x, y)

# ---------- Finger helpers ----------
def _d(a, b): return hypot(a.x - b.x, a.y - b.y)
def _hand_size(lm): return _d(lm[0], lm[9]) + 1e-6

def _extended(lm, tip, pip, thr=0.35):
    # A finger is "extended" if the tip is noticeably farther from the wrist than its PIP joint
    wrist = lm[0]
    return (_d(lm[tip], wrist) - _d(lm[pip], wrist)) > (thr * _hand_size(lm))

def is_fist(lm):
    # none of index/middle/ring/pinky extended (ignore thumb for robustness)
    fingers = [
        _extended(lm, 8,6), _extended(lm,12,10),
        _extended(lm,16,14), _extended(lm,20,18)
    ]
    return sum(fingers) == 0

def is_point(lm):
    # index only extended
    idx  = _extended(lm,8,6)
    mid  = _extended(lm,12,10)
    ring = _extended(lm,16,14)
    pink = _extended(lm,20,18)
    return idx and not (mid or ring or pink)

def is_three(lm):
    # index + middle + ring extended; pinky curled
    idx  = _extended(lm,8,6)
    mid  = _extended(lm,12,10)
    ring = _extended(lm,16,14)
    pink = _extended(lm,20,18)
    return idx and mid and ring and not pink

def is_peace(lm):
    # index + middle extended, ring + pinky curled
    idx  = _extended(lm,8,6)
    mid  = _extended(lm,12,10)
    ring = _extended(lm,16,14)
    pink = _extended(lm,20,18)
    return idx and mid and (not ring) and (not pink)

def classify(lm):
    # order matters to avoid conflicts
    if is_peace(lm): return "peace"   # quit / exit slideshow
    if is_fist(lm):  return "fist"    # pause/resume
    if is_point(lm): return "point"   # L/R navigation
    if is_three(lm): return "three"   # U/D scrolling (UI only)
    return None

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

# ---------- UI App ----------
class DemoApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Gesture Demo • Slides Control")
        self.root.geometry("1000x660")
        self.root.configure(bg="white")  # light background

        # quick quit keybinds
        self.root.bind("q", lambda e: self.quit())
        self.root.bind("<Escape>", lambda e: self.quit())

        self.paused = False
        self.sections = ["Inbox", "Notes", "Tasks", "Calendar"]
        self.section_index = 0

        # Slides control toggle
        self.slides_mode = tk.BooleanVar(value=False)

        # for preview/frame exchange across threads
        self.latest_bgr = None
        self._tkimg = None  # keep a ref so ImageTk isn't GC'd
        self.name = None    # current static gesture name

        self._build_ui()

        self.running = True
        self.cap, self.hands = None, None

        t = threading.Thread(target=self.camera_loop, daemon=True)
        t.start()

        self.tick_hud()
        self.render_preview()

    # ----- UI -----
    def _build_ui(self):
        # Top bar
        top = tk.Frame(self.root, bg="#111111")
        top.pack(side="top", fill="x")

        self.status = tk.Label(
            top, text="", fg="white", bg="#111111",
            font=("Arial", 14), padx=12, pady=8
        )
        self.status.pack(side="left")

        # Slides mode controls
        ctrls = tk.Frame(top, bg="#111111")
        ctrls.pack(side="right", padx=8)

        self.chip = tk.Label(ctrls, text="LIVE", fg="white", bg="#2e7d32", padx=10, pady=6)
        self.chip.pack(side="right", padx=8)

        slides_chk = tk.Checkbutton(
            ctrls, text="Slides Mode", variable=self.slides_mode,
            fg="white", bg="#111111", selectcolor="#111111",
            activebackground="#111111", activeforeground="white"
        )
        slides_chk.pack(side="right", padx=8)

        start_btn = tk.Button(
            ctrls, text="Start slideshow (⌘/Ctrl+Enter)",
            command=self.start_slideshow, padx=10, pady=4
        )
        start_btn.pack(side="right", padx=8)

        # Camera preview box (top-right)
        self.preview = tk.Label(self.root, bd=1, relief="solid", bg="white")
        self.preview.place(x=800, y=58, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1])

        # Body split: left sections, right content
        body = tk.Frame(self.root, bg="white")
        body.pack(side="top", fill="both", expand=True)

        # Left: sections list
        left = tk.Frame(body, width=220, bg="white")
        left.pack(side="left", fill="y")
        tk.Label(left, text="Sections", font=("Arial", 12, "bold"),
                 fg="#111", bg="white").pack(anchor="w", padx=12, pady=(12, 0))

        self.listbox = tk.Listbox(
            left, height=len(self.sections),
            fg="#111111", bg="white", highlightthickness=1, selectbackground="#d0ebff"
        )
        for s in self.sections:
            self.listbox.insert("end", s)
        self.listbox.pack(fill="y", padx=12, pady=10)
        self.listbox.select_set(0)

        # Right: scrollable content (used when Slides Mode is OFF)
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

        hint_text = (
            "Fist=Pause/Resume • Peace=Quit • "
            "Point + Swipe L/R=Change Section (or Next/Prev Slide when Slides Mode ON) • "
            "Three + Swipe U/D=Scroll (UI only)"
        )
        hint = tk.Label(self.root, text=hint_text, fg="#333333", bg="white")
        hint.pack(side="bottom", fill="x", pady=8)

        # Warning if pyautogui missing
        if pyautogui is None:
            warn = tk.Label(
                self.root,
                text="Slides Mode needs 'pyautogui' (pip install pyautogui) and Accessibility permission on macOS.",
                fg="#b00020", bg="white"
            )
            warn.pack(side="bottom", pady=(0, 8))

    # ----- HUD update -----
    def tick_hud(self):
        sec = self.sections[self.section_index]
        mode = "Slides" if self.slides_mode.get() else "Local UI"
        self.status.config(text=f"Mode={mode} | PAUSED={self.paused} | Section: {sec} | static: {self.name or '-'}")
        self.chip.config(text="PAUSED" if self.paused else "LIVE",
                         bg="#c62828" if self.paused else "#2e7d32")
        if self.running:
            self.root.after(120, self.tick_hud)

    # ----- Local UI Actions (no OS keys) -----
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

    # ----- Slides Actions (send keys) -----
    def start_slideshow(self):
        if pyautogui is None:
            print("[Slides] pyautogui not installed.")
            return
        # Slides: ⌘Enter (mac) or Ctrl+Enter (win/linux) starts presenting (if supported)
        try:
            if IS_MAC:
                pyautogui.keyDown("command"); pyautogui.press("enter"); pyautogui.keyUp("command")
            else:
                pyautogui.keyDown("ctrl"); pyautogui.press("enter"); pyautogui.keyUp("ctrl")
            print("[Slides] Start slideshow key sent. Make sure the Slides tab/window is focused.")
        except Exception as e:
            print(f"[Slides] Failed to start slideshow: {e}")

    def slides_next(self):
        if pyautogui is None: return
        try:
            pyautogui.press("right")
            print("[Slides] Next slide →")
        except Exception as e:
            print(f"[Slides] next failed: {e}")

    def slides_prev(self):
        if pyautogui is None: return
        try:
            pyautogui.press("left")
            print("[Slides] Prev slide ←")
        except Exception as e:
            print(f"[Slides] prev failed: {e}")

    def slides_exit(self):
        if pyautogui is None: return
        try:
            pyautogui.press("esc")
            print("[Slides] Exit slideshow ⎋")
        except Exception as e:
            print(f"[Slides] exit failed: {e}")

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

        while self.running:
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

            fired = stable_emit(name, now)
            self.name = name

            if fired == "fist":
                self.root.after(0, self.toggle_pause)
            elif fired == "peace":
                # If Slides Mode is ON, also send Esc to exit before quitting UI
                if self.slides_mode.get():
                    self.slides_exit()
                self.root.after(0, self.quit)
                break

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

                    slides_on = self.slides_mode.get()

                    # horizontal with POINT
                    if name == "point" and abs(dx) >= SWIPE_MIN_DX and abs(dx) > abs(dy):
                        if slides_on:
                            if dx > 0: self.slides_next()
                            else:      self.slides_prev()
                        else:
                            if dx > 0: self.root.after(0, self.next_section)
                            else:      self.root.after(0, self.prev_section)
                        _last_swipe_fire = now

                    # vertical with THREE
                    elif name == "three" and abs(dy) >= SWIPE_MIN_DY and abs(dy) > abs(dx):
                        # In Slides mode, we ignore vertical swipes (to keep things simple).
                        if not slides_on:
                            if dy < 0: self.root.after(0, self.scroll_up)
                            else:      self.root.after(0, self.scroll_down)
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
    mp.solutions.hands  # ensure module load
    app = DemoApp()
    app.run()
