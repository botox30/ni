
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional
import uvicorn

app = FastAPI(title="Discord Bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database initialization
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    # Create guilds table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guilds (
            guild_id INTEGER PRIMARY KEY,
            owner_id INTEGER,
            name TEXT,
            access_role INTEGER,
            notification_channel INTEGER,
            purchase_channel INTEGER,
            has_subscription BOOLEAN DEFAULT TRUE,
            subscription_active BOOLEAN DEFAULT TRUE,
            subscription_end TEXT,
            disabled BOOLEAN DEFAULT FALSE
        )
    """)
    
    # Create guild_members table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            member_id INTEGER,
            email TEXT,
            has_access BOOLEAN DEFAULT FALSE,
            access_end TEXT,
            hours INTEGER DEFAULT 0,
            days INTEGER DEFAULT 0,
            refresh_token TEXT,
            sent_ended_notif BOOLEAN DEFAULT FALSE,
            notification_channel INTEGER,
            UNIQUE(guild_id, member_id)
        )
    """)
    
    # Create discord_users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS discord_users (
            discord_user_id TEXT PRIMARY KEY,
            email TEXT,
            has_access BOOLEAN DEFAULT FALSE,
            access_end TEXT,
            additional_days INTEGER DEFAULT 0
        )
    """)
    
    # Create tickets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            channel_id TEXT UNIQUE,
            user_id TEXT,
            deleted BOOLEAN DEFAULT FALSE
        )
    """)
    
    # Create scraped_content table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scraped_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            content TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect("bot_database.db")

# Initialize database on startup
try:
    init_db()
    print("Database initialized successfully")
except Exception as e:
    print(f"Database initialization error: {e}")
    init_db()  # Try again

# Guild endpoints
@app.get("/api/guild/{guild_id}/")
async def get_guild(guild_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM guilds WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    
    if not row:
        # Create default guild
        cursor.execute("""
            INSERT INTO guilds (guild_id, has_subscription, subscription_active, subscription_end, disabled)
            VALUES (?, TRUE, TRUE, ?, FALSE)
        """, (guild_id, "2025-12-31T23:59:59"))
        conn.commit()
        
        cursor.execute("SELECT * FROM guilds WHERE guild_id = ?", (guild_id,))
        row = cursor.fetchone()
    
    conn.close()
    
    columns = ['guild_id', 'owner_id', 'name', 'access_role', 'notification_channel', 
               'purchase_channel', 'has_subscription', 'subscription_active', 'subscription_end', 'disabled']
    
    return dict(zip(columns, row))

@app.post("/api/guild/")
async def create_guild(guild_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO guilds (guild_id, owner_id, name, access_role, notification_channel, purchase_channel)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            guild_data['guild_id'],
            guild_data.get('owner_id'),
            guild_data.get('name'),
            guild_data.get('access_role'),
            guild_data.get('notification_channel'),
            guild_data.get('purchase_channel')
        ))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

