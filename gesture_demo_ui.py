# gesture_demo_ui.py
import time
from math import hypot
import threading
import platform

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

# ---------- App/Preview settings ----------
W, H = 640, 360                  # camera capture size
MIN_DET, MIN_TRK = 0.6, 0.6      # MediaPipe confidences
PREVIEW_SIZE = (180, 135)        # (w, h) camera tile in UI
PREVIEW_FPS_MS = 60              # ~16 fps

# Stabilizer for static gestures
HOLD_MS, COOL_MS = 250, 800
_last_name, _start_t, _last_fire_t = None, 0.0, 0.0

# ---------- Finger helpers ----------
def _d(a, b): return hypot(a.x - b.x, a.y - b.y)
def _hand_size(lm): return _d(lm[0], lm[9]) + 1e-6

def _extended(lm, tip, pip, thr=0.35):
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
        self.root.configure(bg="white")

        # Slides control toggle
        self.slides_mode = tk.BooleanVar(value=True)  # default ON since you're using Google Slides

        # simple sections just to visualize local actions
        self.sections = ["Inbox", "Notes", "Tasks", "Calendar"]
        self.section_index = 0

        # for preview/frame exchange across threads
        self.latest_bgr = None
        self._tkimg = None
        self.name = None

        self._build_ui()

        self.running = True
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

        ctrls = tk.Frame(top, bg="#111111")
        ctrls.pack(side="right", padx=8)

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

        # Camera preview
        self.preview = tk.Label(self.root, bd=1, relief="solid", bg="white")
        self.preview.place(x=800, y=58, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1])

        # Body split (for demo local actions)
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

        # Right: scrollable content (used for Rock/Shaka when Slides Mode is OFF)
        right = tk.Frame(body, bg="white")
        right.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(right, bg="white", highlightthickness=0)
        self.scroll_y = tk.Scrollbar(right, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll_y.set)
        self.scroll_y.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.content = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        for i in range(60):
            tk.Label(
                self.content,
                text=f"Line {i+1}: Lorem ipsum dolor sit amet…",
                bg="white", fg="#111111", anchor="w"
            ).pack(fill="x", padx=16, pady=3)

        self.content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        hint_text = (
            "Peace ✌️=Quit • Thumbs-Up 👍=Next • Thumbs-Down 👎=Previous • "
            "Rock 🤘=Scroll Up (UI) / ArrowUp (Slides) • Shaka 🤙=Scroll Down (UI) / ArrowDown (Slides) • "
            "OK 👌=Start Slideshow • Open ✋=Stop Slideshow"
        )
        hint = tk.Label(self.root, text=hint_text, fg="#333333", bg="white", wraplength=980, justify="left")
        hint.pack(side="bottom", fill="x", pady=8)

        if pyautogui is None:
            warn = tk.Label(
                self.root,
                text="Slides Mode needs 'pyautogui' (pip install pyautogui) and Accessibility permission on macOS.",
                fg="#b00020", bg="white"
            )
            warn.pack(side="bottom", pady=(0, 8))

    # ----- HUD update -----
    def tick_hud(self):
        mode = "Slides" if self.slides_mode.get() else "Local UI"
        self.status.config(text=f"Mode={mode} | static: {self.name or '-'}")
        if self.running:
            self.root.after(120, self.tick_hud)

    # ----- Local UI Actions (for demo pane) -----
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

    def quit(self):
        print("[STATE] Quit via peace sign")
        self.running = False
        self.root.after(100, self.root.destroy)

    # ----- Slides Actions (send keys) -----
    def start_slideshow(self):
        if pyautogui is None:
            print("[Slides] pyautogui not installed.")
            return
        try:
            if IS_MAC:
                pyautogui.keyDown("command"); pyautogui.press("enter"); pyautogui.keyUp("command")
            else:
                pyautogui.keyDown("ctrl"); pyautogui.press("enter"); pyautogui.keyUp("ctrl")
            print("[Slides] Start slideshow key sent. Ensure Slides window/tab is focused.")
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

    def slides_arrow_up(self):
        if pyautogui is None: return
        try:
            pyautogui.press("up")
            print("[Slides] ArrowUp")
        except Exception as e:
            print(f"[Slides] ArrowUp failed: {e}")

    def slides_arrow_down(self):
        if pyautogui is None: return
        try:
            pyautogui.press("down")
            print("[Slides] ArrowDown")
        except Exception as e:
            print(f"[Slides] ArrowDown failed: {e}")

    # ----- Camera / Gesture Thread -----
    def camera_loop(self):
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

            # Keep a copy for preview BEFORE drawing
            self.latest_bgr = frame.copy()

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = hands.process(rgb)
            now = time.time()

            name = None
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0].landmark
                name = classify(lm)

            fired = stable_emit(name, now)
            self.name = name

            # --- static gesture actions ---
            if fired == "peace":
                if self.slides_mode.get():
                    self.slides_exit()
                self.root.after(0, self.quit)
                break

            elif fired == "thumb_up":
                if self.slides_mode.get():
                    self.slides_next()
                else:
                    self.root.after(0, self.next_section)

            elif fired == "thumb_down":
                if self.slides_mode.get():
                    self.slides_prev()
                else:
                    self.root.after(0, self.prev_section)

            elif fired == "rock":
                if self.slides_mode.get():
                    self.slides_arrow_up()
                else:
                    self.root.after(0, self.scroll_up)

            elif fired == "shaka":
                if self.slides_mode.get():
                    self.slides_arrow_down()
                else:
                    self.root.after(0, self.scroll_down)

            elif fired == "ok":
                self.start_slideshow()

            elif fired == "open":
                self.slides_exit()

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
            rgb = cv2.cvtColor(self.latest_bgr, cv2.COLOR_BGR2RGB)
            hud = f"{self.name or '-'} | Mode={'Slides' if self.slides_mode.get() else 'Local'}"
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
