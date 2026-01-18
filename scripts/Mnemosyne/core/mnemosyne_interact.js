/**
 * Mnemosyne Core V3.0 - Tier 3: The View
 * Module: Interaction Handler (User Feedback Layer)
 * 
 * Этот модуль обрабатывает пользовательские взаимодействия с дашбордом:
 * - Флагирование записей как некорректных
 * - Коррекция записей
 * - Сбор обучающей выборки
 */

class MnemosyneInteractionHandler {
    /**
     * Конструктор обработчика взаимодействий
     * @param {Object} app - Obsidian API app object
     * @param {Object} dv - Dataview API object
     */
    constructor(app, dv) {
        this.app = app;
        this.dv = dv;
        
        // Хранилище для флагов и коррекций
        this._feedbackStore = new Map();
        
        // Загружаем сохраненную обратную связь
        this._loadFeedback();
    }
    
    /**
     * Загружает сохраненную обратную связь из метаданных
     * @private
     */
    async _loadFeedback() {
        try {
            const feedbackFile = '.mnemosyne/feedback.json';
            const adapter = this.app.vault.adapter;
            
            if (await adapter.exists(feedbackFile)) {
                const content = await adapter.read(feedbackFile);
                this._feedbackStore = new Map(JSON.parse(content));
            }
        } catch (error) {
            console.warn('MnemosyneInteractionHandler: Failed to load feedback:', error);
        }
    }
    
    /**
     * Сохраняет обратную связь в файл
     * @private
     */
    async _saveFeedback() {
        try {
            const feedbackFile = '.mnemosyne/feedback.json';
            const adapter = this.app.vault.adapter;
            
            const content = JSON.stringify(Array.from(this._feedbackStore.entries()));
            await adapter.write(feedbackFile, content);
        } catch (error) {
            console.error('MnemosyneInteractionHandler: Failed to save feedback:', error);
        }
    }
    
    /**
     * Флагирует событие как некорректное
     * @param {Object} event - Объект события
     */
    flagEntry(event) {
        const eventId = event.id || event.timestamp;
        
        this._feedbackStore.set(`flag_${eventId}`, {
            type: 'flag',
            event: event,
            timestamp: Date.now(),
            reason: 'User flagged as incorrect'
        });
        
        this._saveFeedback();
        
        // Показываем уведомление
        this._showNotification('🚩 Entry flagged', 'This entry has been marked for review.');
    }
    
    /**
     * Открывает диалог коррекции для события
     * @param {Object} event - Объект события
     */
    correctEntry(event) {
        const eventId = event.id || event.timestamp;
        
        // Создаем модальный диалог
        const modal = this._createCorrectionModal(event);
        
        document.body.appendChild(modal);
    }
    
    /**
     * Создает модальный диалог коррекции
     * @private
     */
    _createCorrectionModal(event) {
        const modal = document.createElement('div');
        modal.className = 'mnemosyne-modal-overlay';
        
        const modalContent = document.createElement('div');
        modalContent.className = 'mnemosyne-modal';
        
        // Заголовок
        const header = document.createElement('h3');
        header.textContent = '✏️ Correct Entry';
        modalContent.appendChild(header);
        
        // Текущее значение
        const currentSection = document.createElement('div');
        currentSection.className = 'current-value-section';
        
        const currentLabel = document.createElement('label');
        currentLabel.textContent = 'Current Intent:';
        currentSection.appendChild(currentLabel);
        
        const currentValue = document.createElement('div');
        currentValue.className = 'current-intent';
        currentValue.textContent = event.intent || 'No intent';
        currentSection.appendChild(currentValue);
        
        modalContent.appendChild(currentSection);
        
        // Поле для коррекции
        const correctionSection = document.createElement('div');
        correctionSection.className = 'correction-section';
        
        const correctionLabel = document.createElement('label');
        correctionLabel.textContent = 'Corrected Intent:';
        correctionSection.appendChild(correctionLabel);
        
        const correctionInput = document.createElement('textarea');
        correctionInput.className = 'correction-input';
        correctionInput.placeholder = 'Enter the correct interpretation...';
        correctionInput.rows = 4;
        correctionSection.appendChild(correctionInput);
        
        modalContent.appendChild(correctionSection);
        
        // Кнопки
        const buttons = document.createElement('div');
        buttons.className = 'modal-buttons';
        
        const saveBtn = document.createElement('button');
        saveBtn.textContent = '💾 Save';
        saveBtn.className = 'save-btn';
        saveBtn.onclick = () => {
            this._saveCorrection(event, correctionInput.value);
            document.body.removeChild(modal);
        };
        buttons.appendChild(saveBtn);
        
        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = '❌ Cancel';
        cancelBtn.className = 'cancel-btn';
        cancelBtn.onclick = () => {
            document.body.removeChild(modal);
        };
        buttons.appendChild(cancelBtn);
        
        modalContent.appendChild(buttons);
        modal.appendChild(modalContent);
        
        return modal;
    }
    
