import datetime
import json
import os
from flask import Flask, request, jsonify
import db  # Import the db module from the same folder
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path

# Load .env file from parent directory
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Initialize Flask app
app = Flask(__name__)

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

genai.configure(api_key=GEMINI_API_KEY)

class StateManager:
    def __init__(self, db_path=None):
        """
        Initialize StateManager.
        Args:
            db_path: Optional path to SQLite DB for testing (e.g., ':memory:').
                     If None, uses 'backend/elfrid.db'.
        """
        self.db_path = db_path  # For testing with a different DB path
        
        # Initialize Gemini model
        try:
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        except Exception as e:
            # List available models for debugging
            try:
                models = genai.list_models()
                model_names = [m.name for m in models]
                print(f"Available models: {model_names}")
            except Exception as list_error:
                print(f"Failed to list models: {list_error}")
            raise RuntimeError(f"Failed to initialize Gemini model: {e}")
    
    def get_db(self):
        """
        Get database connection.
        Returns:
            SQLite connection with row_factory set and foreign keys enabled.
        """
        import sqlite3
        conn = sqlite3.connect(self.db_path or 'backend/elfrid.db')
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return conn
    
    def validate_user(self, user_id):
        """Validate that user_id exists in users table."""
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        
        if count == 0:
            raise ValueError(f"User ID {user_id} not found")
        return True
    
    async def call_gemini(self, prompt):
        """
        Call the Gemini API with the given prompt.
        Returns:
            Response text from the API.
        Raises:
            RuntimeError: If the API call fails.
        """
        try:
            response = await self.model.generate_content_async(prompt)
            return response.text
        except Exception as e:
            raise RuntimeError(f"Error calling Gemini API: {e}")
    
    async def process_request(self, user_id, input_text):
        """
        Process a user request through the Elfrid pipeline:
        1. Fetch initial context (config, user, modes, memory, session).
        2. Ask LLM for needed function calls (e.g., get_schedule).
        3. Execute requested queries to gather context.
        4. Generate final response with context.
        5. Log the request and response.
        """
        # Validate user exists
        self.validate_user(user_id)
        
        # Step 1: Fetch Initial Context
        conn = self.get_db()
        cursor = conn.cursor()
        
        # Level 0: Global prompt and user's world model
        cursor.execute("SELECT elfrid_prompt FROM config LIMIT 1")
        elfrid_prompt = cursor.fetchone()["elfrid_prompt"]
        
        cursor.execute("SELECT world_model FROM users WHERE user_id = ?", (user_id,))
        world_model = cursor.fetchone()["world_model"]
        
        # Level 1: Modes and memory tables
        cursor.execute("SELECT mode_name, mode_data FROM modes WHERE user_id = ?", (user_id,))
        modes_rows = cursor.fetchall()
        modes_array = [{"mode_name": row["mode_name"], "mode_data": row["mode_data"]} for row in modes_rows]
        
        cursor.execute("SELECT DISTINCT table_name FROM memory WHERE user_id = ?", (user_id,))
        memory_tables = [row["table_name"] for row in cursor.fetchall()]
        
        # Level 2: Current session
        cursor.execute(
            "SELECT session_id, chat_state FROM sessions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", 
            (user_id,)
        )
        session_row = cursor.fetchone()
        
        if session_row:
            session_id = session_row["session_id"]
            chat_state = session_row["chat_state"]
        else:
            session_id = self.new_session(user_id)
            chat_state = '{}'
        
        # Step 2: Pipeline Step 1 - Ask LLM for needed function calls
        initial_prompt = f"""You are Elfrid, analyzing a request.
Available modes: {json.dumps(modes_array)}.
Memory tables: {json.dumps(memory_tables)}.
Agentic functions: [] (none available yet).
Input: {input_text}.
Do you need more context, modes, or functions to respond? Return only a JSON array of function names needed, e.g., ["get_schedule", "get_nutrition"]. If none, return []."""
        
        needed_functions_response = await self.call_gemini(initial_prompt)
        
        try:
            cleaned_response = needed_functions_response.strip()
            if '```' in cleaned_response:
                code_block = cleaned_response.split('```')[1]
                if code_block.startswith('json'):
                    cleaned_response = code_block[4:].strip()
                else:
                    cleaned_response = code_block.strip()
            
            if cleaned_response.startswith('[') and cleaned_response.endswith(']'):
                json_start = cleaned_response.find('[')
                json_end = cleaned_response.rfind(']') + 1
                cleaned_response = cleaned_response[json_start:json_end]
            
            needed_functions = json.loads(cleaned_response)
            if not isinstance(needed_functions, list):
                raise ValueError("LLM response must be a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error: Invalid LLM response format: {needed_functions_response}")
            raise ValueError(f"LLM response must be a valid JSON array: {e}")
        
        # Step 3: Pipeline Step 2 - Execute requested queries
        context = {}
        
        for function_name in needed_functions:
            if function_name == "get_schedule":
                cursor.execute(
                    "SELECT data FROM memory WHERE user_id = ? AND table_name = 'schedules' LIMIT 1", 
                    (user_id,)
                )
                result = cursor.fetchone()
                if result:
                    context["get_schedule"] = result["data"]
            elif function_name == "get_nutrition":
                cursor.execute(
                    "SELECT data FROM memory WHERE user_id = ? AND table_name = 'nutrition' LIMIT 1", 
                    (user_id,)
                )
                result = cursor.fetchone()
                if result:
                    context["get_nutrition"] = result["data"]
            else:
                print(f"Warning: Unrecognized function call: {function_name}")
        
        # Step 4: Pipeline Step 3 - Final LLM call
        final_prompt = f"""You are Elfrid, defined by: {elfrid_prompt}.
User's world model: {world_model}.
Available modes: {json.dumps(modes_array)}.
Memory tables: {json.dumps(memory_tables)}.
Current session state: {chat_state}.
Additional context: {json.dumps(context)}.
Input: {input_text}.
Respond naturally as a formal, concise butler, choosing the best mode(s) if relevant."""
        
        final_response = await self.call_gemini(final_prompt)
        
        # Step 5: Log request and response
        timestamp = datetime.datetime.now()
        cursor.execute(
            "INSERT INTO logs (user_id, session_id, request, response, timestamp) VALUES (?, ?, ?, ?, ?)",
            (user_id, session_id, input_text, final_response, timestamp)
        )
        conn.commit()
        conn.close()
        
        return final_response
    
    def new_session(self, user_id):
        """Create a new chat session for the user."""
        self.validate_user(user_id)
        
        conn = self.get_db()
        cursor = conn.cursor()
        timestamp = datetime.datetime.now()
        
        cursor.execute(
            "INSERT INTO sessions (user_id, chat_state, timestamp) VALUES (?, ?, ?)",
            (user_id, '{}', timestamp)
        )
        conn.commit()
        
        session_id = cursor.lastrowid
        conn.close()
        
        return session_id

