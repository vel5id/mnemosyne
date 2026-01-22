// Package buffer provides in-memory buffering for log entries to minimize SSD writes.
// Implements buffered persistence with configurable flush policies.
package buffer

import (
	"database/sql"
	"fmt"
	"sync"
	"time"
)

// LogEntry represents a single activity log entry.
// Uses small types to minimize memory footprint.
// Matches the raw_events table schema in db/schema.sql.
type LogEntry struct {
	SessionUUID    string  // Session UUID for grouping events
	UnixTime       int64   // Unix timestamp in milliseconds
	ProcessName    string  // Process executable name (interned string for memory efficiency)
	WindowTitle    string  // Window title text
	WindowHandle   int64   // HWND as int64 (SQLite INTEGER)
	InputIdleMs    int64   // Time of inactivity in milliseconds
	InputIntensity float32 // Calculated input intensity (0.0 to 1.0)
	ScreenshotPath string  // Path to captured screenshot
	ScreenshotData []byte  // In-memory screenshot data (JPEG)
}

// BufferConfig holds configuration for the buffer behavior.
type BufferConfig struct {
	Capacity      int           // Maximum number of entries before forced flush
	FlushTimeout  time.Duration // Time between automatic flushes
	IdleThreshold time.Duration // Time of inactivity before marking as idle
}

// DefaultConfig returns sensible defaults for the buffer.
func DefaultConfig() BufferConfig {
	return BufferConfig{
		Capacity:      100, // Flush when 100 entries accumulated
		FlushTimeout:  5 * time.Minute,
		IdleThreshold: 60 * time.Second,
	}
}

// Buffer manages in-memory storage of log entries with thread-safe operations.
// Implements buffered persistence to protect SSD from write amplification.
type Buffer struct {
	mu         sync.RWMutex
	entries    []LogEntry
	config     BufferConfig
	lastFlush  time.Time
	flushTimer *time.Timer
	flushChan  chan struct{}
	stopChan   chan struct{}
}

// New creates a new buffer with the given configuration.
func New(config BufferConfig) *Buffer {
	b := &Buffer{
		entries:   make([]LogEntry, 0, config.Capacity),
		config:    config,
		lastFlush: time.Now(),
		flushChan: make(chan struct{}, 1),
		stopChan:  make(chan struct{}),
	}

	// Start automatic flush timer
	b.startFlushTimer()

	return b
}

// startFlushTimer starts the background timer for periodic flushing.
func (b *Buffer) startFlushTimer() {
	b.flushTimer = time.AfterFunc(b.config.FlushTimeout, func() {
		select {
		case b.flushChan <- struct{}{}:
		default:
			// Flush already pending
		}
	})
}

// resetFlushTimer resets the automatic flush timer.
func (b *Buffer) resetFlushTimer() {
	if b.flushTimer != nil {
		b.flushTimer.Stop()
	}
	b.startFlushTimer()
}

// Add adds a new log entry to the buffer.
// Returns true if the buffer was flushed due to capacity threshold.
func (b *Buffer) Add(entry LogEntry) (flushed bool) {
	b.mu.Lock()
	defer b.mu.Unlock()

	b.entries = append(b.entries, entry)

	// Check capacity threshold
	if len(b.entries) >= b.config.Capacity {
		// Signal flush (will be handled by caller)
		return true
	}

	return false
}

// Len returns the current number of entries in the buffer.
func (b *Buffer) Len() int {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return len(b.entries)
}

// Size returns the current memory usage estimate in bytes.
func (b *Buffer) Size() int {
	b.mu.RLock()
	defer b.mu.RUnlock()

	size := 0
	for _, entry := range b.entries {
		size += 32 + // Fixed fields (SessionUUID string pointer + UnixTime + WindowHandle + InputIdleMs + InputIntensity)
			len(entry.SessionUUID) +
			len(entry.ProcessName) +
			len(entry.ProcessName) +
			len(entry.WindowTitle) +
			len(entry.ScreenshotPath) +
			len(entry.ScreenshotData)
	}
	return size
}

