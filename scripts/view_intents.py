"""View Deepseek R1 analysis results from database"""
import sqlite3

conn = sqlite3.connect('.mnemosyne/activity.db')
cur = conn.cursor()

print("=" * 70)
print("🧠 DEEPSEEK R1 INTENT ANALYSIS - Latest 10 Results")
print("=" * 70)

# Join raw_events with context_enrichment
cur.execute('''
    SELECT r.window_title, c.user_intent, c.generated_tags, 
           datetime(r.unix_time, 'unixepoch', 'localtime') as time
    FROM raw_events r
    INNER JOIN context_enrichment c ON r.id = c.event_id
    WHERE c.user_intent IS NOT NULL AND c.user_intent != '' 
    ORDER BY r.unix_time DESC 
    LIMIT 10
''')

rows = cur.fetchall()

if not rows:
    print("\n❌ No enriched events found yet!")
    print("   Brain needs to process events first.")
    
    # Check what tables exist
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cur.fetchall()]
    print(f"\n   Existing tables: {tables}")
    
    # Check raw_events count
    cur.execute("SELECT COUNT(*) FROM raw_events")
    raw_count = cur.fetchone()[0]
    print(f"   Raw events: {raw_count}")
    
    # Check context_enrichment count
    try:
        cur.execute("SELECT COUNT(*) FROM context_enrichment")
        ctx_count = cur.fetchone()[0]
        print(f"   Enriched events: {ctx_count}")
    except:
        print("   Enriched events: 0 (table empty or missing)")
else:
    for i, (title, intent, tags, time) in enumerate(rows, 1):
        print(f"\n{'─' * 70}")
        print(f"#{i} | {time}")
        print(f"📝 Window: {title[:65]}{'...' if len(str(title)) > 65 else ''}")
        print(f"🎯 Intent: {intent}")
        print(f"🏷️  Tags:   {tags}")

print("\n" + "=" * 70)

# Stats
try:
    cur.execute("SELECT COUNT(*) FROM context_enrichment WHERE user_intent IS NOT NULL")
    enriched = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM raw_events")
    total = cur.fetchone()[0]
    pct = (enriched/total*100) if total > 0 else 0
    print(f"📊 Stats: {enriched} enriched / {total} total events ({pct:.1f}% processed)")
except Exception as e:
    print(f"📊 Stats error: {e}")
    
print("=" * 70)
conn.close()
