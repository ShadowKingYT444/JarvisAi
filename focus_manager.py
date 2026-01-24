"""
Deep Work Fortress - Focus Manager
Semantic filter that evaluates browser tabs for relevance to the current goal.

Uses Google Gemini to judge whether tabs are work-related or distractions.
"""

import os
import json
from typing import TypedDict
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


class TabInfo(TypedDict):
    id: int
    title: str
    url: str


class TabEvaluation(TypedDict):
    id: int
    title: str
    score: int
    reason: str


class FocusManagerResult(TypedDict):
    tabs_to_keep: list[int]
    tabs_to_hide: list[int]
    evaluations: list[TabEvaluation]


class FocusManager:
    """
    Evaluates browser tabs for relevance to the user's current goal.
    Uses Google Gemini to semantically judge each tab.
    """
    
    RELEVANCE_THRESHOLD = 6  # Tabs scoring > 6 are kept
    
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Missing GOOGLE_API_KEY in .env")
        
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.0-flash"  # Fastest model
    
    def evaluate_tabs(self, tabs: list[TabInfo], current_goal: str) -> FocusManagerResult:
        """
        Evaluate a list of tabs against the current goal.
        
        Args:
            tabs: List of tab dictionaries with {id, title, url}
            current_goal: The user's current work focus (e.g., "Learning React Hooks")
            
        Returns:
            FocusManagerResult with tabs_to_keep, tabs_to_hide, and detailed evaluations
        """
        if not tabs:
            return {
                "tabs_to_keep": [],
                "tabs_to_hide": [],
                "evaluations": []
            }
        
        # Build the tab list for the prompt
        tab_list_str = "\n".join([
            f"- Tab {tab['id']}: \"{tab['title']}\" ({tab['url']})"
            for tab in tabs
        ])
        
        prompt = f"""You are a focus assistant helping someone stay on task.

The user's current goal is: "{current_goal}"

Here are their open browser tabs:
{tab_list_str}

For EACH tab, rate its relevance to the user's goal on a scale of 0-10:
- 0-3: Complete distraction (social media, entertainment, unrelated content)
- 4-6: Marginally related or neutral (might be useful later, but not for current task)
- 7-10: Directly relevant to the goal (documentation, research, tools for the task)

Respond with ONLY a JSON array containing an object for each tab:
[
  {{"id": 1, "score": 8, "reason": "React documentation directly supports learning goal"}},
  {{"id": 2, "score": 2, "reason": "Cat videos are entertainment, not related to React"}}
]

Output ONLY the JSON array, no markdown code blocks, no other text."""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,  # Low temperature for consistent judgments
                )
            )
            
            # Parse the response
            content = response.text.strip()
            
            # Remove markdown code blocks if present
            if content.startswith("```"):
                # Extract content between code blocks
                lines = content.split("\n")
                # Remove first line (```json) and last line (```)
                content = "\n".join(lines[1:-1])
            
            parsed = json.loads(content)
            
            # Handle both array and object responses
            if isinstance(parsed, dict):
                # If wrapped in an object, extract the array
                evaluations = parsed.get("tabs") or parsed.get("evaluations") or list(parsed.values())[0]
            else:
                evaluations = parsed
            
            # Build result lists
            tabs_to_keep = []
            tabs_to_hide = []
            detailed_evaluations = []
            
            # Create a lookup for tab titles
            tab_lookup = {tab["id"]: tab["title"] for tab in tabs}
            
            for eval_item in evaluations:
                tab_id = eval_item.get("id")
                score = eval_item.get("score", 0)
                reason = eval_item.get("reason", "")
                
                if tab_id is None:
                    continue
                
                detailed_evaluations.append({
                    "id": tab_id,
                    "title": tab_lookup.get(tab_id, "Unknown"),
                    "score": score,
                    "reason": reason
                })
                
                if score > self.RELEVANCE_THRESHOLD:
                    tabs_to_keep.append(tab_id)
                else:
                    tabs_to_hide.append(tab_id)
            
            return {
                "tabs_to_keep": tabs_to_keep,
                "tabs_to_hide": tabs_to_hide,
                "evaluations": detailed_evaluations
            }
            
        except json.JSONDecodeError as e:
            print(f"[FocusManager] Failed to parse LLM response: {e}")
            print(f"[FocusManager] Raw response: {content}")
            # Fallback: keep all tabs
            return {
                "tabs_to_keep": [tab["id"] for tab in tabs],
                "tabs_to_hide": [],
                "evaluations": []
            }
        except Exception as e:
            print(f"[FocusManager] Error calling Gemini: {e}")
            # Fallback: keep all tabs
            return {
                "tabs_to_keep": [tab["id"] for tab in tabs],
                "tabs_to_hide": [],
                "evaluations": []
            }
    
    def print_evaluation(self, result: FocusManagerResult):
        """Pretty print the evaluation results."""
        print("\n" + "=" * 60)
        print("🏰 DEEP WORK FORTRESS - Tab Evaluation")
        print("=" * 60)
        
        for eval_item in result["evaluations"]:
            score = eval_item["score"]
            status = "✅ KEEP" if score > self.RELEVANCE_THRESHOLD else "🚫 HIDE"
            bar = "█" * score + "░" * (10 - score)
            
            print(f"\n[{status}] {eval_item['title']}")
            print(f"   Score: [{bar}] {score}/10")
            print(f"   Reason: {eval_item['reason']}")
        
        print("\n" + "-" * 60)
        print(f"📌 Tabs to keep: {result['tabs_to_keep']}")
        print(f"🙈 Tabs to hide: {result['tabs_to_hide']}")
        print("=" * 60 + "\n")


# Singleton for easy import
focus_manager = FocusManager() if os.getenv("GOOGLE_API_KEY") else None


# --- Standalone Test ---
if __name__ == "__main__":
    # Test with dummy data
    dummy_tabs = [
        {"id": 0, "title": "React Hooks Documentation – React", "url": "https://react.dev/reference/react/hooks"},
        {"id": 1, "title": "useState Hook Explained - YouTube", "url": "https://youtube.com/watch?v=O6P86uwfdR0"},
        {"id": 2, "title": "Funny Cat Compilation 2024 - YouTube", "url": "https://youtube.com/watch?v=cats123"},
        {"id": 3, "title": "Stack Overflow - useEffect infinite loop", "url": "https://stackoverflow.com/questions/123456"},
        {"id": 4, "title": "Twitter / X", "url": "https://twitter.com/home"},
        {"id": 5, "title": "Amazon.com: Shopping Cart", "url": "https://amazon.com/cart"},
        {"id": 6, "title": "VS Code - Keyboard Shortcuts", "url": "https://code.visualstudio.com/docs/getstarted/keybindings"},
        {"id": 7, "title": "Reddit - r/reactjs", "url": "https://reddit.com/r/reactjs"},
    ]
    
    test_goal = "Learning React Hooks and building a todo app"
    
    print(f"\n🎯 Current Goal: {test_goal}\n")
    print("Testing FocusManager with dummy tabs...")
    
    try:
        fm = FocusManager()
        result = fm.evaluate_tabs(dummy_tabs, test_goal)
        fm.print_evaluation(result)
    except ValueError as e:
        print(f"Error: {e}")
        print("Make sure GOOGLE_API_KEY is set in your .env file")
