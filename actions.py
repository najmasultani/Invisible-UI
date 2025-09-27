# actions.py
import platform
import time

try:
    import pyautogui
except Exception:
    pyautogui = None

IS_MAC = platform.system() == "Darwin"

# --- optional tiny debounce so two inputs (voice+gesture) don't double-fire ---
_LAST = {"t": 0.0}
DEBOUNCE_SEC = 0.15
def _ok():
    now = time.time()
    if now - _LAST["t"] < DEBOUNCE_SEC:
        return False
    _LAST["t"] = now
    return True

def _need_pyauto():
    if pyautogui is None:
        print("[actions] pyautogui not installed. pip install pyautogui")
        return True
    return False

# -------- Slides navigation --------
def next_slide():
    if _need_pyauto() or not _ok(): return
    pyautogui.press("right"); print("[actions] NEXT →")

def prev_slide():
    if _need_pyauto() or not _ok(): return
    pyautogui.press("left"); print("[actions] PREV ←")

def start_slideshow():
    if _need_pyauto() or not _ok(): return
    if IS_MAC:
        pyautogui.keyDown("command"); pyautogui.press("enter"); pyautogui.keyUp("command")
    else:
        pyautogui.keyDown("ctrl"); pyautogui.press("enter"); pyautogui.keyUp("ctrl")
    print("[actions] Start slideshow (Present)")

def stop_slideshow():
    if _need_pyauto() or not _ok(): return
    pyautogui.press("esc"); print("[actions] Stop slideshow (Esc)")

def arrow_up():
    if _need_pyauto() or not _ok(): return
    pyautogui.press("up"); print("[actions] ArrowUp")

def arrow_down():
    if _need_pyauto() or not _ok(): return
    pyautogui.press("down"); print("[actions] ArrowDown")

def quit_app(cb=None):
    print("[actions] Quit requested")
    if cb: cb()

# -------- Video controls (while presenting on a slide with an embedded video) --------
# These mirror YouTube player shortcuts that also work inside Google Slides video frames.
def video_play_pause():
    if _need_pyauto() or not _ok(): return
    pyautogui.press("k")  # Space also works; K is more reliable for play/pause
    print("[actions] Video: Play/Pause (K)")

def video_back_10():
    if _need_pyauto() or not _ok(): return
    pyautogui.press("j")  # -10s
    print("[actions] Video: -10s (J)")

def video_forward_10():
    if _need_pyauto() or not _ok(): return
    pyautogui.press("l")  # +10s
    print("[actions] Video: +10s (L)")
