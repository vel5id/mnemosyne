# Go Module Configuration (go.mod)

Содержимое для `go.mod`:

```go
module github.com/mnemosyne/core

go 1.22

require (
	github.com/mattn/go-sqlite3 v1.14.22
	gopkg.in/natefinch/lumberjack.v2 v2.2.1
	golang.org/x/sys v0.20.0
)

require (
	github.com/google/uuid v1.6.0 // indirect
	golang.org/x/text v0.15.0 // indirect
)
```

**Зависимости:**
- `github.com/mattn/go-sqlite3` - драйвер SQLite с поддержкой CGO
- `gopkg.in/natefinch/lumberjack.v2` - ротация логов для CSV
- `golang.org/x/sys` - низкоуровневые системные вызовы Windows
