// Package monitor implements the main 5Hz observation loop with Smart Full Stop.
// This is the core of the Watcher tier - orchestrating data collection with minimal resource usage.
package monitor

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/base64"
	"fmt"
	"image"
	"image/jpeg"
	"log"
	"runtime"
	"sync"
	"syscall"
	"time"

	"github.com/kbinani/screenshot"

	"mnemosyne/internal/buffer"
	"mnemosyne/internal/storage"
	"mnemosyne/internal/win32"
)

// Config holds configuration for the monitor.
type Config struct {
	TickInterval       time.Duration // Time between ticks (default: 200ms for 5Hz)
	IdleThreshold      time.Duration // Time of inactivity before marking as idle
	BufferCapacity     int           // Buffer capacity before forced flush
	FlushTimeout       time.Duration // Time between automatic flushes
	ScreenshotInterval time.Duration // Time between screenshots (e.g. 2s)
}

// DefaultConfig returns sensible defaults for the monitor.
func DefaultConfig() Config {
	return Config{
		TickInterval:       1000 * time.Millisecond, // 1Hz (1 tick per second)
		IdleThreshold:      60 * time.Second,
		BufferCapacity:     100,
		FlushTimeout:       5 * time.Minute,
		ScreenshotInterval: 1 * time.Second, // Rate limit: 1 screenshot per second
	}
}

// State holds the current state of the monitor.
type State struct {
	LastWindowHandle   uintptr
	LastWindowTitle    string
	LastProcessName    string
	LastInputTick      uint32
	LastTickTime       time.Time
	LastScreenshotTime time.Time // Track last screenshot time
}

// Monitor implements the main observation loop with Smart Full Stop.
type Monitor struct {
	config Config
	db     *sql.DB
	redis  *storage.RedisClient // Optional Redis client
	buf    *buffer.Buffer
	state  State
	mu     sync.RWMutex

	// Statistics
	tickCount    uint64
	skippedTicks uint64 // Ticks skipped due to game mode
	idleTicks    uint64
	flushCount   uint64
	eventsPushed uint64
	startTime    time.Time
}

// New creates a new monitor instance.
func New(db *sql.DB, redis *storage.RedisClient, config Config) *Monitor {
	return &Monitor{
		config: config,
		db:     db,
		redis:  redis,
		buf: buffer.New(buffer.BufferConfig{
			Capacity:      config.BufferCapacity,
			FlushTimeout:  config.FlushTimeout,
			IdleThreshold: config.IdleThreshold,
		}),
		state: State{
			LastTickTime: time.Now(),
		},
		startTime: time.Now(),
	}
}

// Start begins the main observation loop.
// Blocks until context is cancelled.
func (m *Monitor) Start(ctx context.Context) error {
	log.Printf("Starting monitor with tick interval: %v", m.config.TickInterval)

	ticker := time.NewTicker(m.config.TickInterval)
	defer ticker.Stop()

	// Start background flush handler
	flushDone := make(chan struct{})
	go m.flushHandler(ctx, flushDone)

	// Start stats logger (every 30 seconds)
	go m.statsLogger(ctx)

	// Main loop
	for {
		select {
		case <-ctx.Done():
			log.Println("Context cancelled, stopping monitor")
			m.flushHandlerStop()
			<-flushDone
			return m.shutdown()

		case <-ticker.C:
			m.tick()
		}
	}
}

