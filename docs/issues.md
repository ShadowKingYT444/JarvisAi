# Code Review & Issue Summary

## 🚨 Critical Issues (Potential Non-Functionality)

### 1. **macOS AppleScript Execution Policy**
   - **File:** `browser_control.py`
   - **Issue:** The `subprocess.run(["osascript", ...])` calls rely on the user granting "Accessibility" and "Apple Events" permissions to the terminal/application running the script.
   - **Impact:** If permissions are not granted, all browser control features (closing tabs, getting URLs) will fail silently or crash the thread.
   - **Recommendation:** Add a try-catch block that specifically checks for permission errors (exit code 1) and prompts the user to enable permissions in System Settings -> Privacy & Security -> Automation.

### 2. **Audio Device Conflict (Microphone Locking)**
   - **File:** `wakeword/listener.py` vs `wakeword/stt.py`
   - **Issue:** `WakeWordListener` (Porcupine) and `SpeechToText` (SpeechRecognition) both attempt to access the microphone.
   - **Detail:** Porcupine holds the audio stream open. In `main.py`, `listener.listen()` returns `True` (stopping the recorder), but `stt.listen_and_transcribe()` immediately tries to open `sr.Microphone()`. On some systems (especially macOS CoreAudio), switching access this quickly can cause `OSError: [Errno -9981] Input overflowed` or device busy errors.
   - **Recommendation:** Ensure explicit `recorder.delete()` or release of resources in `listener.listen()` before returning, or add a small `time.sleep(0.1)` buffer between wake word detection and STT listening.

### 3. **Blocking Main Thread in Monitor Loop**
   - **File:** `main.py`
   - **Issue:** The `_monitor_loop` method in `JarvisAgent` is running in a `threading.Thread`, but the current implementation has a `pass` in the focus mode check:
     ```python
     if self.focus_mode_active:
         # Logic similar to before, simplified
         # Get active tab (requires applescript)
         # For now, let's just sleep to avoid blocking if not needed
         pass
     ```
   - **Impact:** **Active Distraction Monitoring is currently unimplemented/commented out in `main.py`!** The agent will claim to be in "Focus Mode" but will never actually close any distractions.
   - **Recommendation:** The logic from `jarvis_agent.py` (checking active tab, evaluating, closing) needs to be properly restored into this loop.

---

## ⚠️ Major Bugs & Logic Errors

### 4. **JSON Parsing Reliability**
   - **File:** `focus_manager.py`
   - **Issue:** The regex/string manipulation to extract JSON from Gemini's response is fragile:
     ```python
     if content.startswith("```"):
         content = "\n".join(lines[1:-1])
     ```
   - **Impact:** If the model returns text *before* the code block (e.g., "Here is the JSON: ```json..."), the parsing will fail, and tabs will default to "keep".
   - **Recommendation:** Use a robust JSON extractor that finds the first `{` or `[` and the last `}` or `]`, or use the `response_mime_type="application/json"` feature if available in the library version.

### 5. **Missing Tab Index Handling**
   - **File:** `browser_control.py`
   - **Issue:** AppleScript indexes are 1-based, but Playwright/internal logic often uses 0-based.
   - **Impact:** `close_tab(window_id, tab_index)` sends the index directly to AppleScript. If the internal logic (like in `focus_manager`) treats it as 0-based, we might close the *wrong* tab (off by one error).
   - **Recommendation:** Standardize on 0-based internally and add `+1` only when formatting the AppleScript string.

---

## 🔧 Minor Issues & Optimizations

### 6. **Hardcoded Voice Rate**
   - **File:** `main.py`
   - **Issue:** `["say", "-v", "Samantha", "-r", "200", text]` uses a fixed rate.
   - **Impact:** Might be too fast/slow for some users.
   - **Recommendation:** Move configuration to `.env` or a config file.

### 7. **Dependencies**
   - **File:** `requirements.txt`
   - **Issue:** `faster-whisper` and `google-genai` versions are pinned broadly.
   - **Impact:** Breaking changes in newer API versions could break the app.
   - **Recommendation:** Pin to specific tested minor versions (e.g., `google-genai==0.3.0`).

---

## ✅ Summary
The most critical issue is #3 (Monitor Loop unimplemented), which renders the core "Focus Mode" feature non-functional. Issue #2 (Audio conflict) is the most likely cause of runtime crashes.
