// Package storage_test содержит тесты для модуля storage
// Mnemosyne Core V3.0 - Tier 0: Database Layer Tests
package storage_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"mnemosyne/internal/storage"
)

func TestInitDB(t *testing.T) {
	// Создаем временный файл для тестовой базы данных
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test_mnemosyne.db")

	// Инициализируем базу данных
	db, err := storage.InitDB(dbPath)
	require.NoError(t, err, "InitDB должен успешно создать базу данных")
	require.NotNil(t, db, "База данных не должна быть nil")
	defer storage.CloseDB(db)

	// Проверяем, что файл базы данных создан
	_, err = os.Stat(dbPath)
	require.NoError(t, err, "Файл базы данных должен существовать")

	// Проверяем, что WAL файл создан (признак работы WAL режима)
	walPath := dbPath + "-wal"
	_, err = os.Stat(walPath)
	require.NoError(t, err, "WAL файл должен существовать при включенном WAL режиме")
}

func TestInitDB_PRAGMAs(t *testing.T) {
	// Создаем временную базу данных
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test_pragmas.db")

	db, err := storage.InitDB(dbPath)
	require.NoError(t, err)
	defer storage.CloseDB(db)

	// Проверяем journal_mode = WAL
	var journalMode string
	err = db.QueryRow("PRAGMA journal_mode;").Scan(&journalMode)
	require.NoError(t, err)
	assert.Equal(t, "wal", journalMode, "journal_mode должен быть 'wal'")

	// Проверяем synchronous = NORMAL
	var synchronous string
	err = db.QueryRow("PRAGMA synchronous;").Scan(&synchronous)
	require.NoError(t, err)
	assert.Equal(t, "1", synchronous, "synchronous должен быть 1 (NORMAL)")

	// Проверяем temp_store = MEMORY
	var tempStore string
	err = db.QueryRow("PRAGMA temp_store;").Scan(&tempStore)
	require.NoError(t, err)
	assert.Equal(t, "2", tempStore, "temp_store должен быть 2 (MEMORY)")

	// Проверяем busy_timeout = 5000
	var busyTimeout int
	err = db.QueryRow("PRAGMA busy_timeout;").Scan(&busyTimeout)
	require.NoError(t, err)
	assert.Equal(t, 5000, busyTimeout, "busy_timeout должен быть 5000 мс")

	// Проверяем mmap_size = 268435456 (256MB)
	var mmapSize int
	err = db.QueryRow("PRAGMA mmap_size;").Scan(&mmapSize)
	require.NoError(t, err)
	assert.Equal(t, 268435456, mmapSize, "mmap_size должен быть 268435456 (256MB)")
}

func TestInitDB_TablesCreated(t *testing.T) {
	// Создаем временную базу данных
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test_tables.db")

	db, err := storage.InitDB(dbPath)
	require.NoError(t, err)
	defer storage.CloseDB(db)

	// Проверяем существование таблицы raw_events
	var tableName string
	err = db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='table' AND name='raw_events';",
	).Scan(&tableName)
	require.NoError(t, err, "Таблица raw_events должна существовать")
	assert.Equal(t, "raw_events", tableName)

	// Проверяем существование таблицы context_enrichment
	err = db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='table' AND name='context_enrichment';",
	).Scan(&tableName)
	require.NoError(t, err, "Таблица context_enrichment должна существовать")
	assert.Equal(t, "context_enrichment", tableName)

	// Проверяем существование виртуальной таблицы fts_search
	err = db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='table' AND name='fts_search';",
	).Scan(&tableName)
	require.NoError(t, err, "Виртуальная таблица fts_search должна существовать")
	assert.Equal(t, "fts_search", tableName)
}

func TestInitDB_IndexesCreated(t *testing.T) {
	// Создаем временную базу данных
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test_indexes.db")

	db, err := storage.InitDB(dbPath)
	require.NoError(t, err)
	defer storage.CloseDB(db)

	// Проверяем существование индекса idx_raw_time
	var indexName string
	err = db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='index' AND name='idx_raw_time';",
	).Scan(&indexName)
	require.NoError(t, err, "Индекс idx_raw_time должен существовать")
	assert.Equal(t, "idx_raw_time", indexName)

	// Проверяем существование индекса idx_raw_processed
	err = db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='index' AND name='idx_raw_processed';",
	).Scan(&indexName)
	require.NoError(t, err, "Индекс idx_raw_processed должен существовать")
	assert.Equal(t, "idx_raw_processed", indexName)

	// Проверяем существование индекса idx_raw_session
	err = db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='index' AND name='idx_raw_session';",
	).Scan(&indexName)
	require.NoError(t, err, "Индекс idx_raw_session должен существовать")
	assert.Equal(t, "idx_raw_session", indexName)

	// Проверяем существование индекса idx_raw_process
	err = db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='index' AND name='idx_raw_process';",
	).Scan(&indexName)
	require.NoError(t, err, "Индекс idx_raw_process должен существовать")
	assert.Equal(t, "idx_raw_process", indexName)
}

