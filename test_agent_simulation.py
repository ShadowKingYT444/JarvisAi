"""
Test simulation for Jarvis Agent
Tests various tab configurations and commands without actual voice input.
"""

import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Simulated tab configurations
TEST_CONFIGS = {
    "mixed_tabs": [
        {"id": 0, "title": "GitHub - Project", "url": "https://github.com/user/project"},
        {"id": 1, "title": "YouTube - Music", "url": "https://youtube.com/watch?v=123"},
        {"id": 2, "title": "Google Docs - Notes", "url": "https://docs.google.com/doc/123"},
        {"id": 3, "title": "Instagram", "url": "https://instagram.com"},
        {"id": 4, "title": "Stack Overflow - Python", "url": "https://stackoverflow.com/q/123"},
    ],
    "all_productive": [
        {"id": 0, "title": "VS Code Docs", "url": "https://code.visualstudio.com/docs"},
        {"id": 1, "title": "GitHub", "url": "https://github.com"},
        {"id": 2, "title": "Google Docs", "url": "https://docs.google.com"},
    ],
    "all_distracting": [
        {"id": 0, "title": "YouTube", "url": "https://youtube.com"},
        {"id": 1, "title": "Netflix", "url": "https://netflix.com"},
        {"id": 2, "title": "Instagram", "url": "https://instagram.com"},
        {"id": 3, "title": "Reddit", "url": "https://reddit.com"},
    ],
    "work_context": [
        {"id": 0, "title": "Gmail - Inbox", "url": "https://mail.google.com"},
        {"id": 1, "title": "Google Calendar", "url": "https://calendar.google.com"},
        {"id": 2, "title": "Slack", "url": "https://slack.com"},
        {"id": 3, "title": "Notion - Tasks", "url": "https://notion.so"},
        {"id": 4, "title": "Twitter", "url": "https://twitter.com"},
    ],
}

TEST_COMMANDS = [
    # Simple commands
    ("open gmail", "Should open gmail"),
    ("close youtube", "Should close youtube tab"),
    ("switch to github", "Should switch to github"),
    ("focus on coding", "Should enable focus mode"),
    ("break time", "Should disable focus mode"),
    ("back to work", "Should re-enable focus mode"),
    ("status", "Should report status"),
    ("restore tabs", "Should restore closed tabs"),
    
    # Complex multi-action commands
    ("open google docs and close instagram", "Should do both actions"),
    ("switch to gmail and close youtube", "Should switch then close"),
    ("focus on python and open stackoverflow", "Should focus then open"),
    ("close twitter, close reddit, open github", "Should close 2 and open 1"),
]


def test_intent_parsing():
    """Test the intent parser with various commands."""
    print("\n" + "="*60)
    print("🧪 INTENT PARSING TEST")
    print("="*60)
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ Missing GOOGLE_API_KEY")
        return
    
    client = genai.Client(api_key=api_key)
    model = "gemini-2.0-flash"
    
    results = []
    
    for command, expected in TEST_COMMANDS:
        print(f"\n📢 Command: \"{command}\"")
        print(f"   Expected: {expected}")
        
        prompt = f"""Parse: "{command}"

Actions: focus, switch, open, close, restore, pause_monitor (break time), resume_monitor (back to work), status, scan

Return JSON array:
[{{"action":"open","target":"gmail"}},{{"action":"close","target":"youtube"}}]

Examples:
"open docs and close youtube" -> [{{"action":"open","target":"google docs"}},{{"action":"close","target":"youtube"}}]
"focus on coding" -> [{{"action":"focus","target":"coding"}}]
"break time" -> [{{"action":"pause_monitor"}}]
"go to github" -> [{{"action":"switch","target":"github"}}]

JSON only:"""
        
        try:
            import time
            start = time.time()
            
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            
            elapsed = time.time() - start
            text = response.text.strip()
            
            # Parse JSON
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:-1])
            
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                parsed = [parsed]
            
            print(f"   ✅ Parsed in {elapsed:.2f}s: {parsed}")
            results.append({
                "command": command,
                "actions": len(parsed),
                "time": elapsed,
                "success": True
            })
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append({
                "command": command,
                "error": str(e),
                "success": False
            })
    
    # Summary
    print("\n" + "="*60)
    print("📊 RESULTS SUMMARY")
    print("="*60)
    
    successful = [r for r in results if r.get("success")]
    avg_time = sum(r["time"] for r in successful) / len(successful) if successful else 0
    
    print(f"   Total tests: {len(results)}")
    print(f"   Successful: {len(successful)}")
    print(f"   Failed: {len(results) - len(successful)}")
    print(f"   Avg response time: {avg_time:.2f}s")
    
    return results


