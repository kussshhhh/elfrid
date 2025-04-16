import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
import db
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
import time

# Initialize Rich Console
console = Console()

# Load environment variables
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

BASE_URL = "http://localhost:5000"

def check_server_connection(url, retries=3, delay=2):
    """Check if the Flask server is running."""
    console.print(f"Checking connection to [cyan]{url}[/]...")
    health_url = url.rstrip('/') + "/health" # Ensure correct URL formation
    for i in range(retries):
        try:
            response = requests.get(health_url, timeout=2) # Check the /health endpoint
            response.raise_for_status() # Raise an exception for bad status codes
            if response.json().get("status") == "ok":
                 console.print("[green]Server connection successful![/]")
                 return True
            else:
                 console.print(f"[yellow]Connection attempt {i+1}/{retries} failed. Server responded but status not ok. Retrying in {delay}s...[/]")
                 time.sleep(delay)

        except requests.exceptions.ConnectionError:
            console.print(f"[yellow]Connection attempt {i+1}/{retries} failed. Server not reachable. Retrying in {delay}s...[/]")
            time.sleep(delay)
        except requests.exceptions.Timeout:
            console.print(f"[yellow]Connection attempt {i+1}/{retries} timed out. Retrying in {delay}s...[/]")
            time.sleep(delay)
        except requests.exceptions.RequestException as e:
            console.print(f"[red]An error occurred during connection check: {e}[/]")
            return False # Non-recoverable error
    console.print("[red]Server connection failed after multiple attempts.[/]")
    return False

def create_session():
    """Create a new chat session for user_id=1."""
    url = f"{BASE_URL}/new_chat"
    payload = {"user_id": 1}
    console.print("Creating new session...")
    try:
        response = requests.post(url, json=payload, timeout=10) # Increased timeout
        if response.status_code == 200:
            data = response.json()
            console.print(f"[green]New session created: session_id={data['session_id']}[/]")
            return data["session_id"]
        else:
            console.print(f"[red]Error creating session: Status {response.status_code}, {response.text}[/]")
            return None
    except requests.RequestException as e:
        console.print(f"[red]Error sending request to create session: {e}[/]")
        return None

def chat_loop(session_id):
    """Run an interactive chat loop with the /voice endpoint using Rich."""
    url = f"{BASE_URL}/voice"
    console.print("\n[bold blue]Chat with Elfrid[/] (type '[italic red]quit[/]' to exit):")

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]> [/]")
            if user_input.lower() == 'quit':
                break

            payload = {"user_id": 1, "input": user_input}
            try:
                response = requests.post(url, json=payload, timeout=30) # Increased timeout for potentially long LLM calls
                # console.print(f"Status Code: {response.status_code}") # Optional: for debugging
                if response.status_code == 200:
                    data = response.json()
                    # Use Panel for Elfrid's response
                    console.print(Panel(data['response'].strip(), title="[bold magenta]Elfrid[/]", border_style="magenta"))
                else:
                    console.print(Panel(f"Error: {response.text}", title="[bold red]Error[/]", border_style="red"))
            except requests.exceptions.Timeout:
                 console.print(Panel("Request timed out. The server might be busy.", title="[bold red]Timeout[/]", border_style="red"))
            except requests.RequestException as e:
                console.print(Panel(f"Error sending request: {e}", title="[bold red]Request Error[/]", border_style="red"))

        except EOFError: # Handle Ctrl+D
             console.print("\n[yellow]Exiting chat.[/]")
             break
        except KeyboardInterrupt: # Handle Ctrl+C
             console.print("\n[yellow]Exiting chat.[/]")
             break

def cleanup_database():
    """Clean up test data from the database."""
    console.print("\nCleaning up test data...")
    conn = db.get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM logs WHERE user_id = ?", (1,))
    cursor.execute("DELETE FROM sessions WHERE user_id = ?", (1,))
    cursor.execute("DELETE FROM memory WHERE user_id = ?", (1,))
    cursor.execute("DELETE FROM modes WHERE user_id = ?", (1,))
    cursor.execute("DELETE FROM users WHERE user_id = ?", (1,))

    conn.commit()
    db.close_db(conn)
    console.print("[green]Test data cleaned up.[/]")

def main():
    """Run the interactive chat loop."""
    if not env_path.exists():
        console.print(f"[bold red]Error:[/].env file not found at {env_path}")
        exit(1)

    if not os.getenv("GEMINI_API_KEY"):
        console.print("[bold red]Error:[/][yellow] GEMINI_API_KEY not set in .env[/]")
        exit(1)

    # Check server connection first
    if not check_server_connection(BASE_URL):
        console.print("[bold red]Exiting:[/][yellow] Cannot connect to the backend server.[/]")
        exit(1)

    # No database initialization here - app.py already does this
    
    session_id = create_session()
    if session_id:
        chat_loop(session_id)
        # Don't clean up data to ensure persistence
    else:
        console.print("[red]Failed to start chat session.[/]")

    console.print("[bold blue]Chat session ended.[/]")

if __name__ == '__main__':
    main()