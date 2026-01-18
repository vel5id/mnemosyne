/**
 * Mnemosyne Core V3.0 - Tier 3: The View
 * Main Dashboard Script
 * 
 * Точка входа для отображения дашборда в Obsidian.
 * Интегрирует все модули: Data Connector, Renderer и Interaction Handler.
 * 
 * Использование в Daily Note:
 * ```dataviewjs
 * const MnemosyneDashboard = await dv.view('Mnemosyne/views/daily_dashboard');
 * await MnemosyneDashboard.render(dv, app);
 * ```
 */

class MnemosyneDashboard {
    /**
     * Инициализация дашборда
     * @param {Object} dv - Dataview API object
     * @param {Object} app - Obsidian API app object
     */
    constructor(dv, app) {
        this.dv = dv;
        this.app = app;
        
        // Инициализируем модули
        this.connector = new MnemosyneDataConnector(app, dv);
        this.renderer = new MnemosyneRenderer(dv);
        this.interaction = new MnemosyneInteractionHandler(app, dv);
        
        // Определяем текущую дату
        this.currentDate = this._getCurrentDate();
        
        // Режим отображения
        this.viewMode = 'full'; // 'full', 'summary', 'timeline', 'debug'
    }
    
    /**
     * Получает текущую дату из контекста
     * @private
     * @returns {string} Дата в формате YYYY-MM-DD
     */
    _getCurrentDate() {
        // Проверяем, находимся ли мы в Daily Note
        const currentFile = this.app.workspace.getActiveFile();
        
        if (currentFile) {
            // Пытаемся извлечь дату из имени файла
            const dateMatch = currentFile.basename.match(/(\d{4}-\d{2}-\d{2})/);
            if (dateMatch) {
                return dateMatch[1];
            }
        }
        
        // По умолчанию используем сегодняшнюю дату
        const now = new Date();
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }
    
    /**
     * Основной метод рендеринга дашборда
     * @param {Object} options - Опции рендеринга
     */
    async render(options = {}) {
        try {
            // Применяем опции
            this.viewMode = options.mode || this.viewMode;
            const targetDate = options.date || this.currentDate;
            
            // Очищаем кэш если требуется
            if (options.clearCache) {
                this.connector.clearCache();
            }
            
            // Рендерим в зависимости от режима
            switch (this.viewMode) {
                case 'summary':
                    await this._renderSummary(targetDate);
                    break;
                case 'timeline':
                    await this._renderTimeline(targetDate);
                    break;
                case 'debug':
                    await this._renderDebug(targetDate);
                    break;
                case 'full':
                default:
                    await this._renderFull(targetDate);
                    break;
            }
            
        } catch (error) {
            this._renderError(error);
        }
    }
    
    /**
     * Рендерит полный дашборд
     * @private
     * @param {string} dateKey - Ключ даты
     */
    async _renderFull(dateKey) {
        // Заголовок дашборда
        this._renderHeader(dateKey);
        
        // Получаем данные
        const events = await this.connector.getDailyLog(dateKey);
        
        if (events.length === 0) {
            this._renderNoActivity(dateKey);
            return;
        }
        
        // Получаем сводку
        const summary = await this.connector.getDailySummary(dateKey);
        summary.events = events; // Добавляем события для тепловой карты
        
        // Рендерим сводку
        this.renderer.renderDailySummary(summary);
        
        // Разделитель
        this.dv.paragraph('---');
        
        // Рендерим Timeline
        this.dv.el('h2', '📅 Activity Timeline');
        this.renderer.renderTimeline(events, {
            title: `Activity Timeline - ${dateKey}`,
            showAll: false,
            minDuration: 60000 // Только события от 1 минуты
        });
        
        // Разделитель
        this.dv.paragraph('---');
        
        // Рендерим список событий с кнопками обратной связи
        this.dv.el('h2', '📋 Activity Stream');
        this.renderer.renderEventList(
            events,
            (event) => this.interaction.flagEntry(event),
            (event) => this.interaction.correctEntry(event)
        );
        
        // Разделитель
        this.dv.paragraph('---');
        
        // Рендерим статистику обучающей выборки
        const statsContainer = this.dv.el('div', '', { cls: 'mnemosyne-stats-section' });
        await this.interaction.renderTrainingStats(statsContainer);
    }
    
