/**
 * Mnemosyne Core V3.0 - Tier 3: The View
 * Unit Tests for JS Logic
 * 
 * Тесты для "чистых" функций, которые не зависят от Obsidian API.
 * Могут быть запущены в Node.js или любом JS тест-раннере.
 * 
 * Запуск тестов:
 * node tests/js/test_view_logic.js
 */

// Простая тестовая утилита
class TestRunner {
    constructor() {
        this.tests = [];
        this.passed = 0;
        this.failed = 0;
    }
    
    test(name, fn) {
        this.tests.push({ name, fn });
    }
    
    async run() {
        console.log('🧪 Running Mnemosyne View Logic Tests\n');
        
        for (const { name, fn } of this.tests) {
            try {
                await fn();
                this.passed++;
                console.log(`✅ ${name}`);
            } catch (error) {
                this.failed++;
                console.log(`❌ ${name}`);
                console.log(`   Error: ${error.message}`);
            }
        }
        
        console.log('\n' + '='.repeat(50));
        console.log(`Total: ${this.tests.length} | Passed: ${this.passed} | Failed: ${this.failed}`);
        console.log('='.repeat(50));
        
        return this.failed === 0;
    }
    
    assertEqual(actual, expected, message = '') {
        if (actual !== expected) {
            throw new Error(`${message}\nExpected: ${expected}\nActual: ${actual}`);
        }
    }
    
    assertMatch(actual, pattern, message = '') {
        if (!pattern.test(actual)) {
            throw new Error(`${message}\nExpected to match: ${pattern}\nActual: ${actual}`);
        }
    }
    
    assertNotMatch(actual, pattern, message = '') {
        if (pattern.test(actual)) {
            throw new Error(`${message}\nExpected NOT to match: ${pattern}\nActual: ${actual}`);
        }
    }
    
    assertArrayEqual(actual, expected, message = '') {
        if (JSON.stringify(actual) !== JSON.stringify(expected)) {
            throw new Error(`${message}\nExpected: ${JSON.stringify(expected)}\nActual: ${JSON.stringify(actual)}`);
        }
    }
}

// ============================================================================
// ТЕСТЫ ДЛЯ ФОРМАТИРОВАНИЯ ДЛИТЕЛЬНОСТИ
// ============================================================================

/**
 * Форматирует длительность в человеко-читаемый формат
 */
function formatDuration(ms) {
    if (!ms || ms < 0) return '0м';
    
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) {
        const mins = minutes % 60;
        return `${hours}ч ${mins}м`;
    } else if (minutes > 0) {
        const secs = seconds % 60;
        return secs > 0 ? `${minutes}м ${secs}с` : `${minutes}м`;
    } else if (seconds > 0) {
        return `${seconds}с`;
    } else {
        return '0м';
    }
}

// ============================================================================
// ТЕСТЫ ДЛЯ ФОРМАТИРОВАНИЯ ВРЕМЕНИ
// ============================================================================

/**
 * Форматирует время из ISO строки
 */
