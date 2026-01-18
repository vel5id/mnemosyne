// Tests for the buffer package.
package buffer_test

import (
	"database/sql"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"mnemosyne/internal/buffer"
)

// setupTestDB creates an in-memory SQLite database with the raw_events table.
func setupTestDB(t *testing.T) *sql.DB {
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("Failed to open test database: %v", err)
	}

	// Create the raw_events table
	_, err = db.Exec(`
		CREATE TABLE raw_events (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			session_uuid TEXT NOT NULL,
			timestamp_utc TEXT NOT NULL,
			unix_time INTEGER NOT NULL,
			process_name TEXT NOT NULL,
			window_title TEXT,
			window_hwnd INTEGER NOT NULL,
			input_idle_ms INTEGER DEFAULT 0,
			input_intensity REAL DEFAULT 0.0
		)
	`)
	if err != nil {
		t.Fatalf("Failed to create raw_events table: %v", err)
	}

	return db
}

// TestBufferAdd tests adding entries to the buffer.
func TestBufferAdd(t *testing.T) {
	config := buffer.DefaultConfig()
	buf := buffer.New(config)

	entry := buffer.LogEntry{
		SessionUUID:    "test-session",
		UnixTime:       time.Now().UnixMilli(),
		ProcessName:    "test.exe",
		WindowTitle:    "Test Window",
		WindowHandle:   12345,
		InputIdleMs:    1000,
		InputIntensity: 0.5,
	}

	// Add entry
	flushed := buf.Add(entry)
	if flushed {
		t.Error("Expected no flush on first entry")
	}

	// Check buffer length
	if buf.Len() != 1 {
		t.Errorf("Expected buffer length 1, got %d", buf.Len())
	}
}

// TestBufferCapacity tests that buffer signals flush when capacity is reached.
func TestBufferCapacity(t *testing.T) {
	config := buffer.BufferConfig{
		Capacity:      10, // Small capacity for testing
		FlushTimeout:  5 * time.Minute,
		IdleThreshold: 60 * time.Second,
	}
	buf := buffer.New(config)

	// Add entries up to capacity
	for i := 0; i < 9; i++ {
		entry := buffer.LogEntry{
			SessionUUID:    "test-session",
			UnixTime:       time.Now().UnixMilli(),
			ProcessName:    "test.exe",
			WindowTitle:    "Test Window",
			WindowHandle:   int64(i),
			InputIdleMs:    1000,
			InputIntensity: 0.5,
		}
		flushed := buf.Add(entry)
		if flushed {
			t.Errorf("Unexpected flush at entry %d", i)
		}
	}

	// Add one more entry to reach capacity
	entry := buffer.LogEntry{
		SessionUUID:    "test-session",
		UnixTime:       time.Now().UnixMilli(),
		ProcessName:    "test.exe",
		WindowTitle:    "Test Window",
		WindowHandle:   999,
		InputIdleMs:    1000,
		InputIntensity: 0.5,
	}
	flushed := buf.Add(entry)
	if !flushed {
		t.Error("Expected flush when capacity is reached")
	}

	if buf.Len() != 10 {
		t.Errorf("Expected buffer length 10, got %d", buf.Len())
	}
}

