import json
import sqlite3
from datetime import datetime

def init_db():
    """Initialize the SQLite database 'elfrid.db' with required tables and default config."""
    conn = sqlite3.connect('backend/elfrid.db')
    cursor = conn.cursor()
    cursor.execute('PRAGMA foreign_keys = ON')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY,
            elfrid_prompt TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            world_model TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS modes (
            mode_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            mode_name TEXT NOT NULL,
            mode_data TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory (
            memory_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            table_name TEXT NOT NULL,
            data TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            chat_state TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            log_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            request TEXT NOT NULL,
            response TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
    ''')

    cursor.execute('SELECT COUNT(*) FROM config')
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            'INSERT INTO config (elfrid_prompt, created_at) VALUES (?, ?)',
            ("You are Elfrid, a formal and concise AI butler.", datetime.now())
        )

    conn.commit()
    conn.close()

def get_db():
    """Get a database connection to 'elfrid.db'."""
    conn = sqlite3.connect('backend/elfrid.db')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def close_db(conn):
    """Close the database connection."""
    conn.close()

def validate_user(user_id):
    """Validate that user_id exists in users table."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    close_db(conn)
    
    if count == 0:
        raise ValueError(f"User ID {user_id} not found")
    return True

def new_session(user_id):
    """Create a new chat session for the user."""
    validate_user(user_id)
    
    conn = get_db()
    cursor = conn.cursor()
    timestamp = datetime.now()
    
    cursor.execute(
        "INSERT INTO sessions (user_id, chat_state, timestamp) VALUES (?, ?, ?)",
        (user_id, '{}', timestamp)
    )
    conn.commit()
    
    session_id = cursor.lastrowid
    close_db(conn)
    
    return session_id

def get_context(user_id):
    """Fetch context for a user request."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT elfrid_prompt FROM config LIMIT 1")
    elfrid_prompt = cursor.fetchone()["elfrid_prompt"]
    
    cursor.execute("SELECT world_model FROM users WHERE user_id = ?", (user_id,))
    world_model = cursor.fetchone()["world_model"]
    
    cursor.execute("SELECT mode_name, mode_data FROM modes WHERE user_id = ?", (user_id,))
    modes_rows = cursor.fetchall()
    modes_array = [{"mode_name": row["mode_name"], "mode_data": row["mode_data"]} for row in modes_rows]
    
    cursor.execute("SELECT DISTINCT table_name FROM memory WHERE user_id = ?", (user_id,))
    memory_tables = [row["table_name"] for row in cursor.fetchall()]
    
    cursor.execute(
        "SELECT session_id, chat_state FROM sessions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
        (user_id,)
    )
    session_row = cursor.fetchone()
    
    if session_row:
        session_id = session_row["session_id"]
        chat_state = session_row["chat_state"]
    else:
        session_id = new_session(user_id)
        chat_state = '{}'
    
    close_db(conn)
    
    return elfrid_prompt, world_model, modes_array, memory_tables, session_id, chat_state

def get_session_logs(session_id):
    """Fetch all logs for a given session_id."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT request, response FROM logs WHERE session_id = ? ORDER BY timestamp",
        (session_id,)
    )
    logs = [{"request": row["request"], "response": row["response"]} for row in cursor.fetchall()]
    
    close_db(conn)
    return logs

def execute_query(user_id, action, table_name, data=None):
    """
    Execute a query on the memory table.
    Args:
        user_id: Integer ID of the user.
        action: String, either 'read' or 'update'.
        table_name: String name of the memory table (e.g., 'nutrition').
        data: String JSON data for updates (optional).
    Returns:
        For 'read': Query result (string) or None if not found.
        For 'update': None (updates the DB).
    """
    validate_user(user_id)
    conn = get_db()
    cursor = conn.cursor()
    
    if action == "read":
        cursor.execute(
            "SELECT data FROM memory WHERE user_id = ? AND table_name = ? LIMIT 1",
            (user_id, table_name)
        )
        row = cursor.fetchone()
        close_db(conn)
        return row["data"] if row else None
    elif action == "update":
        if not data:
            close_db(conn)
            raise ValueError("Data required for update action")
        try:
            json.loads(data)  # Validate JSON
            cursor.execute(
                "SELECT memory_id FROM memory WHERE user_id = ? AND table_name = ?",
                (user_id, table_name)
            )
            row = cursor.fetchone()
            timestamp = datetime.now()
            if row:
                cursor.execute(
                    "UPDATE memory SET data = ?, last_updated = ? WHERE memory_id = ?",
                    (data, timestamp, row["memory_id"])
                )
            else:
                cursor.execute(
                    "INSERT INTO memory (user_id, table_name, data, last_updated) VALUES (?, ?, ?, ?)",
                    (user_id, table_name, data, timestamp)
                )
            conn.commit()
        except json.JSONDecodeError:
            close_db(conn)
            raise ValueError("Invalid JSON data for update")
        close_db(conn)
        return None
    else:
        close_db(conn)
        raise ValueError("Invalid action: must be 'read' or 'update'")

def update_mode(user_id, mode_name, new_data):
    """
    Update or insert data in the modes table for a user.
    Args:
        user_id: Integer ID of the user.
        mode_name: String name of the mode (e.g., 'schedule').
        new_data: String JSON data to store.
    """
    validate_user(user_id)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT mode_id FROM modes WHERE user_id = ? AND mode_name = ?",
        (user_id, mode_name)
    )
    row = cursor.fetchone()
    
    timestamp = datetime.now()
    if row:
        cursor.execute(
            "UPDATE modes SET mode_data = ?, last_updated = ? WHERE mode_id = ?",
            (new_data, timestamp, row["mode_id"])
        )
    else:
        cursor.execute(
            "INSERT INTO modes (user_id, mode_name, mode_data, last_updated) VALUES (?, ?, ?, ?)",
            (user_id, mode_name, new_data, timestamp)
        )
    
    conn.commit()
    close_db(conn)

def log_interaction(user_id, session_id, request_text, response_text):
    """Log a request-response pair to the logs table."""
    conn = get_db()
    cursor = conn.cursor()
    timestamp = datetime.now()
    
    cursor.execute(
        "INSERT INTO logs (user_id, session_id, request, response, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, session_id, request_text, response_text, timestamp)
    )
    conn.commit()
    close_db(conn)