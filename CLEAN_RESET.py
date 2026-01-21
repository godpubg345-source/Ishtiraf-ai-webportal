"""
🧹 IshtirafAI Web Portal - Complete Cleanup & Reset Script
Run this to get a FRESH START with clean structure
"""

import os
import shutil
import sys

# Set working directory
PORTAL_DIR = os.path.abspath(os.path.dirname(__file__))
os.chdir(PORTAL_DIR)

print("=" * 60)
print("  🧹 IshtirafAI Web Portal - Clean Reset")
print("=" * 60)
print()

# Items to delete
cleanup_items = [
    # Database (will be recreated)
    "ishtiraf_ai.db",
    "ishtiraf_ai.db-journal",
    
    # Python cache
    "__pycache__",
    "models/__pycache__",
    "routes/__pycache__",
    "utils/__pycache__",
    
    # Old redundant files
    "models.py",  # We use models/ directory now
    "ADMIN_SETUP_GUIDE.md",  # Outdated guide
]

print("⚠️  WARNING: This will DELETE:")
for item in cleanup_items:
    if os.path.exists(item):
        print(f"   ❌ {item}")
print()

confirm = input("Type 'RESET' to confirm: ")

if confirm != "RESET":
    print("❌ Cleanup cancelled.")
    sys.exit(0)

print()
print("🗑️  Deleting files...")

deleted_count = 0
for item in cleanup_items:
    item_path = os.path.join(PORTAL_DIR, item)
    try:
        if os.path.isfile(item_path):
            os.remove(item_path)
            print(f"   ✅ Deleted: {item}")
            deleted_count += 1
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)
            print(f"   ✅ Deleted: {item}/")
            deleted_count += 1
    except Exception as e:
        print(f"   ⚠️  Could not delete {item}: {e}")

print()
print("=" * 60)
print(f"✅ Cleanup Complete! ({deleted_count} items removed)")
print("=" * 60)
print()
print("🚀 NEXT STEPS:")
print("   1. Run Flask app:")
print("      & ../.venv310/Scripts/python.exe app.py")
print()
print("   2. Register first user at:")
print("      http://127.0.0.1:5000/auth/register")
print()
print("   3. First user will automatically be ADMIN!")
print()
