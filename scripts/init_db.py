"""Initialize fresh database with schema."""
import sqlite3
from pathlib import Path

DB_PATH = Path('.mnemosyne/activity.db')
SCHEMA_PATH = Path('db/schema.sql')

def main():
    print('  Creating database...')
    
    # Ensure directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Apply schema
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = f.read()
        cursor.executescript(schema)

    conn.commit()

    # Verify tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    print(f'  Created tables: {tables}')

    conn.close()
    print('  Database ready!')

if __name__ == '__main__':
    main()
