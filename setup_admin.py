"""
IshtirafAI Admin Setup Wizard
Production-ready script to initialize the first admin account.
Run this ONCE during initial deployment.
"""

import os
import sys
import sqlite3
import bcrypt
import getpass

# Use absolute path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "ishtiraf_ai.db")

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    print("=" * 60)
    print("  🏥 IshtirafAI - Admin Setup Wizard")
    print("=" * 60)
    print()

def check_existing_admin(cursor):
    """Check if admin already exists"""
    cursor.execute("SELECT COUNT(*) FROM user WHERE role = 'admin'")
    count = cursor.fetchone()[0]
    return count > 0

def setup_admin():
    clear_screen()
    print_header()
    
    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at:")
        print(f"   {DB_PATH}")
        print()
        print("Please run the Flask app first to create tables:")
        print("   cd c:/Users/Omen/OneDrive/Desktop/IshtirafAI_Project/IshtirafAI_WebPortal")
        print("   & ../.venv310/Scripts/python.exe app.py")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if admin exists
        if check_existing_admin(cursor):
            print("⚠️  WARNING: An admin account already exists!")
            print()
            choice = input("Do you want to create ANOTHER admin? (yes/no): ").lower()
            if choice != 'yes':
                print("❌ Setup cancelled.")
                return
        
        print("📝 Create Super Admin Account")
        print("-" * 60)
        
        # Get user input
        name = input("Enter Admin Name: ").strip()
        if not name:
            print("❌ Name cannot be empty!")
            return
        
        email = input("Enter Admin Email: ").strip()
        if not email or '@' not in email:
            print("❌ Invalid email!")
            return
        
        # Check if email exists
        cursor.execute("SELECT id FROM user WHERE email = ?", (email,))
        if cursor.fetchone():
            print(f"❌ Email '{email}' already exists!")
            return
        
        password = getpass.getpass("Enter Password (hidden): ")
        password_confirm = getpass.getpass("Confirm Password: ")
        
        if password != password_confirm:
            print("❌ Passwords do not match!")
            return
        
        if len(password) < 6:
            print("❌ Password must be at least 6 characters!")
            return
        
        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Insert admin user
        cursor.execute("""
            INSERT INTO user (email, name, password_hash, role, is_active, is_verified)
            VALUES (?, ?, ?, 'admin', 1, 1)
        """, (email, name, password_hash))
        
        conn.commit()
        
        print()
        print("=" * 60)
        print("✅ SUCCESS! Admin account created successfully!")
        print("=" * 60)
        print(f"   Name:  {name}")
        print(f"   Email: {email}")
        print(f"   Role:  SUPER ADMIN")
        print()
        print("🚀 You can now login at: http://127.0.0.1:5000/auth/login")
        print()
        
    except sqlite3.Error as e:
        print(f"❌ Database Error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if conn:
            conn.close()

def reset_database():
    """Delete and recreate database (CAREFUL!)"""
    print_header()
    print("⚠️  DATABASE RESET - THIS WILL DELETE ALL DATA!")
    print()
    confirm = input("Type 'DELETE EVERYTHING' to confirm: ")
    
    if confirm != "DELETE EVERYTHING":
        print("❌ Reset cancelled.")
        return
    
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"✅ Database deleted: {DB_PATH}")
    else:
        print("ℹ️  Database doesn't exist.")
    
    print()
    print("🔄 Please restart the Flask app to recreate tables.")
    print("   Then run this script again to create the admin account.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        reset_database()
    else:
        setup_admin()