    /**
     * Сохраняет коррекцию для события
     * @private
     * @param {Object} event - Объект события
     * @param {string} correction - Текст коррекции
     */
    _saveCorrection(event, correction) {
        if (!correction || correction.trim() === '') {
            this._showNotification('⚠️ Empty correction', 'Please enter a correction before saving.');
            return;
        }
        
        const eventId = event.id || event.timestamp;
        
        this._feedbackStore.set(`correction_${eventId}`, {
            type: 'correction',
            event: event,
            correction: correction.trim(),
            timestamp: Date.now()
        });
        
        this._saveFeedback();
        this._showNotification('✅ Correction saved', 'Your feedback has been recorded.');
    }
    
    /**
     * Показывает уведомление пользователю
     * @private
     * @param {string} title - Заголовок уведомления
     * @param {string} message - Текст уведомления
     */
    _showNotification(title, message) {
        // Используем Obsidian API для уведомлений
        if (this.app.notice) {
            this.app.notice(message, 5000);
        } else {
            // Fallback для браузера
            console.log(`[${title}] ${message}`);
        }
    }
    
    /**
     * Рендерит статистику обучающей выборки
     * @param {HTMLElement} container - Контейнер для рендеринга
     */
    async renderTrainingStats(container) {
        if (!container) return;
        
        const statsSection = this.dv.el('div', '', { 
            cls: 'training-stats-section',
            container
        });
        
        this.dv.el('h3', '📊 Training Statistics', { container: statsSection });
        
        // Собираем статистику
        const stats = this._calculateStats();
        
        // Рендерим метрики
        const metricsContainer = this.dv.el('div', '', { 
            cls: 'stats-metrics',
            container: statsSection
        });
        
        this._renderStatMetric(metricsContainer, 'Total Flags', stats.totalFlags);
        this._renderStatMetric(metricsContainer, 'Total Corrections', stats.totalCorrections);
        this._renderStatMetric(metricsContainer, 'Pending Review', stats.pendingReview);
        
        // Кнопка экспорта
        const exportBtn = this.dv.el('button', '📤 Export Training Data', { 
            cls: 'export-btn',
            container: statsSection
        });
        exportBtn.onclick = () => this._exportTrainingData();
    }
    
    /**
     * Рассчитывает статистику из хранилища обратной связи
     * @private
     * @returns {Object} Объект статистики
     */
    _calculateStats() {
        let totalFlags = 0;
        let totalCorrections = 0;
        let pendingReview = 0;
        
        for (const [key, value] of this._feedbackStore) {
            if (value.type === 'flag') {
                totalFlags++;
            } else if (value.type === 'correction') {
                totalCorrections++;
            }
        }
        
        pendingReview = totalFlags + totalCorrections;
        
        return {
            totalFlags,
            totalCorrections,
            pendingReview
        };
    }
    
    /**
     * Рендерит метрику статистики
     * @private
     */
    _renderStatMetric(container, label, value) {
        const metric = this.dv.el('div', '', { 
            cls: 'stat-metric',
            container
        });
        
        this.dv.el('span', label, { 
            cls: 'stat-label',
            container: metric
        });
        
        this.dv.el('span', value, { 
            cls: 'stat-value',
            container: metric
        });
    }
    
    /**
     * Экспортирует данные обучающей выборки в файл
     * @private
     */
    async _exportTrainingData() {
        try {
            const exportData = {
                exported_at: new Date().toISOString(),
                total_entries: this._feedbackStore.size,
                entries: Array.from(this._feedbackStore.entries())
            };
            
            const exportFile = `.mnemosyne/training_export_${Date.now()}.json`;
            const adapter = this.app.vault.adapter;
            
            await adapter.write(exportFile, JSON.stringify(exportData, null, 2));
            
            this._showNotification('📤 Export complete', `Training data exported to ${exportFile}`);
        } catch (error) {
            console.error('MnemosyneInteractionHandler: Export failed:', error);
            this._showNotification('❌ Export failed', 'Could not export training data.');
        }
    }
    
    /**
     * Получает все сохраненные флаги и коррекции
     * @returns {Array} Массив записей обратной связи
     */
    getAllFeedback() {
        return Array.from(this._feedbackStore.values());
    }
    
    /**
     * Очищает хранилище обратной связи
     */
    clearFeedback() {
        this._feedbackStore.clear();
        this._saveFeedback();
        this._showNotification('🗑️ Feedback cleared', 'All feedback has been deleted.');
    }
}

// Экспорт для использования в других модулях
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { MnemosyneInteractionHandler };
}