// Flush writes all buffered entries to the database in a single transaction.
// This is the critical operation for SSD protection - batch inserts minimize I/O.
func (b *Buffer) Flush(db *sql.DB) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	if len(b.entries) == 0 {
		return nil
	}

	// Start transaction
	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}

	// Prepare insert statement
	stmt, err := tx.Prepare(`
		INSERT INTO raw_events
		(session_uuid, timestamp_utc, unix_time, process_name, window_title, window_hwnd, input_idle_ms, input_intensity, screenshot_path)
		VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?)
	`)
	if err != nil {
		tx.Rollback()
		return fmt.Errorf("failed to prepare statement: %w", err)
	}
	defer stmt.Close()

	// Batch insert all entries
	for _, entry := range b.entries {
		_, err := stmt.Exec(
			entry.SessionUUID,
			entry.UnixTime,
			entry.ProcessName,
			entry.WindowTitle,
			entry.WindowHandle,
			entry.InputIdleMs,
			entry.InputIdleMs,
			entry.InputIntensity,
			entry.ScreenshotPath,
		)
		if err != nil {
			tx.Rollback()
			return fmt.Errorf("failed to insert entry: %w", err)
		}
	}

	// Commit transaction
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	// Clear buffer and update last flush time
	b.entries = b.entries[:0]
	b.lastFlush = time.Now()
	b.resetFlushTimer()

	return nil
}

// ForceFlush immediately flushes all entries regardless of thresholds.
// Used during graceful shutdown.
func (b *Buffer) ForceFlush(db *sql.DB) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	if len(b.entries) == 0 {
		return nil
	}

	// Stop timer to prevent race conditions
	if b.flushTimer != nil {
		b.flushTimer.Stop()
	}

	// Perform flush
	err := b.flushUnsafe(db)
	if err != nil {
		return err
	}

	// Clear buffer
	b.entries = b.entries[:0]
	b.lastFlush = time.Now()

	return nil
}

// flushUnsafe performs flush without locking (caller must hold lock).
func (b *Buffer) flushUnsafe(db *sql.DB) error {
	if len(b.entries) == 0 {
		return nil
	}

	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}

	// Prepare insert statement
	stmt, err := tx.Prepare(`
		INSERT INTO raw_events
		(session_uuid, timestamp_utc, unix_time, process_name, window_title, window_hwnd, input_idle_ms, input_intensity, screenshot_path)
		VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?)
	`)
	if err != nil {
		tx.Rollback()
		return fmt.Errorf("failed to prepare statement: %w", err)
	}
	defer stmt.Close()

	for _, entry := range b.entries {
		_, err := stmt.Exec(
			entry.SessionUUID,
			entry.UnixTime,
			entry.ProcessName,
			entry.WindowTitle,
			entry.WindowHandle,
			entry.InputIdleMs,
			entry.InputIntensity,
			entry.ScreenshotPath,
		)
		if err != nil {
			tx.Rollback()
			return fmt.Errorf("failed to insert entry: %w", err)
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	return nil
}

// FlushChannel returns a channel that signals when a flush is needed.
func (b *Buffer) FlushChannel() <-chan struct{} {
	return b.flushChan
}

// LastFlush returns the time of the last successful flush.
func (b *Buffer) LastFlush() time.Time {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return b.lastFlush
}

// Stop stops the background flush timer.
// Should be called during graceful shutdown.
func (b *Buffer) Stop() {
	close(b.stopChan)
	if b.flushTimer != nil {
		b.flushTimer.Stop()
	}
}

// GetEntries returns a copy of all buffered entries.
// Used for testing and debugging.
func (b *Buffer) GetEntries() []LogEntry {
	b.mu.RLock()
	defer b.mu.RUnlock()

	copies := make([]LogEntry, len(b.entries))
	copy(copies, b.entries)
	return copies
}

// Clear removes all entries from the buffer without flushing.
// Used for testing.
func (b *Buffer) Clear() {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.entries = b.entries[:0]
}

// GetAndClear returns all entries and clears the buffer atomically.
// Used for Redis processing where we handle persistence externally.
func (b *Buffer) GetAndClear() []LogEntry {
	b.mu.Lock()
	defer b.mu.Unlock()

	if len(b.entries) == 0 {
		return nil
	}

	entries := b.entries
	// Allocate new buffer to avoid race conditions with old slice
	b.entries = make([]LogEntry, 0, b.config.Capacity)

	// Reset timer since we cleared data
	b.lastFlush = time.Now()
	b.resetFlushTimer()

	return entries
}
