/**
 * Mnemosyne Core V3.0 - Tier 3: The View
 * Module: Renderer (Visual Layer)
 * 
 * Этот модуль отвечает за визуализацию данных в Obsidian.
 * Предоставляет методы для рендеринга различных компонентов дашборда.
 */

class MnemosyneRenderer {
    /**
     * Конструктор рендерера
     * @param {Object} dv - Dataview API object
     */
    constructor(dv) {
        this.dv = dv;
        
        // Цвета для приложений
        this.appColors = {
            'vscode': '#007ACC',
            'chrome': '#4285F4',
            'firefox': '#FF7139',
            'edge': '#0078D7',
            'terminal': '#000000',
            'git': '#F05032',
            'github': '#24292E',
            'office': '#D24726',
            'default': '#666666'
        };
    }
    
    /**
     * Получает цвет для приложения
     * @param {string} appName - Имя приложения
     * @returns {string} Цвет в формате HEX
     */
    getAppColor(appName) {
        const lowerName = appName.toLowerCase();
        
        for (const [key, color] of Object.entries(this.appColors)) {
            if (lowerName.includes(key)) {
                return color;
            }
        }
        
        return this.appColors.default;
    }
    
    /**
     * Форматирует длительность в человекочитаемый формат
     * @param {number} ms - Длительность в миллисекундах
     * @returns {string} Форматированная строка
     */
    formatDuration(ms) {
        if (!ms || ms === 0) return '0m';
        
        const seconds = Math.floor(ms / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        
        if (hours > 0) {
            const remainingMinutes = minutes % 60;
            return `${hours}h ${remainingMinutes}m`;
        } else if (minutes > 0) {
            const remainingSeconds = seconds % 60;
            return `${minutes}m ${remainingSeconds}s`;
        } else {
            return `${seconds}s`;
        }
    }
    
    /**
     * Рендерит сводку за день
     * @param {Object} summary - Объект сводки
     */
    renderDailySummary(summary) {
        const container = this.dv.el('div', '', { cls: 'mnemosyne-summary' });
        
        // Карточки метрик
        const metrics = this.dv.el('div', '', { cls: 'summary-metrics', container });
        
        // Общее время
        this._renderMetricCard(metrics, '⏱️ Total Time', this.formatDuration(summary.totalTime), 'time-card');
        
        // Focus Score
        const focusClass = summary.focusScore >= 70 ? 'high' : summary.focusScore >= 40 ? 'medium' : 'low';
        this._renderMetricCard(metrics, '🎯 Focus Score', `${summary.focusScore}%`, `focus-card ${focusClass}`);
        
        // Deep Work
        this._renderMetricCard(metrics, '🔥 Deep Work', this.formatDuration(summary.deepWorkTime), 'deepwork-card');
        
        // Топ приложений
        this._renderTopApps(metrics, summary.topApps);
    }
    
    /**
     * Рендерит карточку метрики
     * @private
     */
    _renderMetricCard(container, label, value, extraClass = '') {
        const card = this.dv.el('div', '', { 
            cls: `metric-card ${extraClass}`,
            container 
        });
        this.dv.el('div', label, { cls: 'metric-label', container: card });
        this.dv.el('div', value, { cls: 'metric-value', container: card });
    }
    
    /**
     * Рендерит топ приложений
     * @private
     */
    _renderTopApps(container, topApps) {
        if (!topApps || topApps.length === 0) return;
        
        const appsContainer = this.dv.el('div', '', { cls: 'top-apps', container });
        this.dv.el('h3', '🏆 Top Applications', { container: appsContainer });
        
        const list = this.dv.el('div', '', { cls: 'top-apps-list', container: appsContainer });
        
        for (const app of topApps) {
            const appItem = this.dv.el('div', '', { 
                cls: 'app-item',
                container: list
            });
            
            const appBar = this.dv.el('div', '', { 
                cls: 'app-bar',
                container: appItem,
                attr: { 
                    style: `width: ${app.percentage}%; background-color: ${this.getAppColor(app.app)};` 
                }
            });
            
            const appInfo = this.dv.el('div', '', { 
                cls: 'app-info',
                container: appItem
            });
            
            this.dv.el('span', app.app, { 
                cls: 'app-name',
                container: appInfo,
                attr: { style: `color: ${this.getAppColor(app.app)};` }
            });
            
            this.dv.el('span', ` ${this.formatDuration(app.time)}`, { 
                cls: 'app-time',
                container: appInfo
            });
        }
    }
    
    /**
     * Рендерит таймлайн событий
     * @param {Array} events - Массив событий
     * @param {Object} options - Опции рендеринга
     */
    renderTimeline(events, options = {}) {
        const { title = 'Timeline', showAll = false, minDuration = 0 } = options;
        
        const container = this.dv.el('div', '', { cls: 'timeline-container' });
        this.dv.el('h2', title, { container });
        
        if (!events || events.length === 0) {
            this.dv.el('p', 'No events to display.', { container });
            return;
        }
        
        // Фильтруем события
        const filteredEvents = showAll 
            ? events 
            : events.filter(e => (e.duration_ms || 0) >= minDuration);
        
        if (filteredEvents.length === 0) {
            this.dv.el('p', 'No events match the filter criteria.', { container });
            return;
        }
        
        // Рендерим события
        const timeline = this.dv.el('div', '', { cls: 'timeline', container });
        
        for (const event of filteredEvents) {
            this._renderTimelineEvent(timeline, event);
        }
    }
    
    /**
     * Рендерит одно событие в таймлайне
     * @private
     */
    _renderTimelineEvent(container, event) {
        const eventItem = this.dv.el('div', '', { 
            cls: 'timeline-event',
            container
        });
        
        // Время
        const timeDiv = this.dv.el('div', '', { 
            cls: 'event-time',
            container: eventItem
        });
        const time = new Date(event.timestamp);
        timeDiv.textContent = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        
        // Контент
        const contentDiv = this.dv.el('div', '', { 
            cls: 'event-content',
            container: eventItem
        });
        
        // Иконка приложения
        const appIcon = this.dv.el('span', '📱', { 
            cls: 'app-icon',
            container: contentDiv,
            attr: { style: `color: ${this.getAppColor(event.app_name)};` }
        });
        
        // Название и заголовок
        const titleDiv = this.dv.el('div', '', { 
            cls: 'event-title',
            container: contentDiv
        });
        
        this.dv.el('span', event.app_name, { 
            cls: 'app-name',
            container: titleDiv,
            attr: { style: `color: ${this.getAppColor(event.app_name)};` }
        });
        
        if (event.window_title) {
            this.dv.el('span', ` - ${event.window_title}`, { 
                cls: 'window-title',
                container: titleDiv
            });
        }
        
        // Intent
        if (event.intent) {
            this.dv.el('div', event.intent, { 
                cls: 'event-intent',
                container: eventItem
            });
        }
        
        // Длительность
        if (event.duration_ms) {
            this.dv.el('div', this.formatDuration(event.duration_ms), { 
                cls: 'event-duration',
                container: eventItem
            });
        }
    }
    
    /**
     * Рендерит список событий с кнопками действий
     * @param {Array} events - Массив событий
     * @param {Function} onFlag - Callback для флага
     * @param {Function} onCorrect - Callback для коррекции
     */
    renderEventList(events, onFlag, onCorrect) {
        if (!events || events.length === 0) {
            this.dv.el('p', 'No events to display.');
            return;
        }
        
        const container = this.dv.el('div', '', { cls: 'event-list' });
        
        for (const event of events) {
            this._renderEventListItem(container, event, onFlag, onCorrect);
        }
    }
    
    /**
     * Рендерит элемент списка событий
     * @private
     */
    _renderEventListItem(container, event, onFlag, onCorrect) {
        const item = this.dv.el('div', '', { cls: 'event-item', container });
        
        // Заголовок события
        const header = this.dv.el('div', '', { cls: 'event-header', container: item });
        
        // Время и приложение
        const metaDiv = this.dv.el('div', '', { cls: 'event-meta', container: header });
        const time = new Date(event.timestamp);
        this.dv.el('span', time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), { 
            cls: 'event-time',
            container: metaDiv
        });
        
        this.dv.el('span', event.app_name, { 
            cls: 'app-name',
            container: metaDiv,
            attr: { style: `color: ${this.getAppColor(event.app_name)};` }
        });
        
        // Заголовок окна
        if (event.window_title) {
            this.dv.el('div', event.window_title, { 
                cls: 'window-title',
                container: header
            });
        }
        
        // Intent
        if (event.intent) {
            this.dv.el('div', event.intent, { 
                cls: 'event-intent',
                container: item
            });
        }
        
        // Кнопки действий
        const actionsDiv = this.dv.el('div', '', { cls: 'event-actions', container: item });
        
        if (onFlag) {
            const flagBtn = this.dv.el('button', '🚩 Flag', { 
                cls: 'action-btn flag-btn',
                container: actionsDiv
            });
            flagBtn.onclick = () => onFlag(event);
        }
        
        if (onCorrect) {
            const correctBtn = this.dv.el('button', '✏️ Correct', { 
                cls: 'action-btn correct-btn',
                container: actionsDiv
            });
            correctBtn.onclick = () => onCorrect(event);
        }
    }
    