func TestInitDB_TriggersCreated(t *testing.T) {
	// Создаем временную базу данных
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test_triggers.db")

	db, err := storage.InitDB(dbPath)
	require.NoError(t, err)
	defer storage.CloseDB(db)

	// Проверяем существование триггера trg_fts_insert
	var triggerName string
	err = db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='trigger' AND name='trg_fts_insert';",
	).Scan(&triggerName)
	require.NoError(t, err, "Триггер trg_fts_insert должен существовать")
	assert.Equal(t, "trg_fts_insert", triggerName)

	// Проверяем существование триггера trg_fts_update
	err = db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='trigger' AND name='trg_fts_update';",
	).Scan(&triggerName)
	require.NoError(t, err, "Триггер trg_fts_update должен существовать")
	assert.Equal(t, "trg_fts_update", triggerName)

	// Проверяем существование триггера trg_fts_delete
	err = db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='trigger' AND name='trg_fts_delete';",
	).Scan(&triggerName)
	require.NoError(t, err, "Триггер trg_fts_delete должен существовать")
	assert.Equal(t, "trg_fts_delete", triggerName)
}

func TestInitDB_ForeignKeyConstraints(t *testing.T) {
	// Создаем временную базу данных
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test_fkeys.db")

	db, err := storage.InitDB(dbPath)
	require.NoError(t, err)
	defer storage.CloseDB(db)

	// Проверяем, что внешние ключи включены
	// modernc.org/sqlite возвращает строковое значение
	var foreignKeys string
	err = db.QueryRow("PRAGMA foreign_keys;").Scan(&foreignKeys)
	require.NoError(t, err)
	assert.Equal(t, "1", foreignKeys, "Внешние ключи должны быть включены")

	// Проверяем CASCADE удаление при удалении записи из raw_events
	// Вставляем тестовую запись в raw_events
	_, err = db.Exec(`
		INSERT INTO raw_events (
			session_uuid, timestamp_utc, unix_time,
			process_name, window_title, window_hwnd
		) VALUES (?, ?, ?, ?, ?, ?)`,
		"test-session-uuid", "2024-01-01T00:00:00Z", 1704067200,
		"test.exe", "Test Window", 12345,
	)
	require.NoError(t, err)

	// Получаем ID вставленной записи
	var eventID int64
	err = db.QueryRow("SELECT last_insert_rowid();").Scan(&eventID)
	require.NoError(t, err)

	// Вставляем связанную запись в context_enrichment
	_, err = db.Exec(`
		INSERT INTO context_enrichment (event_id, ocr_content)
		VALUES (?, ?)`,
		eventID, "Test OCR content",
	)
	require.NoError(t, err)

	// Проверяем, что запись в context_enrichment существует
	var count int
	err = db.QueryRow("SELECT COUNT(*) FROM context_enrichment WHERE event_id = ?;", eventID).Scan(&count)
	require.NoError(t, err)
	assert.Equal(t, 1, count, "Запись в context_enrichment должна существовать")

	// Удаляем запись из raw_events (должен сработать CASCADE)
	_, err = db.Exec("DELETE FROM raw_events WHERE id = ?;", eventID)
	require.NoError(t, err)

	// Проверяем, что запись в context_enrichment удалена
	err = db.QueryRow("SELECT COUNT(*) FROM context_enrichment WHERE event_id = ?;", eventID).Scan(&count)
	require.NoError(t, err)
	assert.Equal(t, 0, count, "Запись в context_enrichment должна быть удалена (CASCADE)")
}

