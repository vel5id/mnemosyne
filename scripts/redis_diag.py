"""Redis Stream Diagnostic Tool for Mnemosyne"""
import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

STREAM = "mnemosyne:events"
GROUP = "mnemosyne_brain_group"

print("=" * 60)
print("MNEMOSYNE REDIS DIAGNOSTIC")
print("=" * 60)

# 1. Stream info
try:
    stream_len = r.xlen(STREAM)
    print(f"\n📊 Stream '{STREAM}': {stream_len} total messages")
except Exception as e:
    print(f"❌ Stream error: {e}")

# 2. Consumer group info
try:
    groups = r.xinfo_groups(STREAM)
    print(f"\n👥 Consumer Groups:")
    for g in groups:
        print(f"   - {g['name']}: {g['pending']} pending, {g['consumers']} consumers, last-id: {g['last-delivered-id']}")
except Exception as e:
    print(f"❌ Group error: {e}")

# 3. Pending messages detail
try:
    pending = r.xpending(STREAM, GROUP)
    print(f"\n⏳ Pending Summary:")
    print(f"   Total pending: {pending['pending']}")
    if pending['pending'] > 0:
        print(f"   Min ID: {pending['min']}")
        print(f"   Max ID: {pending['max']}")
        print(f"   Consumers with pending:")
        for consumer, count in pending['consumers'].items():
            print(f"      - {consumer}: {count} messages")
except Exception as e:
    print(f"❌ Pending error: {e}")

# 4. Sample messages
try:
    msgs = r.xrange(STREAM, count=3)
    print(f"\n📝 Sample messages (first 3):")
    for msg_id, data in msgs:
        print(f"   [{msg_id}] keys: {list(data.keys())}")
except Exception as e:
    print(f"❌ Sample error: {e}")

# 5. Stream info detailed
try:
    info = r.xinfo_stream(STREAM)
    print(f"\n📈 Stream Details:")
    print(f"   Length: {info['length']}")
    print(f"   First entry: {info['first-entry'][0] if info['first-entry'] else 'N/A'}")
    print(f"   Last entry: {info['last-entry'][0] if info['last-entry'] else 'N/A'}")
except Exception as e:
    print(f"❌ Stream info error: {e}")

print("\n" + "=" * 60)
