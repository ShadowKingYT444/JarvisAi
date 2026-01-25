# Testing Guide

This project now supports text-based input testing and a comprehensive automated test suite.

## 1. Text-Based Interactive Mode
You can interact with Jarvis and Soren without a microphone using the CLI text mode. This is useful for debugging logic, intent parsing, and filler word removal.

**Usage:**
```bash
python main.py --test
```
**Commands:**
- Type `Jarvis, <command>` to send a command to Jarvis.
- Type `Soren, <question>` to ask Soren a question.
- Type `exit` or `quit` to close the application.

**Examples:**
- `Jarvis, turn on focus mode`
- `Soren, what is the speed of light?`
- `Um, Jarvis, open Google` (Tests filler word removal)

## 2. Automated Regression Tests
We have a dedicated test driver `test_driver.py` that mocks the Browser and TTS components to verify core logic without side effects (like actually closing your browser tabs).

**Run Tests:**
```bash
python test_driver.py
```

**What is Tested:**
- **Filler Word Removal:** Ensures words like "um", "uh", "like" are stripped.
- **Intent Parsing:** Verifies Gemini API integration for commands.
- **Focus Mode:** Simulates the multi-turn conversation for setting a focus goal and verifying distraction sweeping.
- **Break Mode:** Verifies state transitions.
- **Soren/Alexa Knowledge:** Checks response quality and length constraints (<100 words).

## 3. Test Files
- `test_driver.py`: The main test suite using `unittest` and `unittest.mock`.
- `main.py`: Updated to include `TextWorker` and argument parsing for `--test`.
