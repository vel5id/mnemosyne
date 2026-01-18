// Package storage предоставляет интерфейс для работы с SQLite базой данных
// Mnemosyne Core V3.0 - Tier 0: Database Layer
// Документация: docs/04_SQL_Schema.md
package storage

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"

	_ "modernc.org/sqlite"
)

const (
	// schemaFile - путь к файлу с DDL схемой базы данных (относительно корня проекта)
	schemaFile = "db/schema.sql"
)

// InitDB инициализирует соединение с SQLite базой данных и применяет схему.
//
// Критически важные PRAGMA настройки для производительности и надежности:
//   - journal_mode=WAL: Позволяет одновременное чтение (Python) и запись (Go)
//   - synchronous=NORMAL: Буферизация записи для защиты SSD
//   - temp_store=MEMORY: Временные таблицы в RAM (80GB доступно)
//   - busy_timeout=5000: Таймаут ожидания при блокировке (5 сек)
//
// Параметр path - путь к файлу базы данных (например, "data/mnemosyne.db")
//
// Возвращает *sql.DB и ошибку, если инициализация не удалась.
func InitDB(path string) (*sql.DB, error) {
	// Убеждаемся, что директория для базы данных существует
	dbDir := filepath.Dir(path)
	if dbDir != "." && dbDir != "" {
		if err := os.MkdirAll(dbDir, 0755); err != nil {
			return nil, fmt.Errorf("failed to create database directory: %w", err)
		}
	}

	// Открываем соединение с SQLite
	// DSN параметры:
	//   - _foreign_keys=on: Включаем внешние ключи
	//   - _mutex=noop: Отключаем встроенный мьютекс SQLite (Go управляет конкурентностью)
	dsn := fmt.Sprintf("file:%s?_foreign_keys=on&_mutex=noop", path)
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// Проверяем соединение
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	// Применяем критические PRAGMA настройки
	pragmas := []struct {
		name  string
		value string
	}{
		{"journal_mode", "WAL"},
		{"synchronous", "NORMAL"},
		{"temp_store", "MEMORY"},
		{"busy_timeout", "5000"},
		{"mmap_size", "268435456"}, // 256MB
	}

	for _, pragma := range pragmas {
		if _, err := db.Exec(fmt.Sprintf("PRAGMA %s = %s;", pragma.name, pragma.value)); err != nil {
			db.Close()
			return nil, fmt.Errorf("failed to set PRAGMA %s=%s: %w", pragma.name, pragma.value, err)
		}
	}

	// Ограничиваем количество открытых соединений до 1
	// Это критически важно для предотвращения блокировок при записи
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)

	// Применяем схему базы данных из файла
	if err := applySchema(db); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to apply schema: %w", err)
	}

	return db, nil
}

// applySchema читает DDL из файла schema.sql и применяет его к базе данных.
func applySchema(db *sql.DB) error {
	// Ищем корень проекта через go.mod файл
	wd, err := os.Getwd()
	if err != nil {
		return fmt.Errorf("failed to get working directory: %w", err)
	}

	// Поднимаемся вверх по директориям пока не найдем go.mod
	rootDir := wd
	for {
		if _, err := os.Stat(filepath.Join(rootDir, "go.mod")); err == nil {
			break
		}
		parent := filepath.Dir(rootDir)
		if parent == rootDir {
			// Дошли до корня файловой системы
			return fmt.Errorf("failed to find project root (go.mod not found)")
		}
		rootDir = parent
	}

	// Формируем полный путь к файлу схемы
	schemaPath := filepath.Join(rootDir, schemaFile)

	// Читаем содержимое файла схемы
	schemaContent, err := os.ReadFile(schemaPath)
	if err != nil {
		return fmt.Errorf("failed to read schema file %s: %w", schemaPath, err)
	}

	// Применяем схему
	// SQLite выполняет DDL как транзакцию автоматически
	if _, err := db.Exec(string(schemaContent)); err != nil {
		return fmt.Errorf("failed to execute schema: %w", err)
	}

	return nil
}

// CloseDB безопасно закрывает соединение с базой данных.
func CloseDB(db *sql.DB) error {
	if db == nil {
		return nil
	}
	return db.Close()
}