// tick performs a single observation cycle.
// This function must complete in <10ms to maintain 0% CPU usage.
func (m *Monitor) tick() {
	m.tickCount++
	now := time.Now()

	// Step 1: Gaming Guard - Smart Full Stop
	// If a full-screen game is running, skip this tick entirely
	if isGame, err := win32.IsGameRunning(); err == nil && isGame {
		m.skippedTicks++
		return
	}

	// Step 2: Idle Check
	idleTime, err := win32.GetIdleTime()
	if err != nil {
		// Log error but continue
		log.Printf("Error getting idle time: %v", err)
		idleTime = 0
	}

	isIdle := idleTime >= uint32(m.config.IdleThreshold.Milliseconds())
	if isIdle {
		m.idleTicks++
	}

	// Step 3: Get current window info
	hwnd, err := win32.GetForegroundWindow()
	if err != nil {
		// No foreground window (e.g., workstation locked)
		// Skip this tick
		return
	}

	// Get window title
	windowTitle, err := win32.GetWindowText(hwnd)
	if err != nil {
		log.Printf("Error getting window text: %v", err)
		windowTitle = "Unknown"
	}

	// Get process ID
	_, pid, err := win32.GetWindowThreadProcessId(hwnd)
	if err != nil {
		log.Printf("Error getting process ID: %v", err)
		pid = 0
	}

	// Get process name from PID (simplified - in production would use proper lookup)
	processName := fmt.Sprintf("PID_%d", pid)

	// Step 4: Calculate input intensity score
	inputScore := m.calculateInputScore(isIdle)

	// Step 4.5: Screenshot Capture (Active Vision)
	var screenshotData []byte

	// Only capture if:
	// 1. Not idle (don't screenshot empty screens or screensavers)
	// 2. Interval passed (2s default)
	// 3. Not game mode (already checked above)
	if !isIdle && now.Sub(m.state.LastScreenshotTime) >= m.config.ScreenshotInterval {
		data, err := m.captureScreenshot(hwnd)
		if err != nil {
			// Log error periodically, don't spam
			if m.tickCount%50 == 0 {
				log.Printf("Screenshot failed: %v", err)
			}
		} else {
			screenshotData = data
			m.state.LastScreenshotTime = now
		}
	}
	// Step 5: Check if we should create a new entry
	m.mu.Lock()
	defer m.mu.Unlock()

	shouldLog := false

	// Log if:
	// 1. Window changed
	// 2. Window title changed
	// 3. Process changed
	// 4. Significant time passed (>5 seconds)
	// 5. Not idle and input activity detected

	// 4. Significant time passed (>5 seconds)
	// 5. Not idle and input activity detected
	// 6. Screenshot captured (visual change)

	windowChanged := m.state.LastWindowHandle != uintptr(hwnd)
	titleChanged := m.state.LastWindowTitle != windowTitle
	processChanged := m.state.LastProcessName != processName
	timePassed := now.Sub(m.state.LastTickTime) > 5*time.Second

	if windowChanged || titleChanged || processChanged || timePassed || (!isIdle && inputScore > 0.1) || len(screenshotData) > 0 {
		shouldLog = true
	}

	if shouldLog {
		entry := buffer.LogEntry{
			SessionUUID:    "default-session", // Will be replaced with proper UUID in production
			UnixTime:       now.UnixMilli(),
			ProcessName:    processName,
			WindowTitle:    windowTitle,
			WindowHandle:   int64(hwnd),
			InputIdleMs:    int64(idleTime),
			InputIntensity: inputScore,
			ScreenshotPath: "RAM", // Placeholder for legacy DB compatibility
			ScreenshotData: screenshotData,
		}

		// Add to buffer
		flushNeeded := m.buf.Add(entry)

		// Update state
		m.state.LastWindowHandle = uintptr(hwnd)
		m.state.LastWindowTitle = windowTitle
		m.state.LastProcessName = processName
		m.state.LastTickTime = now

		// Flush if buffer is full
		if flushNeeded {
			m.flush()
		}
	}
}

// calculateInputScore calculates a normalized input intensity score (0.0 to 1.0).
// This is a heuristic based on idle time and input tick changes.
func (m *Monitor) calculateInputScore(isIdle bool) float32 {
	if isIdle {
		return 0.0
	}

	// Get current input tick
	inputTick, err := win32.GetLastInputInfo()
	if err != nil {
		return 0.0
	}

	// Check if input tick changed since last tick
	m.mu.RLock()
	lastTick := m.state.LastInputTick
	m.mu.RUnlock()

	if inputTick == lastTick {
		// No new input
		return 0.0
	}

	// Update last input tick
	m.mu.Lock()
	m.state.LastInputTick = inputTick
	m.mu.Unlock()

	// Calculate score based on time since last input
	// Recent input = higher score
	idleTime, _ := win32.GetIdleTime()

	// Normalize: 0ms idle = 1.0, 5000ms idle = 0.0
	if idleTime >= 5000 {
		return 0.0
	}

	return 1.0 - float32(idleTime)/5000.0
}

// captureScreenshot captures the window content and returns JPEG bytes.
// Uses in-memory processing to avoid SSD writes (Ephemeral Vision).
func (m *Monitor) captureScreenshot(hwnd syscall.Handle) ([]byte, error) {
	// 1. Get Window Rect
	rect, err := win32.GetWindowRect(hwnd)
	if err != nil {
		return nil, err
	}

	// 2. Normalize coordinates
	width := int(rect.Right - rect.Left)
	height := int(rect.Bottom - rect.Top)

	if width <= 0 || height <= 0 {
		return nil, fmt.Errorf("invalid dimensions: %dx%d", width, height)
	}

	// 3. Capture
	img, err := screenshot.CaptureRect(image.Rect(int(rect.Left), int(rect.Top), int(rect.Right), int(rect.Bottom)))
	if err != nil {
		return nil, err
	}

	// 4. Encode to JPEG in memory
	var buf bytes.Buffer
	if err := jpeg.Encode(&buf, img, &jpeg.Options{Quality: 75}); err != nil {
		return nil, err
	}

	return buf.Bytes(), nil
}

// flushHandler handles periodic flushes from the buffer's flush channel.
func (m *Monitor) flushHandler(ctx context.Context, done chan<- struct{}) {
	defer close(done)

	for {
		select {
		case <-ctx.Done():
			return

		case <-m.buf.FlushChannel():
			m.flush()
		}
	}
}

// flushHandlerStop signals the flush handler to stop.
func (m *Monitor) flushHandlerStop() {
	// The flush handler will stop when context is cancelled
}