// TestBufferFlush tests flushing entries to database.
func TestBufferFlush(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()

	config := buffer.DefaultConfig()
	buf := buffer.New(config)

	// Add multiple entries
	for i := 0; i < 5; i++ {
		entry := buffer.LogEntry{
			SessionUUID:    "test-session",
			UnixTime:       time.Now().UnixMilli(),
			ProcessName:    "test.exe",
			WindowTitle:    "Test Window",
			WindowHandle:   int64(i),
			InputIdleMs:    int64(i * 1000),
			InputIntensity: float32(i) * 0.1,
		}
		buf.Add(entry)
	}

	// Flush to database
	err := buf.Flush(db)
	if err != nil {
		t.Fatalf("Failed to flush buffer: %v", err)
	}

	// Verify buffer is empty
	if buf.Len() != 0 {
		t.Errorf("Expected empty buffer after flush, got %d entries", buf.Len())
	}

	// Verify entries in database
	var count int
	err = db.QueryRow("SELECT COUNT(*) FROM raw_events").Scan(&count)
	if err != nil {
		t.Fatalf("Failed to count entries: %v", err)
	}
	if count != 5 {
		t.Errorf("Expected 5 entries in database, got %d", count)
	}

	// Verify entry data
	var processName string
	var windowTitle string
	var windowHandle int64
	var inputIdleMs int64
	var inputIntensity float32

	err = db.QueryRow(`
		SELECT process_name, window_title, window_hwnd, input_idle_ms, input_intensity
		FROM raw_events
		WHERE window_hwnd = 2
	`).Scan(&processName, &windowTitle, &windowHandle, &inputIdleMs, &inputIntensity)
	if err != nil {
		t.Fatalf("Failed to query entry: %v", err)
	}

	if processName != "test.exe" {
		t.Errorf("Expected process name 'test.exe', got '%s'", processName)
	}
	if windowTitle != "Test Window" {
		t.Errorf("Expected window title 'Test Window', got '%s'", windowTitle)
	}
	if windowHandle != 2 {
		t.Errorf("Expected window handle 2, got %d", windowHandle)
	}
	if inputIdleMs != 2000 {
		t.Errorf("Expected input idle 2000ms, got %d", inputIdleMs)
	}
	if inputIntensity != 0.2 {
		t.Errorf("Expected input intensity 0.2, got %f", inputIntensity)
	}
}

// TestBufferFlushEmpty tests flushing an empty buffer.
func TestBufferFlushEmpty(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()

	config := buffer.DefaultConfig()
	buf := buffer.New(config)

	// Flush empty buffer
	err := buf.Flush(db)
	if err != nil {
		t.Fatalf("Failed to flush empty buffer: %v", err)
	}

	// Verify no entries in database
	var count int
	err = db.QueryRow("SELECT COUNT(*) FROM raw_events").Scan(&count)
	if err != nil {
		t.Fatalf("Failed to count entries: %v", err)
	}
	if count != 0 {
		t.Errorf("Expected 0 entries in database, got %d", count)
	}
}

// TestBufferForceFlush tests force flush during shutdown.
func TestBufferForceFlush(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()

	config := buffer.DefaultConfig()
	buf := buffer.New(config)

	// Add entries
	for i := 0; i < 3; i++ {
		entry := buffer.LogEntry{
			SessionUUID:    "test-session",
			UnixTime:       time.Now().UnixMilli(),
			ProcessName:    "test.exe",
			WindowTitle:    "Test Window",
			WindowHandle:   int64(i),
			InputIdleMs:    1000,
			InputIntensity: 0.5,
		}
		buf.Add(entry)
	}

	// Force flush
	err := buf.ForceFlush(db)
	if err != nil {
		t.Fatalf("Failed to force flush: %v", err)
	}

	// Verify buffer is empty
	if buf.Len() != 0 {
		t.Errorf("Expected empty buffer after force flush, got %d entries", buf.Len())
	}

	// Verify entries in database
	var count int
	err = db.QueryRow("SELECT COUNT(*) FROM raw_events").Scan(&count)
	if err != nil {
		t.Fatalf("Failed to count entries: %v", err)
	}
	if count != 3 {
		t.Errorf("Expected 3 entries in database, got %d", count)
	}
}