    /**
     * Рендерит только сводку
     * @private
     * @param {string} dateKey - Ключ даты
     */
    async _renderSummary(dateKey) {
        this._renderHeader(dateKey);
        
        const summary = await this.connector.getDailySummary(dateKey);
        const events = await this.connector.getDailyLog(dateKey);
        summary.events = events;
        
        this.renderer.renderDailySummary(summary);
    }
    
    /**
     * Рендерит только Timeline
     * @private
     * @param {string} dateKey - Ключ даты
     */
    async _renderTimeline(dateKey) {
        this._renderHeader(dateKey);
        
        const events = await this.connector.getDailyLog(dateKey);
        
        if (events.length === 0) {
            this._renderNoActivity(dateKey);
            return;
        }
        
        // Фильтр для Deep Work
        const deepWorkEvents = events.filter(e => (e.input_intensity || 0) > 5);
        
        this.dv.el('h2', '🔥 Deep Work Timeline');
        this.renderer.renderTimeline(deepWorkEvents, {
            title: `Deep Work - ${dateKey}`,
            showAll: true
        });
        
        this.dv.paragraph('---');
        
        this.dv.el('h2', '📅 Full Activity Timeline');
        this.renderer.renderTimeline(events, {
            title: `All Activity - ${dateKey}`,
            showAll: false,
            minDuration: 60000
        });
    }
    
    /**
     * Рендерит отладочную информацию
     * @private
     * @param {string} dateKey - Ключ даты
     */
    async _renderDebug(dateKey) {
        this._renderHeader(dateKey);
        
        const events = await this.connector.getDailyLog(dateKey);
        
        this.dv.el('h2', '🔍 Debug Information');
        
        // Информация о системе
        const systemInfo = this.dv.el('div', '', { cls: 'debug-section' });
        this.dv.el('h3', 'System Info', { container: systemInfo });
        this.dv.el('p', `Current Date: ${dateKey}`, { container: systemInfo });
        this.dv.el('p', `Events Count: ${events.length}`, { container: systemInfo });
        this.dv.el('p', `View Mode: ${this.viewMode}`, { container: systemInfo });
        
        // Информация о кэше
        const cacheInfo = this.dv.el('div', '', { cls: 'debug-section' });
        this.dv.el('h3', 'Cache Info', { container: cacheInfo });
        this.dv.el('p', `Cache Size: ${this.connector._cache.size} entries`, { container: cacheInfo });
        
        // Пример первого события
        if (events.length > 0) {
            const eventInfo = this.dv.el('div', '', { cls: 'debug-section' });
            this.dv.el('h3', 'Sample Event', { container: eventInfo });
            this.dv.paragraph('```json\n' + JSON.stringify(events[0], null, 2) + '\n```');
        }
        
        // Кнопка очистки кэша
        const clearCacheBtn = this.dv.el('button', '🗑️ Clear Cache', { cls: 'debug-btn' });
        clearCacheBtn.onclick = async () => {
            this.connector.clearCache();
            this.dv.paragraph('✅ Cache cleared. Refresh to reload data.');
        };
    }
    
    /**
     * Рендерит заголовок дашборда
     * @private
     * @param {string} dateKey - Ключ даты
     */
    _renderHeader(dateKey) {
        const header = this.dv.el('div', '', { cls: 'mnemosyne-header' });
        
        const title = this.dv.el('h1', '🧠 Mnemosyne Daily Dashboard', { container: header });
        
        const dateDisplay = this.dv.el('div', dateKey, { 
            cls: 'mnemosyne-date',
            container: header
        });
        
        // Кнопки управления режимом
        const controls = this.dv.el('div', '', { 
            cls: 'mnemosyne-controls',
            container: header
        });
        
        this._createModeButton('📊 Summary', 'summary', controls);
        this._createModeButton('📅 Timeline', 'timeline', controls);
        this._createModeButton('🔍 Debug', 'debug', controls);
        this._createModeButton('🔄 Full', 'full', controls);
    }
    
    /**
     * Создает кнопку переключения режима
     * @private
     * @param {string} label - Текст кнопки
     * @param {string} mode - Режим
     * @param {Object} container - Контейнер
     */
    _createModeButton(label, mode, container) {
        const btn = this.dv.el('button', label, { 
            cls: `mode-btn ${this.viewMode === mode ? 'active' : ''}`,
            container
        });
        
        btn.onclick = () => {
            this.viewMode = mode;
            // В реальной реализации здесь нужно перерендерить страницу
            this.dv.paragraph(`🔄 Switching to ${mode} mode... (Refresh to apply)`);
        };
    }
    
