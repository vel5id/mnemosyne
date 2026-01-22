// Mnemosyne Core V3.0 - Tier 1: The Watcher
// Main entry point for the activity monitoring daemon.
// Implements graceful shutdown with SIGTERM/SIGINT handling.
package main

import (
	"context"
	"database/sql"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	_ "modernc.org/sqlite"

	"mnemosyne/internal/monitor"
	"mnemosyne/internal/storage"
)

const (
	// Version is the application version
	Version = "4.0.0-rc1" // Bump version for v4.0

	// Default database path
	defaultDBPath = ".mnemosyne/activity.db"
)

// Config holds the application configuration.
type Config struct {
	DBPath         string
	RedisAddr      string // New: Redis Address
	TickInterval   time.Duration
	IdleThreshold  time.Duration
	BufferCapacity int
	FlushTimeout   time.Duration
}

func main() {
	log.Printf("Mnemosyne Core Watcher v%s starting...", Version)

	// Parse command line flags
	config := parseFlags()

	// Ensure data directory exists
	if err := ensureDataDir(config.DBPath); err != nil {
		log.Fatalf("Failed to create data directory: %v", err)
	}

	// Initialize database (Legacy/Fallback)
	db, err := initDatabase(config.DBPath)
	if err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}
	defer db.Close()

	// Initialize Redis (Primary for v4.0)
	var redisClient *storage.RedisClient
	if config.RedisAddr != "" {
		rc, err := storage.NewRedisClient(config.RedisAddr, "", 0)
		if err != nil {
			log.Fatalf("Failed to connect to Redis at %s: %v", config.RedisAddr, err)
		}
		redisClient = rc
		defer redisClient.Close()
		log.Printf("Redis connected: %s", config.RedisAddr)
	}

	// Create monitor
	monitorConfig := monitor.Config{
		TickInterval:   config.TickInterval,
		IdleThreshold:  config.IdleThreshold,
		BufferCapacity: config.BufferCapacity,
		FlushTimeout:   config.FlushTimeout,
	}

	watcher := monitor.New(db, redisClient, monitorConfig)

	// Setup graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Signal handling for graceful shutdown
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	// Start monitor in a goroutine
	monitorDone := make(chan error, 1)
	go func() {
		monitorDone <- watcher.Start(ctx)
	}()

	log.Println("Watcher started. Press Ctrl+C to stop gracefully.")

	// Wait for shutdown signal
	select {
	case sig := <-stop:
		log.Printf("Received signal %v, initiating graceful shutdown...", sig)
		cancel()

	case err := <-monitorDone:
		if err != nil {
			log.Printf("Monitor stopped with error: %v", err)
			os.Exit(1)
		}
		log.Println("Monitor stopped normally")
		os.Exit(0)
	}

	// Wait for monitor to complete shutdown
	select {
	case err := <-monitorDone:
		if err != nil {
			log.Printf("Shutdown completed with error: %v", err)
			os.Exit(1)
		}
		log.Println("Shutdown completed successfully")
		os.Exit(0)

	case <-time.After(30 * time.Second):
		log.Println("Shutdown timeout exceeded, forcing exit")
		os.Exit(1)
	}
}

// parseFlags parses command line flags and returns configuration.
func parseFlags() Config {
	dbPath := flag.String("db", defaultDBPath, "Path to SQLite database file")
	redisAddr := flag.String("redis", "", "Redis address (e.g., localhost:6379)")
	tickInterval := flag.Duration("tick", 1000*time.Millisecond, "Tick interval (e.g., 1000ms for 1Hz)")
	idleThreshold := flag.Duration("idle", 60*time.Second, "Idle threshold before marking as idle")
	bufferCapacity := flag.Int("buffer", 100, "Buffer capacity before forced flush")
	flushTimeout := flag.Duration("flush", 5*time.Minute, "Time between automatic flushes")

	flag.Parse()

	return Config{
		DBPath:         *dbPath,
		RedisAddr:      *redisAddr,
		TickInterval:   *tickInterval,
		IdleThreshold:  *idleThreshold,
		BufferCapacity: *bufferCapacity,
		FlushTimeout:   *flushTimeout,
	}
}

// ensureDataDir ensures the data directory exists.
func ensureDataDir(dbPath string) error {
	dir := filepath.Dir(dbPath)
	if dir == "." {
		return nil
	}

	return os.MkdirAll(dir, 0755)
}

// initDatabase initializes the SQLite database with proper configuration.
func initDatabase(dbPath string) (*sql.DB, error) {
	// Open database connection
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// Configure SQLite for optimal performance and SSD protection
	pragmas := []string{
		"PRAGMA journal_mode = DELETE", // Uses rollback journal (safer for Windows+Docker bind mounts)
		"PRAGMA synchronous = NORMAL",  // Balance between safety and performance
		"PRAGMA temp_store = MEMORY",   // Store temp tables in RAM
		"PRAGMA mmap_size = 268435456", // 256MB memory-mapped I/O
		"PRAGMA busy_timeout = 5000",   // Wait 5 seconds on lock
		"PRAGMA foreign_keys = ON",     // Enable foreign keys
	}

	for _, pragma := range pragmas {
		if _, err := db.Exec(pragma); err != nil {
			return nil, fmt.Errorf("failed to set pragma %q: %w", pragma, err)
		}
	}

	// Verify connection works
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	log.Printf("Database initialized: %s", dbPath)
	return db, nil
}
