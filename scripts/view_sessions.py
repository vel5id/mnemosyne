"""View Session Aggregation results from database"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('.mnemosyne/activity.db')
cur = conn.cursor()

print("=" * 70)
print("📅 SESSION AGGREGATION - Latest 10 Sessions")
print("=" * 70)

cur.execute('''
    SELECT session_uuid, start_time, end_time, duration_seconds,
           primary_process, primary_window, activity_summary, 
           generated_tags, event_count
    FROM sessions
    ORDER BY start_time DESC 
    LIMIT 10
''')

rows = cur.fetchall()

if not rows:
    print("\n❌ No sessions found yet!")
    print("   Sessions are created when you switch windows or after 30 min of activity.")
    print("   Run Brain for a while and switch between apps to generate sessions.")
else:
    for i, row in enumerate(rows, 1):
        uuid, start, end, duration, process, window, summary, tags, events = row
        start_dt = datetime.fromtimestamp(start).strftime('%H:%M:%S') if start else 'N/A'
        end_dt = datetime.fromtimestamp(end).strftime('%H:%M:%S') if end else 'N/A'
        
        print(f"\n{'─' * 70}")
        print(f"#{i} | {start_dt} → {end_dt} ({duration//60}m {duration%60}s) | {events} events")
        print(f"📱 App: {process}")
        print(f"📝 Window: {(window or 'N/A')[:60]}{'...' if len(str(window or '')) > 60 else ''}")
        print(f"🎯 Summary: {summary or 'No summary'}")
        print(f"🏷️  Tags: {tags}")

print("\n" + "=" * 70)

# Stats
try:
    cur.execute("SELECT COUNT(*) FROM sessions")
    session_count = cur.fetchone()[0]
    cur.execute("SELECT SUM(duration_seconds) FROM sessions")
    total_duration = cur.fetchone()[0] or 0
    print(f"📊 Stats: {session_count} sessions | {total_duration//3600}h {(total_duration%3600)//60}m total tracked")
except Exception as e:
    print(f"📊 Stats error: {e}")

print("=" * 70)
conn.close()
