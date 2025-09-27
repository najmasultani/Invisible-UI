# voice_control.py  — simple, no wake word, easy commands
import string
import time
import actions as act
import speech_recognition as sr

# ===== Commands (exact phrases; case/punctuation ignored) =====
COMMANDS = {
    # Slides
    "next":                act.next_slide,
    "next slide":          act.next_slide,

    "back":                act.prev_slide,
    "previous":            act.prev_slide,
    "previous slide":      act.prev_slide,
    "prev":                act.prev_slide,

    "start":               act.start_slideshow,
    "start slideshow":     act.start_slideshow,
    "present":             act.start_slideshow,

    "stop":                act.stop_slideshow,
    "stop slideshow":      act.stop_slideshow,
    "exit slideshow":      act.stop_slideshow,
    "end slideshow":       act.stop_slideshow,

    # Video on slide
    "play":                act.video_play_pause,
    "pause":               act.video_play_pause,
    "start video":         act.video_play_pause,
    "stop video":          act.video_play_pause,

    "forward ten":         act.video_forward_10,
    "forward ten seconds": act.video_forward_10,
    "fast forward ten":    act.video_forward_10,

    "back ten":            act.video_back_10,
    "back ten seconds":    act.video_back_10,
    "rewind ten":          act.video_back_10,

    # Arrows (optional)
    "up":                  act.arrow_up,
    "down":                act.arrow_down,

    # Quit program
    "quit":                lambda: act.quit_app(),
    "exit":                lambda: act.quit_app(),
    "close app":           lambda: act.quit_app(),
}

_PUNCT = str.maketrans("", "", string.punctuation)
def normalize(text: str) -> str:
    return text.lower().translate(_PUNCT).strip()

def route(text: str) -> bool:
    key = normalize(text)
    fn = COMMANDS.get(key)
    if fn:
        fn()
        return True
    print(f"[voice] No exact match: “{text}”")
    return False

def main():
    print("Voice Control (no wake word). Say: next | back | start | stop | play | pause | forward ten | back ten | up | down | quit")
    rec = sr.Recognizer()

    # ---- Mic sensitivity (adjust if needed) ----
    rec.dynamic_energy_threshold = False
    rec.energy_threshold = 300    # try 250–500; increase if it triggers on noise
    rec.pause_threshold = 0.45
    rec.non_speaking_duration = 0.3
    rec.operation_timeout = 7

    with sr.Microphone() as mic:
        print("[voice] Calibrating… stay quiet for 1.0s")
        rec.adjust_for_ambient_noise(mic, duration=1.0)
        rec.dynamic_energy_threshold = False
        print(f"[voice] energy_threshold={rec.energy_threshold:.1f}")

        while True:
            try:
                print("[voice] Say a command…")
                audio = rec.listen(mic, timeout=6, phrase_time_limit=3.5)
                try:
                    text = rec.recognize_google(audio)
                except Exception as e:
                    print(f"[voice] ASR error: {e}")
                    continue

                print(f"[voice] Heard: {text}")
                if not route(text):
                    print("[voice] Try: next / back / start / stop / play / pause / forward ten / back ten / up / down / quit")
                time.sleep(0.12)

            except sr.WaitTimeoutError:
                continue
            except KeyboardInterrupt:
                print("\n[voice] Bye.")
                break

if __name__ == "__main__":
    main()