function formatTime(isoString) {
    try {
        if (!isoString) return '--:--';
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return '--:--';
        const hours = String(date.getUTCHours()).padStart(2, '0');
        const minutes = String(date.getUTCMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
    } catch (error) {
        return '--:--';
    }
}

// ============================================================================
// ТЕСТЫ ДЛЯ CSV ПАРСИНГА
// ============================================================================

/**
 * Парсит CSV строку в массив значений
 * Учитывает кавычки и экранирование
 */
function parseCSVLine(line) {
    const result = [];
    let current = '';
    let inQuotes = false;
    
    for (let i = 0; i < line.length; i++) {
        const char = line[i];
        const nextChar = line[i + 1];
        
        if (char === '"') {
            if (inQuotes && nextChar === '"') {
                current += '"';
                i++;
            } else {
                inQuotes = !inQuotes;
            }
        } else if (char === ',' && !inQuotes) {
            result.push(current.trim());
            current = '';
        } else {
            current += char;
        }
    }
    result.push(current.trim());
    return result;
}

/**
 * Парсит CSV контент в массив объектов
 */
function parseCSV(csvContent) {
    const lines = csvContent.trim().split('\n');
    if (lines.length < 2) return [];
    
    const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
    const result = [];
    
    for (let i = 1; i < lines.length; i++) {
        const values = parseCSVLine(lines[i]);
        if (values.length !== headers.length) continue;
        
        const obj = {};
        headers.forEach((header, index) => {
            obj[header] = values[index];
        });
        result.push(obj);
    }
    
    return result;
}

// ============================================================================
// ТЕСТЫ ДЛЯ JSONL ПАРСИНГА
// ============================================================================

/**
 * Парсит JSONL (JSON Lines) файл
 */
function parseJSONL(jsonlContent) {
    const lines = jsonlContent.trim().split('\n');
    const result = [];
    
    for (const line of lines) {
        try {
            const obj = JSON.parse(line);
            result.push(obj);
        } catch (error) {
            // Игнорируем некорректные строки
        }
    }
    
    return result;
}

// ============================================================================
// ТЕСТЫ ДЛЯ SANITIZE DISPLAY (Defense in Depth)
// ============================================================================

/**
 * Санитизация текста перед выводом
 * Маскирует PII на случай ошибки в Python-слое
 */
function sanitizeDisplay(text) {
    if (typeof text !== 'string') return text;
    
    let sanitized = text;
    
    // Email адреса
    sanitized = sanitized.replace(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g, '***@***.***');
    
    // Кредитные карты (Visa, MasterCard, Amex)
    sanitized = sanitized.replace(/\b(?:\d[ -]*?){13,16}\b/g, '****-****-****-****');
    
    // API ключи (sk-..., pk-...)
    sanitized = sanitized.replace(/\b(sk|pk|api)[a-zA-Z0-9_-]{20,}\b/gi, '***API_KEY***');
    
    // Телефонные номера
    sanitized = sanitized.replace(/\b\+?[\d\s-()]{10,}\b/g, '***-***-****');
    
    // IP адреса
    sanitized = sanitized.replace(/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g, '***.***.***.***');
    
    // SSN (Social Security Number)
    sanitized = sanitized.replace(/\b\d{3}-\d{2}-\d{4}\b/g, '***-***-****');
    
    return sanitized;
}

// ============================================================================
// ТЕСТЫ ДЛЯ ГЕНЕРАЦИИ MERMAID
// ============================================================================

/**
 * Генерирует диаграмму Mermaid Gantt для Timeline
 */
function generateMermaidTimeline(events, options = {}) {
    const { title = 'Activity Timeline' } = options;
    
    if (events.length === 0) {
        return `gantt\n    title ${title}\n    dateFormat HH:mm\n    axisFormat %H:%M\n    section No Data\n    No activity recorded :done, 00:00, 1m`;
    }
    
    let mermaid = `gantt\n    title ${sanitizeDisplay(title)}\n`;
    mermaid += `    dateFormat HH:mm\n`;
    mermaid += `    axisFormat %H:%M\n`;
    
    // Группируем по приложениям
    const appGroups = {};
    events.forEach(event => {
        const app = sanitizeDisplay(event.app_name || 'Unknown');
        if (!appGroups[app]) {
            appGroups[app] = [];
        }
        appGroups[app].push(event);
    });
    
    // Генерируем секции для каждого приложения
    for (const [appName, appEvents] of Object.entries(appGroups)) {
        mermaid += `    section ${appName}\n`;
        
        for (const event of appEvents) {
            const startTime = formatTime(event.timestamp);
            const durationMinutes = Math.max(1, Math.round((event.duration_ms || 0) / 60000));
            const intent = sanitizeDisplay(event.intent || event.intent_summary || 'Activity');
            
            const shortIntent = intent.length > 30 ? intent.substring(0, 27) + '...' : intent;
            
            mermaid += `    ${shortIntent} :${startTime}, ${durationMinutes}m\n`;
        }
    }
    
    return mermaid;
}

// ============================================================================
// ЗАПУСК ТЕСТОВ
// ============================================================================

async function runTests() {
    const runner = new TestRunner();
    
    // ==================== CSV Parsing Tests ====================
    runner.test('CSV: Parse simple line', () => {
        const result = parseCSVLine('app_name,intent,duration');
        runner.assertArrayEqual(result, ['app_name', 'intent', 'duration'], 'Simple CSV line parsing');
    });
    
    runner.test('CSV: Parse line with quotes', () => {
        const result = parseCSVLine('"app name","intent text",123');
        runner.assertArrayEqual(result, ['app name', 'intent text', '123'], 'CSV with quotes');
    });
    
    runner.test('CSV: Parse full CSV content', () => {
        const csv = 'app_name,intent,duration\n"Visual Studio","Writing code",3600000\nChrome,"Reading docs",1800000';
        const result = parseCSV(csv);
        runner.assertEqual(result.length, 2, 'CSV should have 2 records');
        runner.assertEqual(result[0].app_name, 'Visual Studio', 'First record app_name');
        runner.assertEqual(result[1].intent, 'Reading docs', 'Second record intent');
    });
    
    runner.test('CSV: Handle escaped quotes', () => {
        const result = parseCSVLine('"text with ""quotes""",other');
        runner.assertArrayEqual(result, ['text with "quotes"', 'other'], 'Escaped quotes');
    });
    
    // ==================== JSONL Parsing Tests ====================
    runner.test('JSONL: Parse single line', () => {
        const jsonl = '{"app_name":"Chrome","intent":"Browsing"}';
        const result = parseJSONL(jsonl);
        runner.assertEqual(result.length, 1, 'JSONL should have 1 record');
        runner.assertEqual(result[0].app_name, 'Chrome', 'App name');
    });
    
    runner.test('JSONL: Parse multiple lines', () => {
        const jsonl = '{"app":"Chrome","intent":"Browsing"}\n{"app":"VSCode","intent":"Coding"}';
        const result = parseJSONL(jsonl);
        runner.assertEqual(result.length, 2, 'JSONL should have 2 records');
        runner.assertEqual(result[1].app, 'VSCode', 'Second record app');
    });
    
    runner.test('JSONL: Skip invalid lines', () => {
        const jsonl = '{"app":"Chrome"}\ninvalid json\n{"app":"VSCode"}';
        const result = parseJSONL(jsonl);
        runner.assertEqual(result.length, 2, 'JSONL should skip invalid lines');
    });
    
    // ==================== Sanitize Display Tests ====================
    runner.test('Sanitize: Mask email addresses', () => {
        const text = 'Contact user@example.com for details';
        const result = sanitizeDisplay(text);
        runner.assertNotMatch(result, /user@example\.com/, 'Email should be masked');
        runner.assertMatch(result, /\*\*\*@.*\*\*\*\.\*\*\*/, 'Should contain masked pattern');
    });
    
    runner.test('Sanitize: Mask credit cards', () => {
        const text = 'Card: 4111-1111-1111-1111';
        const result = sanitizeDisplay(text);
        runner.assertNotMatch(result, /4111-1111-1111-1111/, 'Card should be masked');
        runner.assertMatch(result, /\*{4}-\*{4}-\*{4}-\*{4}/, 'Should contain masked card pattern');
    });
    
    runner.test('Sanitize: Mask API keys', () => {
        const text = 'API key: sk_live_51abc123def456';
        const result = sanitizeDisplay(text);
        runner.assertNotMatch(result, /sk_live_51abc123def456/, 'API key should be masked');
        runner.assertMatch(result, /\*\*\*API_KEY\*\*\*/, 'Should contain API_KEY placeholder');
    });
    
    runner.test('Sanitize: Mask phone numbers', () => {
        const text = 'Call +1 (555) 123-4567';
        const result = sanitizeDisplay(text);
        runner.assertNotMatch(result, /\+1.*555.*123.*4567/, 'Phone should be masked');
        runner.assertMatch(result, /\*\*\*-\*\*\*-\*\*\*\*/, 'Should contain masked phone pattern');
    });
    
    runner.test('Sanitize: Mask IP addresses', () => {
        const text = 'Server at 192.168.1.1';
        const result = sanitizeDisplay(text);
        runner.assertNotMatch(result, /192\.168\.1\.1/, 'IP should be masked');
        runner.assertMatch(result, /\*\*\*\.\*\*\*\.\*\*\*\.\*\*\*/, 'Should contain masked IP pattern');
    });
    
    runner.test('Sanitize: Mask SSN', () => {
        const text = 'SSN: 123-45-6789';
        const result = sanitizeDisplay(text);
        runner.assertNotMatch(result, /123-45-6789/, 'SSN should be masked');
        runner.assertMatch(result, /\*\*\*-\*\*\*-\*\*\*\*/, 'Should contain masked SSN pattern');
    });
    
    runner.test('Sanitize: Preserve normal text', () => {
        const text = 'This is normal text without PII';
        const result = sanitizeDisplay(text);
        runner.assertEqual(result, text, 'Normal text should be preserved');
    });
    
    // ==================== Mermaid Generation Tests ====================
    runner.test('Mermaid: Generate empty timeline', () => {
        const events = [];
        const result = generateMermaidTimeline(events);
        runner.assertMatch(result, /gantt/, 'Should contain gantt directive');
        runner.assertMatch(result, /No Data/, 'Should show no data section');
    });
    
    runner.test('Mermaid: Generate timeline with events', () => {
        const events = [
            { app_name: 'Chrome', intent: 'Browsing', timestamp: '2024-01-01T15:00:00Z', duration_ms: 3600000 },
            { app_name: 'VSCode', intent: 'Coding', timestamp: '2024-01-01T16:00:00Z', duration_ms: 1800000 }
        ];
        const result = generateMermaidTimeline(events);
        runner.assertMatch(result, /section Chrome/, 'Should have Chrome section');
        runner.assertMatch(result, /section VSCode/, 'Should have VSCode section');
        runner.assertMatch(result, /Browsing :15:00, 60m/, 'Should have Browsing task');
        runner.assertMatch(result, /Coding :16:00, 30m/, 'Should have Coding task');
    });
    
    runner.test('Mermaid: Sanitize PII in timeline', () => {
        const events = [
            { app_name: 'Chrome', intent: 'Email user@test.com', timestamp: '2024-01-01T15:00:00Z', duration_ms: 60000 }
        ];
        const result = generateMermaidTimeline(events);
        runner.assertNotMatch(result, /user@test\.com/, 'Email should be masked in Mermaid');
    });
    
    // ==================== Duration Formatting Tests ====================
    runner.test('Duration: Format milliseconds', () => {
        runner.assertEqual(formatDuration(500), '0м', 'Less than 1 second');
        runner.assertEqual(formatDuration(1500), '1с', '1.5 seconds');
        runner.assertEqual(formatDuration(59000), '59с', '59 seconds');
        runner.assertEqual(formatDuration(999), '0м', 'Less than 1 second');
    });
    
    runner.test('Duration: Format minutes', () => {
        runner.assertEqual(formatDuration(60000), '1м', '1 minute');
        runner.assertEqual(formatDuration(120000), '2м', '2 minutes');
        runner.assertEqual(formatDuration(125000), '2м 5с', '2 minutes 5 seconds');
    });
    
    runner.test('Duration: Format hours', () => {
        runner.assertEqual(formatDuration(3600000), '1ч 0м', '1 hour');
        runner.assertEqual(formatDuration(5400000), '1ч 30м', '1.5 hours');
        runner.assertEqual(formatDuration(7200000), '2ч 0м', '2 hours');
    });
    
    runner.test('Duration: Handle edge cases', () => {
        runner.assertEqual(formatDuration(0), '0м', 'Zero duration');
        runner.assertEqual(formatDuration(-100), '0м', 'Negative duration');
        runner.assertEqual(formatDuration(null), '0м', 'Null duration');
    });
    
    // ==================== Time Formatting Tests ====================
    runner.test('Time: Format ISO timestamp', () => {
        runner.assertEqual(formatTime('2024-01-01T10:30:00Z'), '10:30', 'Morning time');
        runner.assertEqual(formatTime('2024-01-01T23:59:00Z'), '23:59', 'Late night');
        runner.assertEqual(formatTime('2024-01-01T00:05:00Z'), '00:05', 'Early morning');
        runner.assertEqual(formatTime('2024-01-01T15:30:00Z'), '15:30', 'Afternoon time');
    });
    
    runner.test('Time: Handle invalid input', () => {
        runner.assertEqual(formatTime('invalid'), '--:--', 'Invalid timestamp');
        runner.assertEqual(formatTime(''), '--:--', 'Empty string');
    });
    
    // Запускаем все тесты
    const success = await runner.run();
    
    // Возвращаем код выхода
    process.exit(success ? 0 : 1);
}

// Запускаем тесты если файл выполнен напрямую
if (typeof require !== 'undefined' && require.main === module) {
    runTests().catch(error => {
        console.error('Test runner error:', error);
        process.exit(1);
    });
}

// Экспорт для использования в других тестах
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        parseCSVLine,
        parseCSV,
        parseJSONL,
        sanitizeDisplay,
        generateMermaidTimeline,
        formatDuration,
        formatTime,
        TestRunner
    };
}