def test_distraction_detection():
    """Test distraction detection logic."""
    print("\n" + "="*60)
    print("🧪 DISTRACTION DETECTION TEST")
    print("="*60)
    
    DISTRACTION_PATTERNS = [
        "youtube.com", "netflix.com", "instagram.com", "twitter.com",
        "reddit.com", "tiktok.com", "facebook.com", "discord.com"
    ]
    
    PRODUCTIVITY_PATTERNS = [
        "github.com", "stackoverflow.com", "docs.google.com",
        "mail.google.com", "notion.so", "figma.com"
    ]
    
    def is_distraction(url, title, goal="coding"):
        url_lower = url.lower()
        title_lower = title.lower()
        goal_lower = goal.lower()
        
        # Goal match
        for keyword in goal_lower.split():
            if len(keyword) > 3 and (keyword in url_lower or keyword in title_lower):
                return False
        
        # Productivity match
        for pattern in PRODUCTIVITY_PATTERNS:
            if pattern in url_lower:
                return False
        
        # Distraction match
        for pattern in DISTRACTION_PATTERNS:
            if pattern in url_lower:
                return True
        
        return False
    
    for config_name, tabs in TEST_CONFIGS.items():
        print(f"\n📑 Config: {config_name}")
        
        distractions = 0
        for tab in tabs:
            is_dist = is_distraction(tab["url"], tab["title"])
            status = "🚫 DISTRACTION" if is_dist else "✅ OK"
            print(f"   [{tab['id']}] {status}: {tab['title'][:30]}")
            if is_dist:
                distractions += 1
        
        print(f"   Summary: {distractions}/{len(tabs)} distractions")


def test_url_resolution():
    """Test URL resolution for common site names."""
    print("\n" + "="*60)
    print("🧪 URL RESOLUTION TEST")
    print("="*60)
    
    SITE_URLS = {
        "gmail": "https://mail.google.com",
        "email": "https://mail.google.com",
        "google docs": "https://docs.google.com",
        "docs": "https://docs.google.com",
        "github": "https://github.com",
        "youtube": "https://youtube.com",
        "calendar": "https://calendar.google.com",
    }
    
    test_inputs = [
        "gmail", "google docs", "github", "youtube",
        "docs", "email", "calendar", "linkedin.com",
        "random site", "my project"
    ]
    
    for inp in test_inputs:
        inp_lower = inp.lower().strip()
        
        if inp_lower in SITE_URLS:
            url = SITE_URLS[inp_lower]
        elif "." in inp:
            url = f"https://{inp}"
        else:
            # Partial match
            matched = None
            for name, site_url in SITE_URLS.items():
                if inp_lower in name:
                    matched = site_url
                    break
            url = matched or f"https://{inp_lower.replace(' ', '')}.com"
        
        print(f"   \"{inp}\" → {url}")


def run_all_tests():
    """Run all tests."""
    print("\n" + "🤖"*30)
    print("   JARVIS AGENT TEST SIMULATION")
    print("🤖"*30)
    
    test_url_resolution()
    test_distraction_detection()
    test_intent_parsing()
    
    print("\n✅ All tests complete!")


if __name__ == "__main__":
    run_all_tests()

