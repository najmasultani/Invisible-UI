# Invisible-UI

Create virtual environment:
```bash
python -m venv .venv
```

Entering virtual environment:
```bash
source .venv/bin/activate
```

What are we building?
The gestures navigation system in google slides.

Components of the app
- Hand gesture recognition
  - Video stream -> classified gesture
  - Gestures:
      - "Fist"
      - "3 fingers together horiznotal up or down"
- Classified gesture to a keyboard command
  - "3 fingers together horiznotal up or down" -> scroll up or down -> hold the key up or down for 5 seconds
- Keyboard command to an action on a presentation website
  - Use that key up or down for 5 seconds on the presentation website to move along the slides 





