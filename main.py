import os
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from fastapi import FastAPI
from database import insert_ticket
from pydantic import BaseModel
# from database import insert_ticket, auto_assign_ticket, init_db
from services.assignment_service import auto_assign_ticket, process_queue
from database import insert_ticket, init_db, free_developer

load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")

app = FastAPI()

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def home():
    return {"message": "Server is running"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/test-jira")
def test_jira():
    result = create_jira_ticket("Test API Ticket", "Created from FastAPI")
    return result

def create_jira_ticket(summary, description):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue"

    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    payload = {
        "fields": {
            "project": {
                "key": JIRA_PROJECT_KEY
            },
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": description
                            }
                        ]
                    }
                ]
            },
            "issuetype": {
                "name": "Task"
            }
        }
    }

    response = requests.post(url, json=payload, headers=headers, auth=auth)

    print(response.status_code)
    print(response.text)

    return response.json()

class ChatRequest(BaseModel):
    message: str

def parse_message(message: str):
    parts = message.split()

    data = {}
    for part in parts:
        if "=" in part:
            key, value = part.split("=")
            data[key] = value

    return data

@app.post("/chat-webhook")
def chat_webhook(req: ChatRequest):
    parsed = parse_message(req.message)

    client = parsed.get("client")
    issue = parsed.get("issue")
    eta = parsed.get("eta")

    jira_response = create_jira_ticket(
        summary=f"{client}: {issue}",
        description=f"Issue: {issue}, ETA: {eta}"
    )

    jira_id = jira_response.get("key")

    # DB me save
    # insert_ticket(client, issue, eta, jira_id)
    ticket_id = insert_ticket(client, issue, eta, jira_id)
    assignment = auto_assign_ticket(ticket_id)

    return {
        "message": "Ticket created",
        "jira_ticket": jira_id,
        "assignment": assignment
    }

@app.post("/assign-ticket/{ticket_id}")
def assign_ticket(ticket_id: int):
    import sqlite3
    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE tickets
    SET status = 'ASSIGNED',
        assigned_at = CURRENT_TIMESTAMP
    WHERE id = ?
    """, (ticket_id,))

    conn.commit()

    return {"message": "Ticket assigned"}


@app.post("/complete-ticket/{ticket_id}")
def complete_ticket(ticket_id: int):
    import sqlite3
    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()

    # 1. mark ticket completed
    cursor.execute("""
    UPDATE tickets
    SET status = 'COMPLETED',
        completed_at = CURRENT_TIMESTAMP
    WHERE id = ?
    """, (ticket_id,))

    conn.commit()
    conn.close()

    # 2. free developer
    free_developer(ticket_id)

    # 3. process queue
    result = process_queue()

    return {
        "message": "Ticket completed",
        "next_assignment": result
    }

def calculate_rating(created_at, completed_at, eta):
    from datetime import datetime

    fmt = "%Y-%m-%d %H:%M:%S"

    created = datetime.strptime(created_at, fmt)
    completed = datetime.strptime(completed_at, fmt)

    actual_time = (completed - created).total_seconds() / 3600

    eta_hours = float(eta.replace("d", "")) * 24

    if actual_time <= eta_hours:
        return 5
    elif actual_time <= eta_hours * 1.5:
        return 3
    else:
        return 1

@app.get("/analytics")
def analytics():
    import sqlite3
    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT created_at, completed_at, eta
    FROM tickets
    WHERE status = 'COMPLETED'
    """)

    data = cursor.fetchall()

    ratings = []
    for row in data:
        created, completed, eta = row
        rating = calculate_rating(created, completed, eta)
        ratings.append(rating)

    return {
        "total_completed": len(ratings),
        "ratings": ratings,
        "avg_rating": sum(ratings)/len(ratings) if ratings else 0
    }

@app.get("/tickets")
def get_tickets():
    import sqlite3
    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tickets")
    return {"data": cursor.fetchall()}

@app.get("/dashboard")
def dashboard():
    import sqlite3
    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()

    cursor.execute("SELECT status, COUNT(*) FROM tickets GROUP BY status")
    ticket_stats = cursor.fetchall()

    cursor.execute("SELECT name, status FROM developers")
    devs = cursor.fetchall()

    return {
        "tickets": ticket_stats,
        "developers": devs
    }
