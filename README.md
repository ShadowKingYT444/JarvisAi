# 🤖 JARVIS: The AI Flow State Guardian

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-yellow.svg)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)
![Powered By](https://img.shields.io/badge/Powered%20By-Gemini%202.0%20Flash-orange.svg)

> **"Your voice-controlled co-pilot for deep work."**

Jarvis is a desktop AI agent designed to protect your focus. Unlike standard voice assistants that just answer questions, **Jarvis actively enforces your productivity**. It manages your browser, filters distractions, and executes tasks via voice—so you never have to leave your keyboard or break your flow.

---

## ⚡ Key Features

*   **🛡️ Active Distraction Defense**
    *   Jarvis watches your browser 24/7.
    *   If you open a distraction (e.g., YouTube, Reddit) during "Focus Mode," Jarvis issues a **3-second warning** and then **mercilessly closes the tab**.
*   **🗣️ Near-Zero Latency Control**
    *   Powered by **Faster-Whisper** (local Int8 quantization) for instant transcription.
    *   Uses **Google Gemini 2.0 Flash** for ultra-fast intent understanding.
*   **🖐️ Hands-Free Browser Management**
    *   *"Jarvis, close all social media tabs."*
    *   *"Jarvis, switch to GitHub."*
    *   *"Jarvis, restore my last session."*
*   **💻 Native macOS Integration**
    *   Uses **AppleScript** for deep browser integration (Chrome & Safari).
    *   **PyQt6 Overlay**: A futuristic, non-intrusive "Blue Wave" HUD that appears only when you speak.

---

## 📸 Demo

*(Insert GIF/Screenshot here of the Blue Wave overlay appearing, user speaking, and a YouTube tab getting auto-closed)*

> **User:** "Jarvis, focus on coding."
> **Jarvis:** "Focus mode on. Keeping you sharp."
> *(User opens Twitter)*
> **Jarvis:** "Stay focused." *(Tab closes automatically)*

---

## 🏗️ Architecture

Jarvis isn't just a wrapper; it's a multi-threaded system designed for speed.

1.  **The Ears (Wake Word):** Uses `PvPorcupine` to listen for "Jarvis" efficiently on a background thread.
2.  **The Brain (STT & LLM):** 
    *   Audio is transcribed locally using `faster-whisper` (Privacy + Speed).
    *   Text is sent to **Gemini 2.0 Flash**, which parses natural language into JSON actions (e.g., `{"action": "close", "target": "youtube"}`).
3.  **The Hands (Automation):** The `AppleScriptBrowserControl` module interfaces directly with the macOS WindowServer to manipulate tabs and windows without flaky DOM selectors.
4.  **The Face (UI):** A transparent `PyQt6` overlay that renders visual feedback on top of your workflow without stealing input focus.

---

## 🚀 Getting Started

### Prerequisites
*   macOS (Optimized for AppleScript automation)
*   Python 3.10+
*   Google Chrome or Safari

### Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/ShadowKingYT444/JarvisAi.git
    cd JarvisAi
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up Environment Variables**
    Create a `.env` file in the root directory:
    ```env
    GOOGLE_API_KEY=your_gemini_api_key
    PICOVOICE_ACCESS_KEY=your_porcupine_key
    ```

4.  **Run Jarvis**
    ```bash
    python main.py
    ```

---

## 🎤 Command Guide

| Intent | Example Voice Command | Action |
| :--- | :--- | :--- |
| **Focus** | "Focus on writing code" | Enables Monitor. Blocks distractions. |
| **Navigation** | "Go to Gmail" | Switches to existing tab or opens new one. |
| **Cleanup** | "Close all social media" | Identifies and closes specific tabs. |
| **Break** | "Take a break" | Disables monitoring temporarily. |
| **Rescue** | "Restore my tabs" | Re-opens tabs Jarvis closed recently. |

---

## 🛠️ Tech Stack

*   **Core Logic:** Python
*   **AI Model:** Google Gemini 2.0 Flash
*   **Speech-to-Text:** Faster-Whisper (Local)
*   **Wake Word:** Picovoice Porcupine
*   **GUI:** PyQt6
*   **Automation:** AppleScript (osascript)

---

## 🔮 Future Roadmap

*   [ ] **Windows Support:** Re-implement `browser_control.py` using UIAutomation or Selenium/CDP.
*   [ ] **Context Awareness:** Allow Jarvis to "read" the screen content to answer questions about what you're working on.
*   [ ] **Lighthouse Integration:** Connect to smart lights to change room color based on Focus Mode status.

---

**Built with ❤️ for the Hackathon.**