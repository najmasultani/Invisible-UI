# camera_preview.py
import cv2

def main():
  
    cap = cv2.VideoCapture(0)  # if you have multiple cameras, try 1 or 2
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)

    if not cap.isOpened():
        raise RuntimeError("Could not open webcam")

    print("Press 'q' to quit the preview window.")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        cv2.imshow("Webcam Preview (press q to quit)", frame)
        # press q to exit
        if (cv2.waitKey(1) & 0xFF) == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
