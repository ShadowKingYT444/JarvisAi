
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from platforms.darwin.browser_control import MacOSBrowserControl

class TestMacOSBrowserControl(unittest.TestCase):
    
    @patch('subprocess.run')
    def test_get_tabs_parsing(self, mock_run):
        # Mock AppleScript output for get_tabs
        # Output format: window_id|||tab_index|||title|||url
        mock_output = "1|||1|||Google|||https://google.com\n1|||2|||YouTube|||https://youtube.com/watch?v=123"
        
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
        
        browser = MacOSBrowserControl()
        tabs = browser.get_tabs()
        
        self.assertEqual(len(tabs), 2)
        self.assertEqual(tabs[0]['title'], "Google")
        self.assertEqual(tabs[1]['url'], "https://youtube.com/watch?v=123")
        
    @patch('subprocess.run')
    def test_scour_tabs(self, mock_run):
        # 1. Setup mock for get_tabs call
        # We need to handle multiple calls to subprocess.run.
        # First call is get_tabs, subsequent calls are close_tab.
        
        mock_tabs_output = "1|||1|||Safe Site|||https://work.com\n1|||2|||Distraction|||https://instagram.com"
        
        # Configure the side_effect for subprocess.run
        def side_effect(args, **kwargs):
            cmd = args
            if isinstance(args, list): cmd = " ".join(args)
            
            if "count of windows" in cmd or "repeat with w" in cmd:
                # This is the get_tabs script
                return MagicMock(returncode=0, stdout=mock_tabs_output)
            elif "close tab" in cmd:
                # This is close_tab
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=1, stdout="Unknown script")

        mock_run.side_effect = side_effect
        
        browser = MacOSBrowserControl()
        
        # 2. Run scour_tabs
        browser.scour_tabs(["instagram.com"])
        
        # 3. Verify interactions
        # Should have called run twice: once for get_tabs, once for close_tab
        self.assertTrue(mock_run.call_count >= 2)
        
        # Verify close_tab was called for tab 2 (Instagram)
        # Note: close_tab AppleScript: "close tab 2 of window 1"
        found_close_call = False
        for call_args in mock_run.call_args_list:
            args, _ = call_args
            # args[0] is the command list e.g. ["osascript", "-e", script]
            command_list = args[0] 
            if len(command_list) > 2:
                script_arg = command_list[2]
                if "close tab 2 of window 1" in script_arg:
                    found_close_call = True
                    break
                
        self.assertTrue(found_close_call, "Did not attempt to close the distracting tab")

if __name__ == '__main__':
    unittest.main()
