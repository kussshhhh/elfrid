import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
import db

env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

BASE_URL = "http://localhost:5000"

def setup_test_data():
    """Initialize the database and insert test data."""
    db.init_db()
    
    conn = db.get_db()
    cursor = conn.cursor()
    
    # User
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, world_model, created_at) VALUES (?, ?, ?)",
        (1, '{"mindset": "athlete"}', datetime.now())
    )
    
    # Modes: physical, work, schedule
    cursor.execute(
        "INSERT OR IGNORE INTO modes (user_id, mode_name, mode_data, last_updated) VALUES (?, ?, ?, ?)",
        (1, 'physical', '{"activities": []}', datetime.now())
    )
    cursor.execute(
        "INSERT OR IGNORE INTO modes (user_id, mode_name, mode_data, last_updated) VALUES (?, ?, ?, ?)",
        (1, 'work', '{"tasks": []}', datetime.now())
    )
    cursor.execute(
        "INSERT OR IGNORE INTO modes (user_id, mode_name, mode_data, last_updated) VALUES (?, ?, ?, ?)",
        (1, 'schedule', '{"events": [{"time": "3 PM", "title": "Team Sync"}]}', datetime.now())
    )
    
    # Memory: nutrition
    cursor.execute(
        "INSERT OR IGNORE INTO memory (user_id, table_name, data, last_updated) VALUES (?, ?, ?, ?)",
        (1, 'nutrition', '{"meals": [{"time": "8 AM", "meal": "Oatmeal", "calories": 200, "protein": 10}], "min_protein": 80}', datetime.now())
    )
    
    conn.commit()
    db.close_db(conn)
    print("Test data inserted successfully.")

def create_session():
    """Create a new chat session for user_id=1."""
    url = f"{BASE_URL}/new_chat"
    payload = {"user_id": 1}
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"New session created: session_id={data['session_id']}")
            return data["session_id"]
        else:
            print(f"Error creating session: Status {response.status_code}, {response.text}")
            return None
    except requests.RequestException as e:
        print(f"Error sending request: {e}")
        return None

def chat_loop(session_id):
    """Run an interactive chat loop with the /voice endpoint."""
    url = f"{BASE_URL}/voice"
    print("\nChat with Elfrid (type 'quit' to exit):")
    
    while True:
        user_input = input("> ")
        if user_input.lower() == 'quit':
            break
        
        payload = {"user_id": 1, "input": user_input}
        try:
            response = requests.post(url, json=payload, timeout=5)
            print(f"Status Code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Elfrid: {data['response'].strip()}")
            else:
                print(f"Error: {response.text}")
        except requests.RequestException as e:
            print(f"Error sending request: {e}")

def cleanup_database():
    """Clean up test data from the database."""
    conn = db.get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM logs WHERE user_id = ?", (1,))
    cursor.execute("DELETE FROM sessions WHERE user_id = ?", (1,))
    cursor.execute("DELETE FROM memory WHERE user_id = ?", (1,))
    cursor.execute("DELETE FROM modes WHERE user_id = ?", (1,))
    cursor.execute("DELETE FROM users WHERE user_id = ?", (1,))
    
    conn.commit()
    db.close_db(conn)
    print("\nTest data cleaned up.")

def main():
    """Run the interactive chat loop."""
    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        exit(1)
    
    if not os.getenv("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY not set in .env")
        exit(1)
    
    setup_test_data()
    session_id = create_session()
    if session_id:
        chat_loop(session_id)
    cleanup_database()
    print("Chat session ended.")

if __name__ == '__main__':
    main()