    /**
     * Рендерит тепловую карту активности
     * @param {Array} events - Массив событий
     */
    renderHeatmap(events) {
        if (!events || events.length === 0) {
            this.dv.el('p', 'No data for heatmap.');
            return;
        }
        
        const container = this.dv.el('div', '', { cls: 'heatmap-container' });
        this.dv.el('h3', '📊 Activity Heatmap', { container });
        
        // Группируем события по часам
        const hourlyActivity = new Array(24).fill(0);
        
        for (const event of events) {
            const hour = new Date(event.timestamp).getHours();
            const duration = event.duration_ms || 0;
            hourlyActivity[hour] += duration;
        }
        
        // Находим максимум для нормализации
        const maxActivity = Math.max(...hourlyActivity);
        
        // Рендерим тепловую карту
        const grid = this.dv.el('div', '', { cls: 'heatmap-grid', container });
        
        for (let hour = 0; hour < 24; hour++) {
            const cell = this.dv.el('div', '', { 
                cls: 'heatmap-cell',
                container: grid
            });
            
            const intensity = maxActivity > 0 ? hourlyActivity[hour] / maxActivity : 0;
            const opacity = Math.max(0.1, intensity);
            
            cell.textContent = `${hour}:00`;
            cell.style.backgroundColor = `rgba(102, 126, 234, ${opacity})`;
        }
    }
}

// Экспорт для использования в других модулях
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { MnemosyneRenderer };
}
