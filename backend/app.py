import json
import os
from flask import Flask, request, jsonify
import db
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path
from agents import get_time  

env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

genai.configure(api_key=GEMINI_API_KEY)

class StateManager:
    def __init__(self):
        """Initialize StateManager with Gemini model."""
        try:
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        except Exception as e:
            try:
                models = genai.list_models()
                model_names = [m.name for m in models]
                print(f"Available models: {model_names}")
            except Exception as list_error:
                print(f"Failed to list models: {list_error}")
            raise RuntimeError(f"Failed to initialize Gemini model: {e}")
    
    async def call_gemini(self, prompt):
        """Call the Gemini API with the given prompt."""
        try:
            response = await self.model.generate_content_async(prompt)
            return response.text
        except Exception as e:
            raise RuntimeError(f"Error calling Gemini API: {e}")
    
    async def process_request(self, user_id, input_text):
        """
        Process a user request through the enhanced Elfrid pipeline with full DB control.
        """
        db.validate_user(user_id)
        elfrid_prompt, world_model, modes_array, memory_tables, db_tables, session_id, chat_state = db.get_context(user_id)
        session_logs = db.get_session_logs(session_id)
        
        # Define available database actions
        db_actions = [
            "create_table", 
            "list_tables", 
            "get_schema",
            "execute_query", 
            "insert_data",
            "update_data"
        ]
        
        # Define available agents
        available_agents = ["get_time"]
        
        # Step 1: Ask LLM for actions with enhanced DB capabilities
        initial_prompt = f"""You are Elfrid, a butler AI analyzing a request.
Available modes: {json.dumps(modes_array)}.
Memory tables: {json.dumps(memory_tables)}.
Database tables: {json.dumps(db_tables)}.
Available database actions: {json.dumps(db_actions)}.
Available agents: {json.dumps(available_agents)}.
Session history: {json.dumps(session_logs)}.
Input: {input_text}.

Return a JSON array of actions. Each action is an object:
1. For memory operations:
   - Read: {{"action": "read", "type": "memory", "table_name": str}}
   - Update: {{"action": "update", "type": "memory", "table_name": str, "data": JSON string}}

2. For mode operations:
   - Read: {{"action": "read", "type": "mode", "table_name": str}}
   - Update: {{"action": "update", "type": "mode", "table_name": str, "data": JSON string}}

3. For database operations:
   - Create table: {{"action": "create_table", "table_name": str, "schema": SQL schema string}}
   - List tables: {{"action": "list_tables"}}
   - Get schema: {{"action": "get_schema", "table_name": str (optional)}}
   - Query data: {{"action": "execute_query", "query": SELECT query string}}
   - Insert data: {{"action": "insert_data", "table_name": str, "data": {{"column": "value"}} dict}}
   - Update data: {{"action": "update_data", "table_name": str, "condition": {{"column": "value"}}, "data": {{"column": "value"}}}}

4. For agents:
   - Call agent: {{"action": "call", "type": "agent", "agent_name": str}}

Think carefully about what data structures you need to fulfill the user's request efficiently.
Create tables, insert, or update data as needed to best serve the user.
Be decisive - take action to solve the user's need without excessive questioning. when ask you something and expect you to know chances are they are in the db so run all the queries and find that info from the db and then respond, 
Return [] if no actions needed.
"""
        
        actions_response = await self.call_gemini(initial_prompt)
        
        try:
            cleaned_response = actions_response.strip()
            if '```' in cleaned_response:
                code_block = cleaned_response.split('```')[1]
                if code_block.startswith('json'):
                    cleaned_response = code_block[4:].strip()
                else:
                    cleaned_response = code_block.strip()
            
            actions = json.loads(cleaned_response)
            if not isinstance(actions, list):
                raise ValueError("LLM response must be a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error: Invalid LLM actions response: {actions_response}")
            raise ValueError(f"LLM actions response must be valid JSON array: {e}")
        
        # Step 2: Process actions
        context = {}
        for action in actions:
            action_type = action.get("action")
            table_type = action.get("type", "")
            table_name = action.get("table_name", "")
            agent_name = action.get("agent_name", "")
            data = action.get("data", "")
            
            # Process original memory/mode actions
            if action_type == "read" and table_type in ["memory", "mode"]:
                if table_type == "memory":
                    result = db.execute_query(user_id, "read", table_name)
                    if result:
                        context[f"memory_{table_name}"] = result
                elif table_type == "mode":
                    conn = db.get_db()
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT mode_data FROM modes WHERE user_id = ? AND mode_name = ?",
                        (user_id, table_name)
                    )
                    row = cursor.fetchone()
                    db.close_db(conn)
                    if row:
                        context[f"mode_{table_name}"] = row["mode_data"]
            
            elif action_type == "update" and table_type in ["memory", "mode"]:
                if table_type == "memory":
                    try:
                        db.execute_query(user_id, "update", table_name, data)
                        context[f"update_memory_{table_name}"] = f"Updated {table_name} successfully."
                    except ValueError as e:
                        context[f"update_memory_{table_name}"] = str(e)
                elif table_type == "mode":
                    try:
                        json.loads(data)
                        db.update_mode(user_id, table_name, data)
                        context[f"update_mode_{table_name}"] = f"Updated {table_name} mode successfully."
                    except json.JSONDecodeError:
                        context[f"update_mode_{table_name}"] = "Invalid JSON data for mode update"
            
            # Process new database control actions
            elif action_type == "create_table":
                try:
                    schema = action.get("schema")
                    result = db.create_table(table_name, schema)
                    context[f"create_table_{table_name}"] = result
                except ValueError as e:
                    context[f"create_table_{table_name}"] = str(e)
            
            elif action_type == "list_tables":
                try:
                    tables = db.list_tables()
                    context["list_tables"] = tables
                except Exception as e:
                    context["list_tables"] = str(e)
            
            elif action_type == "get_schema":
                try:
                    if table_name:
                        schema = db.get_schema(table_name)
                        context[f"schema_{table_name}"] = schema
                    else:
                        schemas = db.get_schema()
                        context["all_schemas"] = schemas
                except ValueError as e:
                    context[f"schema_error"] = str(e)
            
            elif action_type == "execute_query":
                try:
                    query = action.get("query")
                    results = db.execute_custom_query(query)
                    context["query_results"] = results
                except ValueError as e:
                    context["query_error"] = str(e)
            
            elif action_type == "insert_data":
                try:
                    data_dict = action.get("data")
                    result = db.insert_data(table_name, data_dict)
                    context[f"insert_{table_name}"] = result
                except ValueError as e:
                    context[f"insert_error_{table_name}"] = str(e)
            
            elif action_type == "update_data":
                try:
                    condition_dict = action.get("condition")
                    data_dict = action.get("data")
                    result = db.update_data(table_name, condition_dict, data_dict)
                    context[f"update_{table_name}"] = result
                except ValueError as e:
                    context[f"update_error_{table_name}"] = str(e)
            
            elif action_type == "call" and table_type == "agent":
                if agent_name == "get_time":
                    result = get_time.get_time()
                    context[f"agent_{agent_name}"] = result
                else:
                    context[f"agent_{agent_name}"] = f"Unknown agent: {agent_name}"
        
        # Get updated list of tables after any changes
        updated_tables = db.list_tables()
        
        # Step 3: Generate final response
        final_prompt = f"""You are Elfrid, defined by: {elfrid_prompt}.
User's world model: {world_model}.
Available modes: {json.dumps(modes_array)}.
Memory tables: {json.dumps(memory_tables)}.
Database tables: {json.dumps(updated_tables)}.
Current session state: {chat_state}.
Session history: {json.dumps(session_logs)}.
Additional context from actions: {json.dumps(context)}.
User request: {input_text}

Respond naturally as a formal, concise butler. Be proactive - anticipate user needs rather than asking questions. 
Use your database knowledge to provide personalized service.
Don't mention technical details about database operations unless specifically relevant to the user.
Focus on solving the user's request efficiently and completely.
"""
        
        final_response = await self.call_gemini(final_prompt)
        
        # Step 4: Log interaction
        db.log_interaction(user_id, session_id, input_text, final_response)
        
        return final_response

# Flask routes
@app.route('/voice', methods=['POST'])
async def voice():
    """Process user voice input."""
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
    """Create a new chat session."""
    data = request.json
    
    if not data or "user_id" not in data:
        return jsonify({"error": "Missing user_id"}), 400
    
    user_id = data["user_id"]
    
    try:
        session_id = db.new_session(user_id)
        return jsonify({"session_id": session_id})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Error creating new session: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({"status": "ok"}), 200

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
