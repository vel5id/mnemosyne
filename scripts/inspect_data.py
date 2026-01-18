import sqlite3
import json

DB_PATH = ".mnemosyne/activity.db"

def inspect():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print("--- SCHEMA ---")
        cursor.execute("PRAGMA table_info(raw_events)")
        for col in cursor.fetchall():
            print(f"{col['name']} ({col['type']})")
            
        print("\n--- SAMPLE RAW EVENTS (Top 3) ---")
        cursor.execute("SELECT * FROM raw_events ORDER BY id DESC LIMIT 3")
        rows = cursor.fetchall()
        for row in rows:
            print(dict(row))
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect()