    /**
     * Рендерит сообщение об отсутствии активности
     * @private
     * @param {string} dateKey - Ключ даты
     */
    _renderNoActivity(dateKey) {
        const container = this.dv.el('div', '', { cls: 'mnemosyne-no-activity' });
        
        this.dv.el('h2', '📭 No Activity Recorded', { container });
        this.dv.el('p', `No activity data found for ${dateKey}.`, { container });
        this.dv.el('p', 'Make sure the Watcher (Tier 1) is running and capturing events.', { container });
        
        // Кнопка проверки
        const checkBtn = this.dv.el('button', '🔍 Check for Data', { 
            cls: 'check-data-btn',
            container
        });
        checkBtn.onclick = async () => {
            this.connector.clearCache(dateKey);
            this.dv.paragraph('🔄 Cache cleared. Refresh to check again.');
        };
    }
    
    /**
     * Рендерит сообщение об ошибке
     * @private
     * @param {Error} error - Объект ошибки
     */
    _renderError(error) {
        const container = this.dv.el('div', '', { cls: 'mnemosyne-error' });
        
        this.dv.el('h2', '⚠️ Dashboard Error', { container });
        this.dv.el('p', error.message, { container });
        
        if (error.stack) {
            const details = this.dv.el('details', '', { container });
            this.dv.el('summary', 'Show Details', { container: details });
            this.dv.paragraph('```\n' + error.stack + '\n```', { container: details });
        }
    }
    
    /**
     * Создает виджет для боковой панели
     * @param {string} dateKey - Ключ даты (опционально)
     */
    async renderSidebarWidget(dateKey = null) {
        const targetDate = dateKey || this.currentDate;
        
        const container = this.dv.el('div', '', { cls: 'mnemosyne-sidebar-widget' });
        
        // Заголовок виджета
        this.dv.el('h3', '🧠 Mnemosyne', { container });
        
        // Получаем сводку
        const summary = await this.connector.getDailySummary(targetDate);
        
        // Компактное отображение
        const metrics = this.dv.el('div', '', { cls: 'sidebar-metrics', container });
        
        this.dv.el('div', `${this.renderer.formatDuration(summary.totalTime)}`, { 
            cls: 'sidebar-metric',
            container: metrics
        });
        
        this.dv.el('div', `🎯 ${summary.focusScore}%`, { 
            cls: 'sidebar-metric',
            container: metrics
        });
        
        // Топ приложение
        if (summary.topApps.length > 0) {
            const topApp = this.dv.el('div', '', { cls: 'sidebar-top-app', container });
            this.dv.el('span', '🏆 ', { container: topApp });
            this.dv.el('span', summary.topApps[0].app, { 
                cls: 'app-name',
                container: topApp,
                attr: { style: `color: ${this.renderer.getAppColor(summary.topApps[0].app)}` }
            });
        }
        
        // Кнопка открытия полного дашборда
        const openBtn = this.dv.el('button', 'Open Dashboard', { 
            cls: 'open-dashboard-btn',
            container
        });
        openBtn.onclick = () => {
            // Открытие полной страницы дашборда
            const targetFile = this.app.vault.getAbstractFileByPath(
                `Mnemosyne/Dashboard/${targetDate}.md`
            );
            if (targetFile) {
                this.app.workspace.openLinkText(targetFile.path, '');
            }
        };
    }
}

/**
 * Точка входа для DataviewJS
 * @param {Object} dv - Dataview API object
 * @param {Object} app - Obsidian API app object
 * @param {Object} options - Опции рендеринга
 */
async function renderDashboard(dv, app, options = {}) {
    try {
        const dashboard = new MnemosyneDashboard(dv, app);
        await dashboard.render(options);
    } catch (error) {
        console.error('Mnemosyne Dashboard Error:', error);
        dv.paragraph(`⚠️ Dashboard Error: ${error.message}`);
    }
}

// Экспорт для использования
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { MnemosyneDashboard, renderDashboard };
}

// Глобальная функция для использования в DataviewJS
window.MnemosyneDashboard = MnemosyneDashboard;
window.renderMnemosyneDashboard = renderDashboard;
