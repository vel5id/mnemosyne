/**
 * Mnemosyne Core V3.0 - Tier 3: The View
 * Module: Data Connector (Data Ingestion Layer)
 * 
 * Этот модуль служит единственной точкой входа для получения данных.
 * Изолирует логику визуализации от физического формата хранения данных.
 * 
 * Особенности:
 * - Использует app.vault.adapter для чтения из скрытых папок (.mnemosyne/)
 * - Реализует кэширование данных для оптимизации производительности
 * - Поддерживает чтение CSV и JSONL форматов
 */

class MnemosyneDataConnector {
    /**
     * Конструктор коннектора данных
     * @param {Object} app - Obsidian API app object
     * @param {Object} dv - Dataview API object
     */
    constructor(app, dv) {
        this.app = app;
        this.dv = dv;
        
        // Кэш данных для предотвращения повторного чтения
        this._cache = new Map();
        
        // Путь к скрытой папке с логами
        this.logBasePath = '.mnemosyne/logs';
        
        // Время жизни кэша в миллисекундах (5 минут)
        this.cacheTTL = 5 * 60 * 1000;
    }
    
    /**
     * Получает ключ кэша для указанной даты и типа данных
     * @private
     * @param {string} dateKey - Ключ даты (YYYY-MM-DD)
     * @param {string} dataType - Тип данных ('csv', 'jsonl', 'markdown')
     * @returns {string} Ключ кэша
     */
    _getCacheKey(dateKey, dataType) {
        return `${dateKey}_${dataType}`;
    }
    
    /**
     * Проверяет, является ли запись в кэше актуальной
     * @private
     * @param {Object} cacheEntry - Запись в кэше
     * @returns {boolean} Актуальна ли запись
     */
    _isCacheValid(cacheEntry) {
        if (!cacheEntry) return false;
        const now = Date.now();
        return (now - cacheEntry.timestamp) < this.cacheTTL;
    }
    
    /**
     * Сохраняет данные в кэш
     * @private
     * @param {string} key - Ключ кэша
     * @param {*} data - Данные для сохранения
     */
    _setCache(key, data) {
        this._cache.set(key, {
            data: data,
            timestamp: Date.now()
        });
    }
    
    /**
     * Получает данные из кэша
     * @private
     * @param {string} key - Ключ кэша
     * @returns {*} Данные или null, если нет или устарело
     */
    _getCache(key) {
        const entry = this._cache.get(key);
        if (this._isCacheValid(entry)) {
            return entry.data;
        }
        return null;
    }
    
    /**
     * Очищает кэш для указанной даты или полностью
     * @param {string} dateKey - Ключ даты для очистки (опционально)
     */
    clearCache(dateKey = null) {
        if (dateKey) {
            // Очищаем только записи для указанной даты
            for (const key of this._cache.keys()) {
                if (key.startsWith(dateKey)) {
                    this._cache.delete(key);
                }
            }
        } else {
            // Очищаем весь кэш
            this._cache.clear();
        }
    }
    
    /**
     * Читает файл через низкоуровневый adapter API
     * Это позволяет читать из скрытых папок (.mnemosyne/)
     * @private
     * @param {string} relativePath - Относительный путь к файлу
     * @returns {Promise<string|null>} Содержимое файла или null при ошибке
     */
    async _readFileViaAdapter(relativePath) {
        try {
            const adapter = this.app.vault.adapter;
            if (await adapter.exists(relativePath)) {
                return await adapter.read(relativePath);
            }
            return null;
        } catch (error) {
            console.error(`MnemosyneDataConnector: Ошибка чтения файла ${relativePath}:`, error);
            return null;
        }
    }
    
    /**
     * Получает список файлов логов для указанной даты
     * @private
     * @param {string} dateKey - Ключ даты (YYYY-MM-DD)
     * @returns {Promise<Array<string>>} Список путей к файлам
     */
    async _getLogFilesForDate(dateKey) {
        try {
            const adapter = this.app.vault.adapter;
            const datePath = `${this.logBasePath}/${dateKey}`;
            
            if (!(await adapter.exists(datePath))) {
                return [];
            }
            
            const files = await adapter.list(datePath);
            return files.files || [];
        } catch (error) {
            console.error(`MnemosyneDataConnector: Ошибка получения списка файлов для ${dateKey}:`, error);
            return [];
        }
    }
    
