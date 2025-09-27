# hand_detection.py
import cv2
import mediapipe as mp

W, H = 640, 360

mp_hands = mp.solutions.hands
mp_draw  = mp.solutions.drawing_utils
mp_style = mp.solutions.drawing_styles

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

    print("Press 'q' to quit. Show your hand to see landmarks.")
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # BGR -> RGB for MediaPipe
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        res = hands.process(rgb)

        if res.multi_hand_landmarks:
            for hand_lms in res.multi_hand_landmarks:
                # draw landmarks & connections
                mp_draw.draw_landmarks(
                    frame,
                    hand_lms,
                    mp_hands.HAND_CONNECTIONS,
                    mp_style.get_default_hand_landmarks_style(),
                    mp_style.get_default_hand_connections_style()
                )

        cv2.imshow("Hand Detection (q to quit)", frame)
        if (cv2.waitKey(1) & 0xFF) == ord('q'):
            break

    hands.close()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
