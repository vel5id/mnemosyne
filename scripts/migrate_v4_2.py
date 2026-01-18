import sqlite3
import os
import sys

# Determine DB path
DB_PATH = os.environ.get("MNEMOSYNE_DB_PATH", ".mnemosyne/activity.db")

def migrate():
    print(f"Migrating database at {DB_PATH}...")
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if columns exist
        cursor.execute("PRAGMA table_info(raw_events)")
        columns = [info[1] for info in cursor.fetchall()]
        
        migrated = False
        
        if "screenshot_path" not in columns:
            print("Adding screenshot_path column...")
            cursor.execute("ALTER TABLE raw_events ADD COLUMN screenshot_path TEXT")
            migrated = True
        else:
            print("column 'screenshot_path' already exists.")
        
        if "vlm_description" not in columns:
            print("Adding vlm_description column...")
            cursor.execute("ALTER TABLE raw_events ADD COLUMN vlm_description TEXT")
            migrated = True
        else:
            print("column 'vlm_description' already exists.")
            
        if migrated:
            conn.commit()
            print("Migration committed successfully.")
        else:
            print("No changes needed.")
            
        conn.close()
        
    except sqlite3.OperationalError as e:
        if "locked" in str(e):
            print("ERROR: Database is locked. Please stop Mnemosyne Brain process and try again.")
        else:
            print(f"ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate()
