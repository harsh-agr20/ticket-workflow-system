import sqlite3

DB_NAME = "tickets.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


# -------------------------
# TICKETS TABLE
# -------------------------
def create_ticket_table():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client TEXT,
        issue TEXT,
        eta TEXT,
        jira_ticket_id TEXT,
        status TEXT DEFAULT 'OPEN',
        assigned_at TIMESTAMP,
        completed_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


# -------------------------
# DEVELOPERS TABLE
# -------------------------
def create_developer_table():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS developers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        status TEXT DEFAULT 'FREE',
        current_ticket_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


# -------------------------
# SEED DEVELOPERS
# -------------------------
def seed_developers():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM developers")
    count = cursor.fetchone()[0]

    if count == 0:
        developers = [
            ("Dev A",),
            ("Dev B",),
            ("Dev C",)
        ]

        cursor.executemany(
            "INSERT INTO developers (name) VALUES (?)",
            developers
        )

    conn.commit()
    conn.close()


# -------------------------
# INSERT TICKET
# -------------------------
def insert_ticket(client, issue, eta, jira_ticket_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO tickets (client, issue, eta, jira_ticket_id)
    VALUES (?, ?, ?, ?)
    """, (client, issue, eta, jira_ticket_id))

    ticket_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return ticket_id


# -------------------------
# INIT DB
# -------------------------
def init_db():
    create_ticket_table()
    create_developer_table()
    seed_developers()


def free_developer(ticket_id):
    conn = get_connection()
    cursor = conn.cursor()

    # find which dev has this ticket
    cursor.execute("""
        SELECT id FROM developers
        WHERE current_ticket_id = ?
    """, (ticket_id,))

    dev = cursor.fetchone()

    if dev:
        dev_id = dev[0]

        cursor.execute("""
            UPDATE developers
            SET status = 'FREE',
                current_ticket_id = NULL
            WHERE id = ?
        """, (dev_id,))

    conn.commit()
    conn.close()