# Flask routes
@app.route('/voice', methods=['POST'])
async def voice():
    """
    Process user voice input.
    Input: { "user_id": int, "input": str }
    Output: { "response": str }
    """
    data = request.json
    
    if not data or "user_id" not in data or "input" not in data:
        return jsonify({"error": "Missing user_id or input"}), 400
    
    user_id = data["user_id"]
    input_text = data["input"]
    
    try:
        state_manager = StateManager()
        response = await state_manager.process_request(user_id, input_text)
        return jsonify({"response": response})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Error processing request: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/new_chat', methods=['POST'])
def new_chat():
    """
    Create a new chat session.
    Input: { "user_id": int }
    Output: { "session_id": int }
    """
    data = request.json
    
    if not data or "user_id" not in data:
        return jsonify({"error": "Missing user_id"}), 400
    
    user_id = data["user_id"]
    
    try:
        state_manager = StateManager()
        session_id = state_manager.new_session(user_id)
        return jsonify({"session_id": session_id})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Error creating new session: {e}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    db.init_db()
    
    import asyncio
    from asgiref.wsgi import WsgiToAsgi
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    
    asgi_app = WsgiToAsgi(app)
    config = Config()
    config.bind = ["localhost:5000"]
    
    asyncio.run(serve(asgi_app, config))