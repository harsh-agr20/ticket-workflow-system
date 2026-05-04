import os
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from fastapi import FastAPI, Request

from database import insert_ticket, init_db
from services.assignment_service import auto_assign_ticket

load_dotenv()

# ---------------- ENV ----------------
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

    print("JIRA STATUS:", response.status_code)
    print("JIRA RESPONSE:", response.text)

    return response.json()

# ---------------- PARSER ----------------
def parse_message(message: str):
    parts = message.split()
    data = {}

    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            data[key] = value.strip()

    return data

# ---------------- CHAT WEBHOOK ----------------
@app.post("/chat-webhook")
async def chat_webhook(request: Request):
    body = await request.json()

    print("GOOGLE CHAT PAYLOAD:", body)

    chat_data = body.get("chat", {})

    # ✅ IMPORTANT: argumentText use karo (mention remove ho jayega)
    message_text = (
        chat_data.get("message", {}).get("argumentText")
        or chat_data.get("messagePayload", {}).get("message", {}).get("argumentText")
        or chat_data.get("messagePayload", {}).get("message", {}).get("text")
    )

    if not message_text:
        return {"text": "❌ No message received"}

    parsed = parse_message(message_text)

    client = parsed.get("client")
    issue = parsed.get("issue")
    eta = parsed.get("eta")

    if not all([client, issue, eta]):
        return {"text": "❌ Format: client=... issue=... eta=..."}

    # ✅ Create Jira Ticket
    jira_response = create_jira_ticket(
        summary=f"{client}: {issue}",
        description=f"Issue: {issue}, ETA: {eta}"
    )

    jira_id = jira_response.get("key", "N/A")

    # ✅ Save + Auto Assign
    ticket_id = insert_ticket(client, issue, eta, jira_id)
    assignment = auto_assign_ticket(ticket_id)

    dev_id = assignment.get("dev_id")

    # ✅ FINAL RESPONSE (ONLY TEXT → guaranteed working)
    response = {
        "text": f"""✅ Ticket Created
JIRA: {jira_id}
Assigned Dev: {dev_id}
Client: {client}
Issue: {issue}
ETA: {eta}
"""
    }

    print("FINAL RESPONSE:", response)

    return response
