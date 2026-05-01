from database import get_connection

def auto_assign_ticket(ticket_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM developers
        WHERE status = 'FREE'
        LIMIT 1
    """)
    dev = cursor.fetchone()

    if dev:
        dev_id = dev[0]

        cursor.execute("""
            UPDATE tickets
            SET status = 'ASSIGNED',
                assigned_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (ticket_id,))

        cursor.execute("""
            UPDATE developers
            SET status = 'BUSY',
                current_ticket_id = ?
            WHERE id = ?
        """, (ticket_id, dev_id))

        conn.commit()
        conn.close()

        return {"status": "ASSIGNED", "dev_id": dev_id}

    else:
        cursor.execute("""
            UPDATE tickets
            SET status = 'WAITING'
            WHERE id = ?
        """, (ticket_id,))

        conn.commit()
        conn.close()

        return {"status": "WAITING"}


def get_next_waiting_ticket():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM tickets
        WHERE status = 'WAITING'
        ORDER BY created_at ASC
        LIMIT 1
    """)

    ticket = cursor.fetchone()
    conn.close()

    return ticket[0] if ticket else None


def process_queue():
    next_ticket_id = get_next_waiting_ticket()

    if next_ticket_id:
        return auto_assign_ticket(next_ticket_id)

    return {"status": "NO_WAITING_TICKETS"}
