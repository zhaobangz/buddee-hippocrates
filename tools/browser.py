# tools/browser.py
import webbrowser

def open_website(url="https://www.google.com"):
    try:
        webbrowser.open(url)
        return f"Opened {url}"
    except Exception as e:
        return f"Failed to open website: {str(e)}"