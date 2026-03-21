import sqlite3
import os
import json
import shutil
import webbrowser
from datetime import datetime, timedelta


def open_website(url: str) -> str:
    """Open a website in the default browser.

    Args:
        url: The URL to open.

    Returns:
        A status message indicating success or failure.
    """
    try:
        webbrowser.open(url)
        return f"Opened {url} in your default browser."
    except Exception as e:
        return f"Failed to open {url}: {e}"

def get_chrome_history(output_file='browser_history.json'):
    """
    Extracts Chrome browsing history from a macOS system and saves it to a JSON file.

    This function locates the Chrome history database, copies it to a temporary
    location to avoid file locking issues, and then queries the database
    to extract browsing history.

    Args:
        output_file (str): The name of the JSON file to save the history to.
    """
    # Path to the Chrome history database on macOS
    history_db_path = os.path.expanduser('~/Library/Application Support/Google/Chrome/Default/History')

    if not os.path.exists(history_db_path):
        print("Error: Chrome history database not found.")
        return

    # To avoid issues with the database being locked by Chrome, we copy it.
    temp_db_path = '/tmp/chrome_history.db'
    shutil.copy2(history_db_path, temp_db_path)

    try:
        # Connect to the copied database
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        # Query to select browsing history
        # last_visit_time is in microseconds since 1601-01-01
        query = "SELECT url, title, visit_count, last_visit_time FROM urls ORDER BY last_visit_time DESC"
        cursor.execute(query)

        history_data = []
        for url, title, visit_count, last_visit_time in cursor.fetchall():
            # Convert the Chrome timestamp to a standard datetime object
            # The epoch for Chrome timestamps is 1601-01-01 UTC
            epoch_start = datetime(1601, 1, 1)
            delta = timedelta(microseconds=last_visit_time)
            # The timestamp is in UTC, so we can represent it as such.
            visit_time = epoch_start + delta

            history_data.append({
                'url': url,
                'title': title,
                'visit_count': visit_count,
                'last_visit_time_utc': visit_time.isoformat() + 'Z'
            })

        # Save the data to a JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, ensure_ascii=False, indent=4)

        print(f"Successfully extracted and saved browser history to {output_file}")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()
        # Clean up the temporary database file
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

if __name__ == '__main__':
    # This allows the script to be run directly from the command line
    get_chrome_history()