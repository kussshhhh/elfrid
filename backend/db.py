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

    # Enhanced butler prompt
    enhanced_prompt = """You are Elfrid, a highly sophisticated AI butler with a formal yet warm demeanor. Your purpose is to serve with exceptional attention to detail and anticipate needs before they are expressed. Consider yourself the digital equivalent of a professional household manager.

Your characteristics include:
1. FORMAL PRECISION: Your language is polished and proper without being stiff.
2. CONCISENESS: You provide complete information efficiently without unnecessary elaboration.
3. PROACTIVITY: You anticipate needs based on context rather than asking questions.
4. MEMORY UTILIZATION: You maintain impeccable records of preferences and important information.
5. ADAPTABILITY: You gracefully pivot between different modes of service based on context.

When responding to requests:
- Acknowledge with a brief, formal address
- Provide clear, actionable information
- Take initiative to solve problems without excessive questioning
- Maintain a consistent tone of dignified service"""

    cursor.execute('SELECT COUNT(*) FROM config')
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            'INSERT INTO config (elfrid_prompt, created_at) VALUES (?, ?)',
            (enhanced_prompt, datetime.now())
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

def create_table(table_name, schema):
    """Create a custom table dynamically based on LLM's decision."""
    if not all(c.isalnum() or c == '_' for c in table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    
    # Security check for schema
    if ";" in schema and not schema.strip().endswith(";"):
        raise ValueError("Invalid schema: multiple SQL statements not allowed")
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(schema)
        conn.commit()
        close_db(conn)
        return f"Table '{table_name}' created successfully"
    except sqlite3.Error as e:
        close_db(conn)
        raise ValueError(f"Failed to create table: {e}")

def execute_custom_query(query, params=None):
    """Execute a custom SQL query (read-only for safety)."""
    # Security check - ensure it's a SELECT query
    if not query.strip().lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed through this method")
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
            
        results = [dict(row) for row in cursor.fetchall()]
        close_db(conn)
        return results
    except sqlite3.Error as e:
        close_db(conn)
        raise ValueError(f"Query execution failed: {e}")

def insert_data(table_name, data_dict):
    """Insert data into any table."""
    if not all(c.isalnum() or c == '_' for c in table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    
    if not isinstance(data_dict, dict) or not data_dict:
        raise ValueError("Data must be a non-empty dictionary")
    
    columns = list(data_dict.keys())
    values = list(data_dict.values())
    placeholders = ", ".join(["?"] * len(values))
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
        cursor.execute(query, values)
        row_id = cursor.lastrowid
        conn.commit()
        close_db(conn)
        return f"Data inserted into '{table_name}' with ID {row_id}"
    except sqlite3.Error as e:
        close_db(conn)
        raise ValueError(f"Failed to insert data: {e}")

def update_data(table_name, condition_dict, data_dict):
    """Update data in any table."""
    if not all(c.isalnum() or c == '_' for c in table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    
    if not isinstance(data_dict, dict) or not data_dict:
        raise ValueError("Data must be a non-empty dictionary")
    
    if not isinstance(condition_dict, dict) or not condition_dict:
        raise ValueError("Condition must be a non-empty dictionary")
    
    set_clause = ", ".join([f"{col} = ?" for col in data_dict.keys()])
    where_clause = " AND ".join([f"{col} = ?" for col in condition_dict.keys()])
    
    params = list(data_dict.values()) + list(condition_dict.values())
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        query = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"
        cursor.execute(query, params)
        affected_rows = cursor.rowcount
        conn.commit()
        close_db(conn)
        return f"Updated {affected_rows} rows in '{table_name}'"
    except sqlite3.Error as e:
        close_db(conn)
        raise ValueError(f"Failed to update data: {e}")

def list_tables():
    """List all tables in the database."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row["name"] for row in cursor.fetchall()]
    
    close_db(conn)
    return tables

def get_schema(table_name=None):
    """Get schema information for database tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    schemas = {}
    
    if table_name:
        if not all(c.isalnum() or c == '_' for c in table_name):
            close_db(conn)
            raise ValueError(f"Invalid table name: {table_name}")
            
        cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        result = cursor.fetchone()
        if result:
            schemas[table_name] = result["sql"]
    else:
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
        for row in cursor.fetchall():
            schemas[row["name"]] = row["sql"]
    
    close_db(conn)
    return schemas

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
    
    # Add all database tables to provide full context
    db_tables = list_tables()
    
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
    
    return elfrid_prompt, world_model, modes_array, memory_tables, db_tables, session_id, chat_state

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
    """Execute a query on the memory table."""
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
    """Update or insert data in the modes table for a user."""
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