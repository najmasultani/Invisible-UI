import pyautogui

# defining actions

def left(): pyautogui.press("left")
def right(): pyautogui.press("right")

# mapping

ACTIONS = {
    "left": left,
    "right": right,
}

def perform_action(motion_name):
    action = ACTIONS.get(motion_name)
    if action:
        print(f"ACTION: {motion_name}")
        action()
    else:
        print(f"WARNING Unknown event: {motion_name}")