func TestInitDB_FTSIntegration(t *testing.T) {
	// Создаем временную базу данных
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test_fts.db")

	db, err := storage.InitDB(dbPath)
	require.NoError(t, err)
	defer storage.CloseDB(db)

	// Вставляем тестовые данные
	_, err = db.Exec(`
		INSERT INTO raw_events (
			session_uuid, timestamp_utc, unix_time,
			process_name, window_title, window_hwnd
		) VALUES (?, ?, ?, ?, ?, ?)`,
		"test-session-uuid", "2024-01-01T00:00:00Z", 1704067200,
		"test.exe", "Test Window Title", 12345,
	)
	require.NoError(t, err)

	var eventID int64
	err = db.QueryRow("SELECT last_insert_rowid();").Scan(&eventID)
	require.NoError(t, err)

	// Вставляем данные в context_enrichment (должен сработать триггер trg_fts_insert)
	_, err = db.Exec(`
		INSERT INTO context_enrichment (
			event_id, ocr_content, vlm_description, user_intent
		) VALUES (?, ?, ?, ?)`,
		eventID, "OCR content from screen", "Visual scene description", "User wants to search",
	)
	require.NoError(t, err)

	// Проверяем, что данные попали в FTS таблицу
	var ftsCount int
	err = db.QueryRow("SELECT COUNT(*) FROM fts_search WHERE rowid = ?;", eventID).Scan(&ftsCount)
	require.NoError(t, err)
	assert.Equal(t, 1, ftsCount, "Запись должна быть в FTS таблице")

	// Проверяем полнотекстовый поиск
	var matchCount int
	err = db.QueryRow(`
		SELECT COUNT(*) FROM fts_search 
		WHERE fts_search MATCH 'search';
	`).Scan(&matchCount)
	require.NoError(t, err)
	assert.Equal(t, 1, matchCount, "Полнотекстовый поиск должен находить записи")

	// Обновляем запись в context_enrichment (должен сработать триггер trg_fts_update)
	_, err = db.Exec(`
		UPDATE context_enrichment 
		SET user_intent = 'Updated user intent' 
		WHERE event_id = ?;
	`, eventID)
	require.NoError(t, err)

	// Проверяем, что данные обновились в FTS таблице
	var userIntent string
	err = db.QueryRow(`
		SELECT user_intent FROM fts_search WHERE rowid = ?;
	`, eventID).Scan(&userIntent)
	require.NoError(t, err)
	assert.Equal(t, "Updated user intent", userIntent, "Данные должны быть обновлены в FTS таблице")

	// Удаляем запись из context_enrichment (должен сработать триггер trg_fts_delete)
	_, err = db.Exec("DELETE FROM context_enrichment WHERE event_id = ?;", eventID)
	require.NoError(t, err)

	// Проверяем, что запись удалена из FTS таблицы
	err = db.QueryRow("SELECT COUNT(*) FROM fts_search WHERE rowid = ?;", eventID).Scan(&ftsCount)
	require.NoError(t, err)
	assert.Equal(t, 0, ftsCount, "Запись должна быть удалена из FTS таблицы")
}

func TestInitDB_ReopenExistingDB(t *testing.T) {
	// Создаем временную базу данных
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test_reopen.db")

	// Первая инициализация
	db1, err := storage.InitDB(dbPath)
	require.NoError(t, err)
	storage.CloseDB(db1)

	// Вторая инициализация (повторное открытие существующей базы)
	db2, err := storage.InitDB(dbPath)
	require.NoError(t, err)
	defer storage.CloseDB(db2)

	// Проверяем, что WAL режим все еще активен
	var journalMode string
	err = db2.QueryRow("PRAGMA journal_mode;").Scan(&journalMode)
	require.NoError(t, err)
	assert.Equal(t, "wal", journalMode, "WAL режим должен сохраняться при повторном открытии")

	// Проверяем, что таблицы существуют
	var tableName string
	err = db2.QueryRow(
		"SELECT name FROM sqlite_master WHERE type='table' AND name='raw_events';",
	).Scan(&tableName)
	require.NoError(t, err)
	assert.Equal(t, "raw_events", tableName)
}

func TestCloseDB(t *testing.T) {
	// Создаем временную базу данных
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test_close.db")

	db, err := storage.InitDB(dbPath)
	require.NoError(t, err)

	// Закрываем базу данных
	err = storage.CloseDB(db)
	require.NoError(t, err, "CloseDB не должен возвращать ошибку")

	// Проверяем, что соединение закрыто (Ping должен вернуть ошибку)
	err = db.Ping()
	assert.Error(t, err, "Ping должен возвращать ошибку после закрытия соединения")
	// modernc.org/sqlite возвращает "sql: database is closed" вместо "sql: connection is already closed"
	assert.Contains(t, err.Error(), "closed", "Ожидается ошибка закрытого соединения")

	// Закрытие nil базы данных не должно вызывать панику
	err = storage.CloseDB(nil)
	require.NoError(t, err, "CloseDB(nil) не должен возвращать ошибку")
}
