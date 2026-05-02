import os
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from fastapi import FastAPI
from pydantic import BaseModel
import threading
from database import insert_ticket, init_db, free_developer
from services.assignment_service import auto_assign_ticket, process_queue

load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")

app = FastAPI()


# ---------------- INIT ----------------
@app.on_event("startup")
def startup():
    init_db()


# ---------------- BASIC ROUTES ----------------
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


# ---------------- JIRA ----------------
def create_jira_ticket(summary, description):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue"

    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
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
            "issuetype": {"name": "Task"}
        }
    }

    response = requests.post(url, json=payload, headers=headers, auth=auth)

    print(response.status_code)
    print(response.text)

    return response.json()


# ---------------- PARSER ----------------
class ChatRequest(BaseModel):
    message: str


def parse_message(message: str):
    parts = message.split()
    data = {}

    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            data[key] = value

    return data


# ---------------- CHAT WEBHOOK ----------

from fastapi import Request
"""
@app.post("/chat-webhook")
async def chat_webhook(request: Request):
    body = await request.json()

    print("GOOGLE CHAT PAYLOAD:", body)

    message_text = (
        body.get("message", {}).get("text")
        or body.get("text")
        or ""
    )

    if not message_text:
        return {"text": "❌ No message received"}

    # 🔥 background me ticket process hoga
    threading.Thread(target=process_ticket, args=(message_text,)).start()

    # ⚡ instant reply
    return {
        "text": "⏳ Creating ticket..."
    }
"""

@app.post("/chat-webhook")
async def chat_webhook(request: Request):
    return {"text": "🔥 BOT HIT SUCCESS"}

# ---------------- ASSIGN ----------------
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
    conn.close()

    return {"message": "Ticket assigned"}


# ---------------- COMPLETE ----------------
@app.post("/complete-ticket/{ticket_id}")
def complete_ticket(ticket_id: int):
    import sqlite3

    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE tickets
        SET status = 'COMPLETED',
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (ticket_id,))

    conn.commit()
    conn.close()

    free_developer(ticket_id)
    result = process_queue()

    return {
        "message": "Ticket completed",
        "next_assignment": result
    }


# ---------------- RATING ----------------
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


# ---------------- ANALYTICS ----------------
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
        ratings.append(calculate_rating(created, completed, eta))

    return {
        "total_completed": len(ratings),
        "ratings": ratings,
        "avg_rating": sum(ratings)/len(ratings) if ratings else 0
    }


# ---------------- TICKETS ----------------
@app.get("/tickets")
def get_tickets():
    import sqlite3

    conn = sqlite3.connect("tickets.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tickets")

    return {"data": cursor.fetchall()}


# ---------------- DASHBOARD ----------------
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


# ---------------- CHAT SENDER ----------------
def send_chat_message(text):
    WEBHOOK_URL = "https://chat.googleapis.com/v1/spaces/AAQA3VIzjzw/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=L50yQPPgo976zZm77mStypfjsi0_LwG2mitPwguX1jc"

    payload = {"text": text}

    requests.post(WEBHOOK_URL, json=payload)

def process_ticket(message_text):
    parsed = parse_message(message_text)

    client = parsed.get("client")
    issue = parsed.get("issue")
    eta = parsed.get("eta")

    if not all([client, issue, eta]):
        send_chat_message("❌ Invalid format. Use: client=... issue=... eta=...")
        return

    jira_response = create_jira_ticket(
        summary=f"{client}: {issue}",
        description=f"Issue: {issue}, ETA: {eta}"
    )

    jira_id = jira_response.get("key")

    ticket_id = insert_ticket(client, issue, eta, jira_id)
    assignment = auto_assign_ticket(ticket_id)

    send_chat_message(
        f"✅ Ticket Created\nJIRA: {jira_id}\nDev: {assignment.get('dev_id')}"
    )