// flush performs a buffer flush to the database or Redis.
func (m *Monitor) flush() {
	// 1. Redis Mode (v4.0 Fast Path)
	if m.redis != nil {
		entries := m.buf.GetAndClear()
		if len(entries) == 0 {
			return
		}

		ctx := context.Background()
		pushed := 0

		for _, entry := range entries {
			// Convert to efficient map for JSON/MsgPack (or plain map for XADD)
			data := map[string]interface{}{
				"session_uuid":    entry.SessionUUID,
				"unix_time":       entry.UnixTime,
				"process_name":    entry.ProcessName,
				"window_title":    entry.WindowTitle,
				"window_hwnd":     entry.WindowHandle,
				"input_idle":      entry.InputIdleMs,
				"intensity":       entry.InputIntensity,
				"screenshot_path": entry.ScreenshotPath, // "RAM"
			}

			// Attach image data if present
			if len(entry.ScreenshotData) > 0 {
				data["image_data"] = base64.StdEncoding.EncodeToString(entry.ScreenshotData)
			}

			if err := m.redis.PublishEvent(ctx, "mnemosyne:events", data); err != nil {
				log.Printf("Error publishing to Redis: %v", err)
			} else {
				pushed++
			}
		}

		if pushed > 0 {
			m.flushCount++
			m.eventsPushed += uint64(pushed)
		}
		return
	}

	// 2. SQLite Mode (Legacy)
	err := m.buf.Flush(m.db)
	if err != nil {
		log.Printf("Error flushing buffer: %v", err)
		return
	}

	m.flushCount++
}

// shutdown performs graceful shutdown by flushing remaining data.
func (m *Monitor) shutdown() error {
	log.Println("Performing graceful shutdown...")

	// Force flush any remaining data
	err := m.buf.ForceFlush(m.db)
	if err != nil {
		log.Printf("Error during final flush: %v", err)
		return err
	}

	m.buf.Stop()

	// Print statistics
	log.Printf("Shutdown statistics:")
	log.Printf("  Total ticks: %d", m.tickCount)
	log.Printf("  Skipped ticks (game mode): %d", m.skippedTicks)
	log.Printf("  Idle ticks: %d", m.idleTicks)
	log.Printf("  Flushes performed: %d", m.flushCount)

	return nil
}

// GetStats returns current monitor statistics.
func (m *Monitor) GetStats() map[string]interface{} {
	m.mu.RLock()
	defer m.mu.RUnlock()

	return map[string]interface{}{
		"tick_count":        m.tickCount,
		"skipped_ticks":     m.skippedTicks,
		"idle_ticks":        m.idleTicks,
		"flush_count":       m.flushCount,
		"buffer_entries":    m.buf.Len(),
		"buffer_size_bytes": m.buf.Size(),
		"last_flush":        m.buf.LastFlush(),
		"current_window":    m.state.LastWindowTitle,
		"current_process":   m.state.LastProcessName,
	}
}

// GetBuffer returns the buffer for testing purposes.
func (m *Monitor) GetBuffer() *buffer.Buffer {
	return m.buf
}

// statsLogger periodically logs monitoring statistics.
func (m *Monitor) statsLogger(ctx context.Context) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			m.logStats()
		}
	}
}

// logStats logs current monitoring statistics.
func (m *Monitor) logStats() {
	m.mu.RLock()
	tickCount := m.tickCount
	skippedTicks := m.skippedTicks
	idleTicks := m.idleTicks
	flushCount := m.flushCount
	eventsPushed := m.eventsPushed
	m.mu.RUnlock()

	// Memory stats
	var memStats runtime.MemStats
	runtime.ReadMemStats(&memStats)
	allocMB := float64(memStats.Alloc) / 1024 / 1024
	sysMB := float64(memStats.Sys) / 1024 / 1024

	// Buffer stats
	bufferLen := m.buf.Len()
	bufferSize := m.buf.Size()

	// Uptime
	uptime := time.Since(m.startTime).Round(time.Second)

	// Log formatted stats
	log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Printf("📊 WATCHER STATS | Uptime: %s", uptime)
	log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Printf("🔄 Ticks: %d total | %d idle | %d skipped (games)", tickCount, idleTicks, skippedTicks)
	log.Printf("💾 Buffer: %d entries | %d bytes", bufferLen, bufferSize)

	if m.redis != nil {
		log.Printf("🚀 Redis: %d events pushed | %d flushes", eventsPushed, flushCount)
	} else {
		// Legacy DB counts
		var totalEvents, pendingEvents int64
		row := m.db.QueryRow("SELECT COUNT(*) FROM raw_events")
		if err := row.Scan(&totalEvents); err != nil {
			totalEvents = -1
		}
		row = m.db.QueryRow("SELECT COUNT(*) FROM raw_events WHERE is_processed = 0")
		if err := row.Scan(&pendingEvents); err != nil {
			pendingEvents = -1
		}
		log.Printf("📁 Database: %d events | %d pending | %d flushes", totalEvents, pendingEvents, flushCount)
	}

	log.Printf("🧠 RAM: %.1f MB used | %.1f MB sys", allocMB, sysMB)
	log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
}