@app.patch("/api/guild/{guild_id}/")
async def update_guild(guild_id: int, update_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    
    # Build dynamic update query
    fields = []
    values = []
    for key, value in update_data.items():
        if key in ['notification_channel', 'purchase_channel', 'access_role']:
            fields.append(f"{key} = ?")
            values.append(value)
    
    if fields:
        values.append(guild_id)
        query = f"UPDATE guilds SET {', '.join(fields)} WHERE guild_id = ?"
        cursor.execute(query, values)
        conn.commit()
    
    conn.close()
    return {"success": True}

# Guild member endpoints
@app.get("/api/guild/{guild_id}/member/{member_id}/")
async def get_guild_member(guild_id: int, member_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM guild_members WHERE guild_id = ? AND member_id = ?", (guild_id, member_id))
    row = cursor.fetchone()
    
    if not row:
        # Create default member with access
        cursor.execute("""
            INSERT INTO guild_members (guild_id, member_id, email, has_access, access_end)
            VALUES (?, ?, NULL, TRUE, ?)
        """, (guild_id, member_id, "2025-12-31T23:59:59"))
        conn.commit()
        
        cursor.execute("SELECT * FROM guild_members WHERE guild_id = ? AND member_id = ?", (guild_id, member_id))
        row = cursor.fetchone()
    
    conn.close()
    
    columns = ['id', 'guild', 'member', 'email', 'has_access', 'access_end', 'hours', 'days', 
               'refresh_token', 'sent_ended_notif', 'notification_channel']
    
    result = dict(zip(columns, row))
    result['guild'] = result.pop('guild')  # Rename guild_id to guild
    result['member'] = result.pop('member')  # Rename member_id to member
    
    return result

@app.post("/api/guild-member/")
async def create_guild_member(member_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO guild_members 
            (guild_id, member_id, email, has_access, access_end, hours, days, refresh_token, sent_ended_notif, notification_channel)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            member_data['guild'],
            member_data['member'],
            member_data.get('email'),
            member_data.get('days', 0) > 0,
            member_data.get('access_end'),
            member_data.get('hours', 0),
            member_data.get('days', 0),
            member_data.get('refresh_token'),
            member_data.get('sent_ended_notif', False),
            member_data.get('notification_channel')
        ))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

@app.delete("/api/guild/{guild_id}/member/{member_id}/email/")
async def reset_member_email(guild_id: int, member_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE guild_members SET email = NULL WHERE guild_id = ? AND member_id = ?", (guild_id, member_id))
    conn.commit()
    conn.close()
    
    return {"success": True, "message": "Email reset successfully"}

@app.patch("/api/guild/{guild_id}/member/{member_id}/")
async def update_guild_member(guild_id: int, member_id: int, update_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    
    # Build dynamic update query
    fields = []
    values = []
    for key, value in update_data.items():
        if key in ['email', 'has_access', 'access_end', 'hours', 'days', 'refresh_token', 'sent_ended_notif', 'notification_channel', 'remove_access']:
            if key == 'remove_access' and value:
                fields.append("has_access = ?")
                values.append(False)
                fields.append("access_end = ?")
                values.append(None)
            elif key == 'days' and value > 0:
                # When adding days, set has_access=True and calculate access_end
                fields.append("days = ?")
                values.append(value)
                fields.append("has_access = ?")
                values.append(True)
                fields.append("access_end = ?")
                if value >= 99999:
                    # Forever access
                    values.append("2099-12-31T23:59:59")
                else:
                    # Calculate end date
                    from datetime import datetime, timedelta
                    end_date = datetime.now() + timedelta(days=value)
                    values.append(end_date.isoformat())
            else:
                fields.append(f"{key} = ?")
                values.append(value)
    
    if fields:
        values.extend([guild_id, member_id])
        query = f"UPDATE guild_members SET {', '.join(fields)} WHERE guild_id = ? AND member_id = ?"
        cursor.execute(query, values)
        conn.commit()
    
    conn.close()
    return {"success": True}

# Discord user endpoints
@app.get("/api/discord-user/{user_id}/")
async def get_discord_user(user_id: str):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM discord_users WHERE discord_user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row:
        columns = ['discord_user_id', 'email', 'has_access', 'access_end', 'additional_days']
        user_data = dict(zip(columns, row))
        return {"success": True, "user": user_data}
    
    conn.close()
    return {"success": False}

@app.post("/api/discord-user/")
async def create_discord_user(user_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO discord_users (discord_user_id, email, has_access, access_end)
            VALUES (?, ?, FALSE, NULL)
        """, (
            user_data['discord_user_id'],
            user_data.get('email')
        ))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

@app.patch("/api/discord-user/{user_id}/update/")
async def update_discord_user(user_id: str, update_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    
    # Handle additional_days logic
    if 'additional_days' in update_data:
        days = update_data['additional_days']
        new_access_end = (datetime.now() + timedelta(days=days)).isoformat()
        update_data['access_end'] = new_access_end
        update_data['has_access'] = True
        del update_data['additional_days']
    
    # Build dynamic update query
    fields = []
    values = []
    for key, value in update_data.items():
        if key in ['email', 'has_access', 'access_end']:
            fields.append(f"{key} = ?")
            values.append(value)
    
    if fields:
        values.append(user_id)
        query = f"UPDATE discord_users SET {', '.join(fields)} WHERE discord_user_id = ?"
        cursor.execute(query, values)
        conn.commit()
    
    conn.close()
    return {"success": True}

# Ticket endpoints
@app.post("/api/ticket/create/")
async def create_ticket(ticket_data: dict):
    print(f"DEBUG: Creating ticket for user {ticket_data.get('user_id')}, channel {ticket_data.get('channel_id')}")
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Check if user already has an active ticket
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE user_id = ? AND deleted = FALSE", (ticket_data['user_id'],))
        active_tickets = cursor.fetchone()[0]
        print(f"DEBUG: User {ticket_data['user_id']} has {active_tickets} active tickets")
        
        if active_tickets > 0:
            print(f"DEBUG: Rejecting ticket creation - user already has active tickets")
            return {"success": False, "error": "User already has an active ticket"}
        
        import time
        import random
        ticket_id = f"ticket_{int(time.time())}_{random.randint(1000, 9999)}"
        print(f"DEBUG: Creating ticket with ID: {ticket_id}")
        cursor.execute("""
            INSERT INTO tickets (ticket_id, channel_id, user_id)
            VALUES (?, ?, ?)
        """, (ticket_id, ticket_data['channel_id'], ticket_data['user_id']))
        conn.commit()
        print(f"DEBUG: Ticket created successfully")
        return {"success": True, "ticket": {"ticket_id": ticket_id}}
    except Exception as e:
        print(f"DEBUG: Error creating ticket: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

@app.post("/api/ticket/delete/")
async def delete_ticket(ticket_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE tickets SET deleted = TRUE WHERE channel_id = ?", (ticket_data['channel_id'],))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

@app.get("/api/ticket/not-deleted/")
async def get_active_tickets():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT channel_id FROM tickets WHERE deleted = FALSE")
    rows = cursor.fetchall()
    conn.close()
    
    channels = [row[0] for row in rows]
    return {"channels": channels}

@app.post("/api/ticket/cleanup-user/")
async def cleanup_user_tickets(ticket_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Mark all tickets for this user as deleted
        cursor.execute("UPDATE tickets SET deleted = TRUE WHERE user_id = ?", (ticket_data['user_id'],))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

# Utility endpoints
@app.get("/api/users-without-access/")
async def users_without_access():
    return []

@app.get("/api/expired-access-users/")
async def expired_access_users():
    return {"success": True, "users": []}

@app.post("/api/save-scrape-content/")
async def save_scraped_content(content_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO scraped_content (url, title, content)
            VALUES (?, ?, ?)
        """, (content_data['url'], content_data['title'], content_data['content']))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

@app.post("/api/get-scraped-content/")
async def get_scraped_content(request_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT content FROM scraped_content WHERE url = ?", (request_data['url'],))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {"content": row[0]}
    return {"content": None}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
