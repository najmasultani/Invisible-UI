# Invisible-UI

# 👋 Gesture Navigation System for Google Slides

DEMO: https://framer.com/projects/Zero-Distance--nV9PyBnMbb4wt0S3KW7i-uLQRz?node=augiA20Il

## ✅ What Are We Building?

We are building a **gesture-based navigation system** that allows users to control **Google Slides** using **hand gestures** detected via a webcam.

---

## 🧩 Components of the App

### 1. Hand Gesture Recognition
- Use a webcam to stream live video.

### 2. Video Stream → Gesture Classification
Input: video stream  
Output: string [gesture class]  

- Continuously capture video frames from the webcam.
- Analyze each frame to classify gestures such as:
  - Peace (✌️) → QUIT (also sends Esc if Slides Mode is ON)
  - Thumbs-Up (👍) → NEXT slide (Right Arrow)
  - Thumbs-Down (👎) → PREVIOUS slide (Left Arrow)
  - Rock (🤘) → SCROLL UP (Arrow Up)
  - Shaka (🤙) → SCROLL DOWN (Arrow Down)
  - OK sign (👌) → START SLIDESHOW (Cmd/Ctrl+Enter)
  - Open palm (✋) → STOP SLIDESHOW (Esc)


### 3. Gesture → Keyboard Command Mapping
Input: string [gesture class]  
Output: keyboard command  

- Map each recognized gesture to a corresponding keyboard command.

#### Example Mappings:
- `"Fist"` → (Neutral or pause state)
- `"3 fingers together, horizontal (up or down)"`:
  - If pointing **up** → simulate holding the **Up Arrow** key.
  - If pointing **down** → simulate holding the **Down Arrow** key.
  - The simulated key press should be held for **5 seconds**.

### 4. Keyboard Command → Presentation Control
Input: keyboard command  
Output: action in the presentation  

- Google Slides (or similar platforms) respond to arrow key input:
- Simulated key presses trigger slide navigation.

---

## 🔄 System Flow Overview



Create virtual environment:
```bash
python -m venv .venv
```

Entering virtual environment:
```bash
source .venv/bin/activate
```