// TestBufferGetEntries tests retrieving entries from buffer.
func TestBufferGetEntries(t *testing.T) {
	config := buffer.DefaultConfig()
	buf := buffer.New(config)

	// Add entries
	expectedEntries := []buffer.LogEntry{
		{
			SessionUUID:    "test-session",
			UnixTime:       1000,
			ProcessName:    "test1.exe",
			WindowTitle:    "Window 1",
			WindowHandle:   1,
			InputIdleMs:    1000,
			InputIntensity: 0.1,
		},
		{
			SessionUUID:    "test-session",
			UnixTime:       2000,
			ProcessName:    "test2.exe",
			WindowTitle:    "Window 2",
			WindowHandle:   2,
			InputIdleMs:    2000,
			InputIntensity: 0.2,
		},
	}

	for _, entry := range expectedEntries {
		buf.Add(entry)
	}

	// Get entries
	entries := buf.GetEntries()

	if len(entries) != len(expectedEntries) {
		t.Fatalf("Expected %d entries, got %d", len(expectedEntries), len(entries))
	}

	for i, entry := range entries {
		if entry.SessionUUID != expectedEntries[i].SessionUUID {
			t.Errorf("Entry %d: SessionUUID mismatch", i)
		}
		if entry.UnixTime != expectedEntries[i].UnixTime {
			t.Errorf("Entry %d: UnixTime mismatch", i)
		}
		if entry.ProcessName != expectedEntries[i].ProcessName {
			t.Errorf("Entry %d: ProcessName mismatch", i)
		}
		if entry.WindowTitle != expectedEntries[i].WindowTitle {
			t.Errorf("Entry %d: WindowTitle mismatch", i)
		}
		if entry.WindowHandle != expectedEntries[i].WindowHandle {
			t.Errorf("Entry %d: WindowHandle mismatch", i)
		}
		if entry.InputIdleMs != expectedEntries[i].InputIdleMs {
			t.Errorf("Entry %d: InputIdleMs mismatch", i)
		}
		if entry.InputIntensity != expectedEntries[i].InputIntensity {
			t.Errorf("Entry %d: InputIntensity mismatch", i)
		}
	}
}

// TestBufferClear tests clearing the buffer.
func TestBufferClear(t *testing.T) {
	config := buffer.DefaultConfig()
	buf := buffer.New(config)

	// Add entries
	for i := 0; i < 5; i++ {
		entry := buffer.LogEntry{
			SessionUUID:    "test-session",
			UnixTime:       time.Now().UnixMilli(),
			ProcessName:    "test.exe",
			WindowTitle:    "Test Window",
			WindowHandle:   int64(i),
			InputIdleMs:    1000,
			InputIntensity: 0.5,
		}
		buf.Add(entry)
	}

	// Verify entries exist
	if buf.Len() != 5 {
		t.Errorf("Expected 5 entries before clear, got %d", buf.Len())
	}

	// Clear buffer
	buf.Clear()

	// Verify buffer is empty
	if buf.Len() != 0 {
		t.Errorf("Expected empty buffer after clear, got %d entries", buf.Len())
	}
}

// TestBufferSize tests memory size estimation.
func TestBufferSize(t *testing.T) {
	config := buffer.DefaultConfig()
	buf := buffer.New(config)

	// Add entries with different string lengths
	entries := []buffer.LogEntry{
		{
			SessionUUID:    "session-1",
			UnixTime:       1000,
			ProcessName:    "short.exe",
			WindowTitle:    "Short",
			WindowHandle:   1,
			InputIdleMs:    1000,
			InputIntensity: 0.5,
		},
		{
			SessionUUID:    "session-with-longer-uuid",
			UnixTime:       2000,
			ProcessName:    "longer-process-name.exe",
			WindowTitle:    "This is a much longer window title with more characters",
			WindowHandle:   2,
			InputIdleMs:    2000,
			InputIntensity: 0.7,
		},
	}

	for _, entry := range entries {
		buf.Add(entry)
	}

	size := buf.Size()
	if size <= 0 {
		t.Error("Expected positive buffer size")
	}

	// Size should be larger for longer strings
	buf2 := buffer.New(config)
	shortEntry := buffer.LogEntry{
		SessionUUID:    "s",
		UnixTime:       1000,
		ProcessName:    "p",
		WindowTitle:    "w",
		WindowHandle:   1,
		InputIdleMs:    1000,
		InputIntensity: 0.5,
	}
	buf2.Add(shortEntry)
	shortSize := buf2.Size()

	if size <= shortSize {
		t.Error("Expected larger buffer size for longer strings")
	}
}

