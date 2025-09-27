# voice_control.py — mic context fixed; ElevenLabs STT optional; simple exact commands
import os
import string
import time
import json
import requests
import actions as act
import speech_recognition as sr

# ==== Config ====
ELEVEN_API_KEY = os.getenv("40a986a6c71277edbf49ea82440ea96623a1005d1e2687abdae285fae5bbd409", "").strip()
ELEVEN_STT_URL = os.getenv("ELEVEN_STT_URL", "https://api.elevenlabs.io/v1/speech-to-text")
USE_ELEVEN = bool(ELEVEN_API_KEY)

# ==== Commands (exact phrases; case/punctuation ignored) ====
COMMANDS = {
    # Slides
    "next":                act.next_slide,
    "next slide":          act.next_slide,
    

    "back":                act.prev_slide,
    "previous":            act.prev_slide,
    "previous slide":      act.prev_slide,
    "former":                act.prev_slide,

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

def elevenlabs_transcribe(audio_wav_bytes: bytes) -> str:
    if not USE_ELEVEN:
        return ""
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Accept": "application/json",
    }
    data = {
        # "model_id": "eleven_multilingual_stt_v1"  # set if your account requires it
    }
    files = {
        "audio": ("speech.wav", audio_wav_bytes, "audio/wav"),
    }
    try:
        resp = requests.post(ELEVEN_STT_URL, headers=headers, data=data, files=files, timeout=30)
        if resp.status_code != 200:
            print(f"[eleven] STT HTTP {resp.status_code}: {resp.text[:300]}")
            return ""
        payload = resp.json()
        text = payload.get("text") or payload.get("transcript") or ""
        if not text:
            print(f"[eleven] Unexpected STT payload: {json.dumps(payload)[:300]}")
        return text
    except Exception as e:
        print(f"[eleven] STT error: {e}")
        return ""

def google_transcribe(recognizer: sr.Recognizer, audio: sr.AudioData) -> str:
    try:
        return recognizer.recognize_google(audio)
    except Exception as e:
        print(f"[google] ASR error: {e}")
        return ""

def main():
    engine = "ElevenLabs" if USE_ELEVEN else "Google Web Speech"
    print(f"Voice Control ({engine}). No wake word. Say: next | back | start | stop | play | pause | forward ten | back ten | up | down | quit")

    rec = sr.Recognizer()

    # ---- Noise hardening (tweak to taste) ----
    rec.dynamic_energy_threshold = False
    rec.energy_threshold = 350   # raise (400–550) if noise triggers; lower (250–300) if misses voice
    rec.pause_threshold = 0.40
    rec.non_speaking_duration = 0.3
    rec.operation_timeout = 8

    # If you have multiple mics, set device_index here, e.g. sr.Microphone(device_index=1)

    with sr.Microphone(device_index=0) as mic:
        print("[voice] Calibrating… stay quiet for 1.0s")
        rec.adjust_for_ambient_noise(mic, duration=1.0)
        rec.dynamic_energy_threshold = False
        print(f"[voice] energy_threshold={rec.energy_threshold:.1f}")

        # >>> Keep the mic context open while listening <<<
        while True:
            try:
                print("[voice] Say a command…")
                audio = rec.listen(mic, timeout=6, phrase_time_limit=3.2)

                # Prefer ElevenLabs if key is set; otherwise Google fallback
                if USE_ELEVEN:
                    text = elevenlabs_transcribe(audio.get_wav_data())
                    if not text:
                        # optional: try google as backup even if Eleven returns nothing
                        text = google_transcribe(rec, audio)
                else:
                    text = google_transcribe(rec, audio)

                if not text:
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
