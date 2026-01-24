# Helpful Documentation

## Setup & Installation

To run this project, you need to have Python installed and set up the necessary dependencies.

### Prerequisites

- **Python 3.10+**: Ensure you have Python installed.
  - **Windows**: Download from [python.org](https://www.python.org/downloads/windows/).
  - **Mac**: Download from [python.org](https://www.python.org/downloads/macos/) or use `brew install python`.
- **Node.js**: The agent uses `npx`, so you need Node.js installed.
  - Download from [nodejs.org](https://nodejs.org/).

### Installation Steps

1.  **Clone the repository** (if you haven't already):
    ```bash
    git clone <your-repo-url>
    cd Ai_Browser_Agent
    ```

2.  **Create a Virtual Environment (Recommended)**
    It's best practice to use a virtual environment to keep dependencies isolated.

    *   **Windows**:
        ```cmd
        python -m venv venv
        venv\Scripts\activate
        ```
    *   **Mac/Linux**:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```

3.  **Install Dependencies**
    Install the required Python packages using `pip`:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables**
    You need a Google API Key for Gemini.
    - Get your key from [Google AI Studio](https://aistudio.google.com/).
    - Set the `GOOGLE_API_KEY` variable:
        *   **Windows (CMD)**: `set GOOGLE_API_KEY=your_actual_api_key`
        *   **Windows (PowerShell)**: `$env:GOOGLE_API_KEY="your_actual_api_key"`
        *   **Mac/Linux**: `export GOOGLE_API_KEY=your_actual_api_key`

### Running the Agent

Once setup is complete, run the agent with:

```bash
python agent.py
```

## Common Issues

### ModuleNotFoundError: No module named 'google'
This means you haven't installed the dependencies. Run `pip install -r requirements.txt`.

### Error: GOOGLE_API_KEY environment variable not set
You need to set the API key in your terminal before running the script. See step 4 above.
