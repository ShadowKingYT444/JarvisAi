import platform

def get_browser_control(browser="chrome"):
    """
    Factory to get the correct BrowserControl for the current running OS.
    Args:
        browser (str): "chrome" or "safari". Defaults to "chrome".
    """
    system = platform.system()
    
    if system == "Windows":
        from .windows.browser_control import WindowsBrowserControl
        return WindowsBrowserControl(browser=browser)
    elif system == "Darwin":  # macOS
        from .darwin.browser_control import MacOSBrowserControl
        return MacOSBrowserControl(browser=browser)
    else:
        raise NotImplementedError(f"Operating System '{system}' is not supported yet.")
