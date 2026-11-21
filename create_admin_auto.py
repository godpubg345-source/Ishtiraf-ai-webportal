import sqlite3
import bcrypt
import os
import secrets

DB_PATH = "ishtiraf_ai.db"

def create_admin():
    if not os.path.exists(DB_PATH):
        print("Database not found. Run app.py first.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    email = "admin@ishtiraf.ai"
    # Never hardcode: take ADMIN_PASSWORD from env, else generate a random one
    password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
    name = "Super Admin"
    
    # Hash password
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        # Check if user exists
        cursor.execute("SELECT id FROM user WHERE email = ?", (email,))
        if cursor.fetchone():
            print(f"User {email} exists. Updating password...")
            cursor.execute("UPDATE user SET password_hash = ? WHERE email = ?", (password_hash, email))
        else:
            print(f"Creating new user {email}...")
            cursor.execute("""
                INSERT INTO user (email, name, password_hash, role, is_active, is_verified)
                VALUES (?, ?, ?, 'admin', 1, 1)
            """, (email, name, password_hash))
        
        conn.commit()
        print("✅ SUCCESS: Credentials set.")
        print(f"Email: {email}")
        print(f"Pass:  {password}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    create_admin()
