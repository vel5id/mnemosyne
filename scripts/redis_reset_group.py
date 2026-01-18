"""Reset Redis Consumer Group to re-read all messages"""
import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

STREAM = "mnemosyne:events"
GROUP = "mnemosyne_brain_group"

print("=" * 60)
print("RESETTING CONSUMER GROUP")
print("=" * 60)

try:
    # Delete the old consumer group
    r.xgroup_destroy(STREAM, GROUP)
    print(f"✅ Deleted consumer group '{GROUP}'")
except Exception as e:
    print(f"⚠️ Could not delete group (may not exist): {e}")

try:
    # Recreate from the BEGINNING of stream (id='0')
    r.xgroup_create(STREAM, GROUP, id='0', mkstream=True)
    print(f"✅ Created consumer group '{GROUP}' starting from ID='0' (beginning)")
except Exception as e:
    print(f"❌ Error creating group: {e}")

# Verify
try:
    groups = r.xinfo_groups(STREAM)
    for g in groups:
        if g['name'] == GROUP:
            print(f"\n📊 New group state:")
            print(f"   last-delivered-id: {g['last-delivered-id']}")
            print(f"   pending: {g['pending']}")
except Exception as e:
    print(f"❌ Verify error: {e}")

print("\n" + "=" * 60)
print("Now restart Brain to start consuming from the beginning!")
print("=" * 60)
