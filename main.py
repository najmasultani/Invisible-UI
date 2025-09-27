# main.py
import sys

def ask(prompt="Choose control mode: [g]esture UI or [v]oice? "):
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return "g"

def main():
    mode = ask()
    if mode.startswith("v"):
        import voice_control
        print("Starting VOICE mode… (Slides tab must be focused)")
        voice_control.main()
    else:
        # default: gesture UI
        import gesture_demo_ui
        print("Starting GESTURE UI mode… (Slides tab must be focused)")
        # If gesture_demo_ui has a DemoApp class:
        if hasattr(gesture_demo_ui, "DemoApp"):
            gesture_demo_ui.DemoApp().run()
        else:
            # or if it exposes main()
            gesture_demo_ui.main()

if __name__ == "__main__":
    main()
