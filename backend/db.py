"""
Database module for Elfrid AI butler app.
This module handles SQLite database initialization, schema creation, and provides the basic
setup for the Elfrid backend storage system.
"""

import sqlite3
import json
import os
from datetime import datetime

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'elfrid.db')

def get_db_connection():
    """Create and return a database connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """
    Initialize the database.
    Creates all tables if they don't exist and adds default config.
    This function is idempotent - can be run multiple times safely.
    """
    conn = get_db_connection()
    
    # Create tables
    conn.executescript('''
        -- Global configuration table (no user_id as it's global)
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY,
            elfrid_prompt TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Users table
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            world_model TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Modes table
        CREATE TABLE IF NOT EXISTS modes (
            mode_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            mode_name TEXT NOT NULL,
            mode_data TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        
        -- Memory table
        CREATE TABLE IF NOT EXISTS memory (
            memory_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            table_name TEXT NOT NULL,
            data TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        
        -- Sessions table
        CREATE TABLE IF NOT EXISTS sessions (
            session_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            chat_state TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        
        -- Logs table
        CREATE TABLE IF NOT EXISTS logs (
            log_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            request TEXT NOT NULL,
            response TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );
    ''')
    
    # Insert default config row if it doesn't exist
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM config")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO config (elfrid_prompt) VALUES (?)",
            ("You are Elfrid, a formal and concise AI butler.",)
        )
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    # This allows running the script directly to initialize the database
    init_db()
    print(f"Database initialized at {DB_PATH}")