    /**
     * Парсит CSV строку в массив объектов
     * @private
     * @param {string} csvContent - Содержимое CSV файла
     * @returns {Array<Object>} Массив распарсенных объектов
     */
    _parseCSV(csvContent) {
        const lines = csvContent.trim().split('\n');
        if (lines.length < 2) return [];
        
        // Получаем заголовки из первой строки
        const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
        
        const result = [];
        
        for (let i = 1; i < lines.length; i++) {
            const values = this._parseCSVLine(lines[i]);
            if (values.length !== headers.length) continue;
            
            const obj = {};
            headers.forEach((header, index) => {
                obj[header] = values[index];
            });
            result.push(obj);
        }
        
        return result;
    }
    
    /**
     * Парсит одну строку CSV с учетом кавычек
     * @private
     * @param {string} line - Строка CSV
     * @returns {Array<string>} Массив значений
     */
    _parseCSVLine(line) {
        const result = [];
        let current = '';
        let inQuotes = false;
        
        for (let i = 0; i < line.length; i++) {
            const char = line[i];
            const nextChar = line[i + 1];
            
            if (char === '"') {
                if (inQuotes && nextChar === '"') {
                    // Экранированная кавычка
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
     * Парсит JSONL (JSON Lines) файл
     * @private
     * @param {string} jsonlContent - Содержимое JSONL файла
     * @returns {Array<Object>} Массив распарсенных объектов
     */
    _parseJSONL(jsonlContent) {
        const lines = jsonlContent.trim().split('\n');
        const result = [];
        
        for (const line of lines) {
            try {
                const obj = JSON.parse(line);
                result.push(obj);
            } catch (error) {
                console.warn(`MnemosyneDataConnector: Ошибка парсинга JSONL строки:`, line, error);
            }
        }
        
        return result;
    }
    
    /**
     * Нормализует данные событий к единой схеме
     * @private
     * @param {Object} rawEvent - Сырое событие
     * @returns {Object} Нормализованное событие
     */
    _normalizeEvent(rawEvent) {
        return {
            timestamp: rawEvent.timestamp || rawEvent.time || rawEvent.datetime || new Date().toISOString(),
            app_name: rawEvent.app_name || rawEvent.app || rawEvent.application || 'Unknown',
            window_title: rawEvent.window_title || rawEvent.title || rawEvent.window || '',
            intent: rawEvent.intent || rawEvent.summary || rawEvent.description || '',
            intent_summary: rawEvent.intent_summary || rawEvent.summary || '',
            input_intensity: parseInt(rawEvent.input_intensity || rawEvent.intensity || 0),
            key_count: parseInt(rawEvent.key_count || rawEvent.keys || 0),
            mouse_clicks: parseInt(rawEvent.mouse_clicks || rawEvent.clicks || 0),
            duration_ms: parseInt(rawEvent.duration_ms || rawEvent.duration || 0),
            screenshot_path: rawEvent.screenshot_path || rawEvent.screenshot || null,
            file_path: rawEvent.file_path || rawEvent.path || null,
            flagged: rawEvent.flagged || false,
            human_verified: rawEvent.human_verified || false,
            correction_text: rawEvent.correction_text || '',
            training_status: rawEvent.training_status || ''
        };
    }
    
    /**
     * Получает массив событий активности за указанную дату
     * @param {string|Date} date - Целевая дата (Date объект или строка YYYY-MM-DD)
     * @returns {Promise<Array>} Массив объектов ActivityEvent
     */
    async getDailyLog(date) {
        let dateKey;
        
        if (date instanceof Date) {
            dateKey = this._formatDateKey(date);
        } else {
            dateKey = date;
        }
        
        // Проверяем кэш
        const cacheKey = this._getCacheKey(dateKey, 'events');
        const cached = this._getCache(cacheKey);
        if (cached) {
            return cached;
        }
        
        // Получаем файлы логов
        const logFiles = await this._getLogFilesForDate(dateKey);
        
        if (logFiles.length === 0) {
            // Пробуем получить данные из Markdown файлов через Dataview
            const markdownEvents = await this._getEventsFromMarkdown(dateKey);
            this._setCache(cacheKey, markdownEvents);
            return markdownEvents;
        }
        
        // Читаем и парсим файлы логов
        const allEvents = [];
        
        for (const filePath of logFiles) {
            const content = await this._readFileViaAdapter(filePath);
            if (!content) continue;
            
            if (filePath.endsWith('.csv')) {
                const csvEvents = this._parseCSV(content);
                allEvents.push(...csvEvents);
            } else if (filePath.endsWith('.jsonl')) {
                const jsonlEvents = this._parseJSONL(content);
                allEvents.push(...jsonlEvents);
            }
        }
        
        // Нормализуем и сортируем события
        const normalizedEvents = allEvents
            .map(e => this._normalizeEvent(e))
            .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        
        // Сохраняем в кэш
        this._setCache(cacheKey, normalizedEvents);
        
        return normalizedEvents;
    }
    
    /**
     * Получает события из Markdown файлов через Dataview
     * @private
     * @param {string} dateKey - Ключ даты (YYYY-MM-DD)
     * @returns {Promise<Array>} Массив событий
     */
    async _getEventsFromMarkdown(dateKey) {
        try {
            const pages = this.dv.pages('"Mnemosyne/Logs"')
                .where(p => p.file.name.includes(dateKey));
            
            const events = [];
            
            for (const page of pages) {
                events.push({
                    timestamp: page.file.ctime.toISOString(),
                    app_name: page.app_name || 'Unknown',
                    window_title: page.window_title || page.title || '',
                    intent: page.intent || '',
                    intent_summary: page.intent_summary || '',
                    input_intensity: page.input_intensity || 0,
                    key_count: page.key_count || 0,
                    mouse_clicks: page.mouse_clicks || 0,
                    duration_ms: page.duration_ms || 0,
                    screenshot_path: page.screenshot_path || null,
                    file_path: page.file.path,
                    flagged: page.flagged || false,
                    human_verified: page.human_verified || false,
                    correction_text: page.correction_text || '',
                    training_status: page.training_status || ''
                });
            }
            
            return events.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        } catch (error) {
            console.error('MnemosyneDataConnector: Ошибка получения событий из Markdown:', error);
            return [];
        }
    }
    
    /**
     * Извлекает контекстную информацию для конкретного проекта
     * @param {string} projectName - Имя проекта (WikiLink)
     * @returns {Promise<Object>} Контекст проекта
     */
    async getProjectContext(projectName) {
        try {
            // Удаляем скобки wiki-link если есть
            const cleanName = projectName.replace(/\[\[|\]\]/g, '');
            
            // Ищем связанные файлы через Dataview
            const relatedPages = this.dv.pages()
                .where(p => 
                    p.file.name.includes(cleanName) || 
                    (p.tags && p.tags.includes(cleanName))
                );
            
            // Собираем статистику по проекту
            const events = await this.getDailyLog(this._formatDateKey(new Date()));
            const projectEvents = events.filter(e => 
                e.window_title.includes(cleanName) || 
                e.intent.includes(cleanName)
            );
            
            return {
                name: cleanName,
                relatedFiles: relatedPages.length,
                todayEvents: projectEvents.length,
                totalTime: projectEvents.reduce((sum, e) => sum + (e.duration_ms || 0), 0),
                lastActivity: projectEvents.length > 0 ? 
                    projectEvents[projectEvents.length - 1].timestamp : null
            };
        } catch (error) {
            console.error('MnemosyneDataConnector: Ошибка получения контекста проекта:', error);
            return {
                name: projectName,
                relatedFiles: 0,
                todayEvents: 0,
                totalTime: 0,
                lastActivity: null
            };
        }
    }
    
    /**
     * Форматирует дату в ключ YYYY-MM-DD
     * @private
     * @param {Date} date - Объект даты
     * @returns {string} Ключ даты
     */
    _formatDateKey(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }
    
    /**
     * Получает высокоуровневую сводку за день
     * @param {string|Date} date - Целевая дата
     * @returns {Promise<Object>} Сводка за день
     */
    async getDailySummary(date) {
        const events = await this.getDailyLog(date);
        
        if (events.length === 0) {
            return {
                totalEvents: 0,
                totalTime: 0,
                focusScore: 0,
                topApps: [],
                deepWorkTime: 0
            };
        }
        
        // Общее время
        const totalTime = events.reduce((sum, e) => sum + (e.duration_ms || 0), 0);
        
        // Focus Score на основе интенсивности ввода
        const avgIntensity = events.reduce((sum, e) => sum + (e.input_intensity || 0), 0) / events.length;
        const focusScore = Math.min(100, Math.round(avgIntensity * 10));
        
        // Топ приложений
        const appTimes = {};
        events.forEach(e => {
            const app = e.app_name || 'Unknown';
            appTimes[app] = (appTimes[app] || 0) + (e.duration_ms || 0);
        });
        
        const topApps = Object.entries(appTimes)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
            .map(([app, time]) => ({ app, time, percentage: Math.round((time / totalTime) * 100) }));
        
        // Deep Work время (высокая интенсивность)
        const deepWorkEvents = events.filter(e => (e.input_intensity || 0) > 5);
        const deepWorkTime = deepWorkEvents.reduce((sum, e) => sum + (e.duration_ms || 0), 0);
        
        return {
            totalEvents: events.length,
            totalTime,
            focusScore,
            topApps,
            deepWorkTime
        };
    }
}

// Экспорт для использования в других модулях
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { MnemosyneDataConnector };
}