// TestBufferLastFlush tests tracking of last flush time.
func TestBufferLastFlush(t *testing.T) {
	config := buffer.DefaultConfig()
	buf := buffer.New(config)

	initialFlush := buf.LastFlush()
	if initialFlush.IsZero() {
		t.Error("Expected non-zero initial flush time")
	}

	// Wait a bit longer to ensure time difference
	time.Sleep(50 * time.Millisecond)

	// Add an entry so Flush actually updates lastFlush
	// (Flush on empty buffer returns early without updating lastFlush)
	entry := buffer.LogEntry{
		SessionUUID:    "test-session",
		UnixTime:       time.Now().UnixMilli(),
		ProcessName:    "test.exe",
		WindowTitle:    "Test Window",
		WindowHandle:   12345,
		InputIdleMs:    1000,
		InputIntensity: 0.5,
	}
	buf.Add(entry)

	// Flush
	db := setupTestDB(t)
	defer db.Close()
	err := buf.Flush(db)
	if err != nil {
		t.Fatalf("Flush failed: %v", err)
	}

	afterFlush := buf.LastFlush()
	if !afterFlush.After(initialFlush) {
		t.Errorf("Expected last flush time to be updated after flush. Initial: %v, After: %v", initialFlush, afterFlush)
	}
}

// TestBufferMultipleFlushes tests multiple flush operations.
func TestBufferMultipleFlushes(t *testing.T) {
	db := setupTestDB(t)
	defer db.Close()

	config := buffer.DefaultConfig()
	buf := buffer.New(config)

	// First batch
	for i := 0; i < 3; i++ {
		entry := buffer.LogEntry{
			SessionUUID:    "session-1",
			UnixTime:       time.Now().UnixMilli(),
			ProcessName:    "test1.exe",
			WindowTitle:    "Window 1",
			WindowHandle:   int64(i),
			InputIdleMs:    1000,
			InputIntensity: 0.5,
		}
		buf.Add(entry)
	}
	buf.Flush(db)

	// Second batch
	for i := 0; i < 3; i++ {
		entry := buffer.LogEntry{
			SessionUUID:    "session-2",
			UnixTime:       time.Now().UnixMilli(),
			ProcessName:    "test2.exe",
			WindowTitle:    "Window 2",
			WindowHandle:   int64(i + 10),
			InputIdleMs:    2000,
			InputIntensity: 0.7,
		}
		buf.Add(entry)
	}
	buf.Flush(db)

	// Verify all entries in database
	var count int
	err := db.QueryRow("SELECT COUNT(*) FROM raw_events").Scan(&count)
	if err != nil {
		t.Fatalf("Failed to count entries: %v", err)
	}
	if count != 6 {
		t.Errorf("Expected 6 entries in database, got %d", count)
	}

	// Verify both sessions exist
	var session1Count, session2Count int
	err = db.QueryRow("SELECT COUNT(*) FROM raw_events WHERE session_uuid = ?", "session-1").Scan(&session1Count)
	if err != nil {
		t.Fatalf("Failed to count session 1 entries: %v", err)
	}
	err = db.QueryRow("SELECT COUNT(*) FROM raw_events WHERE session_uuid = ?", "session-2").Scan(&session2Count)
	if err != nil {
		t.Fatalf("Failed to count session 2 entries: %v", err)
	}

	if session1Count != 3 {
		t.Errorf("Expected 3 entries for session 1, got %d", session1Count)
	}
	if session2Count != 3 {
		t.Errorf("Expected 3 entries for session 2, got %d", session2Count)
	}
}
