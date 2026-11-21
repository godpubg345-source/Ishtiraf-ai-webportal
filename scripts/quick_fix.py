"""
Quick Fix: Promote existing user to Admin
Super simple - just run and enter your email.
"""

import sqlite3
import os

# Use absolute path
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # portal root (script lives in scripts/)
DB_PATH = os.path.join(SCRIPT_DIR, "ishtiraf_ai.db")

print("\n" + "="*50)
print("  🚀 Quick Admin Fix")
print("="*50 + "\n")

if not os.path.exists(DB_PATH):
    print(f"❌ Database not found at: {DB_PATH}")
    print()
    print("Run this command first:")
    print("cd c:/Users/Omen/OneDrive/Desktop/IshtirafAI_Project/IshtirafAI_WebPortal")
    print("& ../.venv-portal/Scripts/python.exe quick_fix.py")
    exit(1)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Show users
print("Current Users:")
print("-" * 50)
cursor.execute("SELECT email, name, role FROM user")
users = cursor.fetchall()

if not users:
    print("  (No users found - database is empty)")
    print()
    print("Register first user at http://127.0.0.1:5000/auth/register")
    print("First user will automatically be ADMIN!")
    conn.close()
    exit(0)

for email, name, role in users:
    print(f"  📧 {email:<30} | {name:<20} | {role}")
print("-" * 50)
print()

email = input("Enter EMAIL to promote to ADMIN: ").strip()

cursor.execute("SELECT id FROM user WHERE email = ?", (email,))
user = cursor.fetchone()

if not user:
    print(f"\n❌ User '{email}' not found!")
    conn.close()
    exit(1)

cursor.execute("UPDATE user SET role = 'admin' WHERE email = ?", (email,))
conn.commit()

print(f"\n✅ SUCCESS! '{email}' is now an ADMIN!")
print("🔄 Logout and login again to see changes.\n")

conn.close()
