/**
 * Enhanced AI Assistant Frontend
 * Revolutionary upgrade with persistent memory, context awareness, and advanced features
 * Integrates seamlessly with the Smart Assistant backend
 */

class EnhancedAIAssistant {
    constructor() {
        this.sessionId = null;
        this.currentContext = {};
        this.userPreferences = {};
        this.messageHistory = [];
        this.isProcessing = false;
        this.isTyping = false;
        this.typingTimeout = null;
        this.connectionStatus = 'disconnected';
        
        // Enhanced configuration
        this.config = {
            endpoints: {
                startSession: '/api/assistant/start-session',
                chat: '/api/assistant/chat',
                sessions: '/api/assistant/sessions',
                personalization: '/api/assistant/personalization',
                analytics: '/api/assistant/analytics',
                capabilities: '/api/assistant/capabilities'
            },
            features: {
                persistentMemory: true,
                contextAwareness: true,
                agentConsultation: true,
                personalization: true,
                typingIndicator: true,
                autoSave: true
            },
            ui: {
                animationDuration: 300,
                typingSpeed: 50,
                maxMessageHeight: 200,
                autoScrollThreshold: 100
            }
        };
        
        // Initialize on DOM ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.initialize());
        } else {
            this.initialize();
        }
    }
    
    async initialize() {
        console.log('🤖 Initializing Enhanced AI Assistant...');
        
        try {
            // Setup DOM elements
            this.setupDOMElements();
            
            // Load user preferences
            await this.loadUserPreferences();
            
            // Setup event listeners
            this.setupEventListeners();
            
            // Initialize session with current page context
            await this.initializeSession();
            
            // Setup auto-save and context monitoring
            this.setupAutoFeatures();
            
            console.log('✅ Enhanced AI Assistant initialized successfully');
            this.updateConnectionStatus('connected');
            
        } catch (error) {
            console.error('❌ Failed to initialize AI Assistant:', error);
            this.showError('Failed to initialize AI Assistant. Please refresh the page.');
        }
    }
    
    setupDOMElements() {
        // Main container (may be empty placeholder from template)
        this.container = document.getElementById('ai-assistant-container') || this.createContainer();

        // If container exists but not yet populated with internal markup, build it
        if (!this.container.querySelector('.messages-container')) {
            this.container.innerHTML = this.buildInterfaceMarkup();
        }

        // Cache element references
        this.chatContainer = this.container.querySelector('.chat-container');
        this.messagesContainer = this.container.querySelector('.messages-container');
        this.inputContainer = this.container.querySelector('.input-container');
        this.messageInput = this.container.querySelector('#message-input');
        this.sendButton = this.container.querySelector('#send-button');
        this.typingIndicator = this.container.querySelector('.typing-indicator');
        this.statusIndicator = this.container.querySelector('.status-indicator');
        this.contextDisplay = this.container.querySelector('.context-display');
        this.agentDisplay = this.container.querySelector('.agent-display');
        this.actionButtons = this.container.querySelector('.action-buttons');
        this.sessionSelector = this.container.querySelector('.session-selector');
        this.preferencesButton = this.container.querySelector('.preferences-button');
    }
    
    createContainer() {
        const container = document.createElement('div');
        container.id = 'ai-assistant-container';
        container.className = 'enhanced-ai-assistant';
        container.innerHTML = this.buildInterfaceMarkup();
        document.body.appendChild(container);
        return container;
    }

    buildInterfaceMarkup() {
        return `
            <div class="assistant-header">
                <div class="header-left">
                    <div class="status-indicator" title="Connection Status">
                        <div class="status-dot"></div>
                        <span class="status-text">Connecting...</span>
                    </div>
                    <div class="context-display" title="Current Context">
                        <i class="fas fa-map-marker-alt"></i>
                        <span class="context-text">Loading...</span>
                    </div>
                </div>
                <div class="header-right">
                    <div class="session-selector">
                        <select id="session-select" title="Switch Session">
                            <option value="">New Session</option>
                        </select>
                    </div>
                    <button class="preferences-button" title="Preferences">
                        <i class="fas fa-cog"></i>
                    </button>
                    <button class="minimize-button" title="Minimize">
                        <i class="fas fa-minus"></i>
                    </button>
                </div>
            </div>
            
            <div class="chat-container">
                <div class="messages-container"></div>
                <div class="typing-indicator" style="display: none;">
                    <div class="typing-dots">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                    <span class="typing-text">AI is thinking...</span>
                </div>
                <div class="agent-display" style="display: none;">
                    <div class="agent-consultation">
                        <i class="fas fa-users"></i>
                        <span class="agent-text">Consulting agents...</span>
                    </div>
                </div>
            </div>
            
            <div class="action-buttons" style="display: none;"></div>
            
            <div class="input-container">
                <div class="input-wrapper">
                    <textarea id="message-input" placeholder="Ask me anything about your supply chain..." rows="1"></textarea>
                    <button id="send-button" title="Send Message">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
                <div class="input-footer">
                    <div class="capabilities-hint">
                        💡 I can help with shipments, suppliers, risks, analytics, and more
                    </div>
                    <div class="personalization-status"></div>
                </div>
            </div>
        `;
    }
    
    createEnhancedChatInterface() {
        // Already handled in createContainer
        this.messagesContainer = this.container.querySelector('.messages-container');
        this.messageInput = this.container.querySelector('#message-input');
        this.sendButton = this.container.querySelector('#send-button');
    }
    
    setupEventListeners() {
        // Send message events
        this.sendButton?.addEventListener('click', () => this.sendMessage());
        this.messageInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Auto-resize textarea
        this.messageInput?.addEventListener('input', () => this.autoResizeTextarea());
        
        // Session selector
        const sessionSelect = this.container.querySelector('#session-select');
        sessionSelect?.addEventListener('change', (e) => this.switchSession(e.target.value));
        
        // Preferences button
        this.preferencesButton?.addEventListener('click', () => this.showPreferences());
        
        // Minimize/maximize
        const minimizeButton = this.container.querySelector('.minimize-button');
        minimizeButton?.addEventListener('click', () => this.toggleMinimize());
        
        // External trigger button (from base template)
        const externalTrigger = document.getElementById('assistantTrigger');
        if (externalTrigger) {
            externalTrigger.addEventListener('click', () => this.toggleMinimize());
        }
        
        // Page context monitoring
        this.setupContextMonitoring();
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboardShortcuts(e));
    }
    
    setupContextMonitoring() {
        // Monitor page changes for context awareness
        let lastUrl = location.href;
        let lastPageData = this.getCurrentPageData();
        
        // URL change detection
        const observer = new MutationObserver(() => {
            if (location.href !== lastUrl) {
                lastUrl = location.href;
                this.onPageChange();
            }
            
            // Data change detection
            const currentData = this.getCurrentPageData();
            if (JSON.stringify(currentData) !== JSON.stringify(lastPageData)) {
                lastPageData = currentData;
                this.onPageDataChange(currentData);
            }
        });
        
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['data-id', 'data-status', 'data-value']
        });
        
        // Periodic context updates
        setInterval(() => this.updateContext(), 30000); // Every 30 seconds
    }
    
    async loadUserPreferences() {
        try {
            const response = await fetch(this.config.endpoints.personalization, {headers: {'Accept': 'application/json'}});
            if (!response.ok) return;
            // Defensive: server might return HTML login page in some configs
            const text = await response.text();
            if (text.trim().startsWith('<')) {
                console.warn('Personalization endpoint returned HTML – using defaults');
                return;
            }
            let data = {};
            try { data = JSON.parse(text); } catch (e) { console.warn('Parse personalization JSON failed', e); return; }
            if (data.success) {
                this.userPreferences = data.personalization;
                this.applyUserPreferences();
            }
        } catch (error) {
            console.warn('Could not load user preferences:', error);
        }
    }
    
    applyUserPreferences() {
        const style = this.userPreferences.preferred_response_style || 'balanced';
        const personalizationStatus = this.container.querySelector('.personalization-status');
        
        if (personalizationStatus) {
            personalizationStatus.innerHTML = `
                <span class="style-indicator" title="Response Style: ${style}">
                    <i class="fas fa-${this.getStyleIcon(style)}"></i>
                    ${style}
                </span>
            `;
        }
        
        // Apply visual preferences
        if (this.userPreferences.preferences) {
            this.applyVisualPreferences(this.userPreferences.preferences);
        }
    }

    // NEW: Apply visual preference keys (darkMode, compact, fontSize, accentColor)
    applyVisualPreferences(prefs = {}) {
        if (!this.container) return;
        const c = this.container;
        // Dark mode toggle
        if (prefs.darkMode || prefs.theme === 'dark') {
            c.classList.add('dark-mode');
        } else {
            c.classList.remove('dark-mode');
        }
        // Compact mode
        if (prefs.compact) {
            c.classList.add('compact');
        } else {
            c.classList.remove('compact');
        }
        // Font size
        if (prefs.fontSize) {
            c.style.setProperty('--assistant-font-size', prefs.fontSize + 'px');
        }
        // Accent color
        if (prefs.accentColor) {
            c.style.setProperty('--assistant-accent', prefs.accentColor);
        }
    }
    
    getStyleIcon(style) {
        const icons = {
            'brief': 'compress-alt',
            'balanced': 'balance-scale',
            'detailed': 'expand-alt'
        };
        return icons[style] || 'balance-scale';
    }
    
    async initializeSession() {
        try {
            const context = this.buildCurrentContext();
            
            const response = await fetch(this.config.endpoints.startSession, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    page_info: context.page_info,
                    current_data: context.current_data,
                    user_preferences: this.userPreferences
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.sessionId = data.session_id;
                this.userPreferences = { ...this.userPreferences, ...data.user_preferences };
                
                // Display welcome message
                this.displayWelcomeMessage(data.welcome_message, data.capabilities);
                
                // Update context display
                this.updateContextDisplay(context);
                
                console.log('✅ Session initialized:', this.sessionId);
            } else {
                throw new Error(data.error || 'Failed to initialize session');
            }
            
        } catch (error) {
            console.error('Failed to initialize session:', error);
            this.showError('Failed to start conversation. Please refresh the page.');
        }
    }
    
    buildCurrentContext() {
        const path = window.location.pathname;
        const pageType = this.detectPageType(path);
        const currentData = this.getCurrentPageData();
        
        return {
            page_info: {
                type: pageType,
                path: path,
                title: document.title,
                url: window.location.href,
                timestamp: new Date().toISOString()
            },
            current_data: currentData,
            user_session: {
                duration: this.getSessionDuration(),
                actions_taken: this.getRecentUserActions()
            }
        };
    }
    
    detectPageType(path) {
        if (path.includes('/shipments')) return 'shipments';
        if (path.includes('/suppliers')) return 'suppliers';
        if (path.includes('/procurement')) return 'procurement';
        if (path.includes('/risk')) return 'risk';
        if (path.includes('/analytics')) return 'analytics';
        if (path.includes('/logistics')) return 'logistics';
        if (path.includes('/dashboard')) return 'dashboard';
        return 'general';
    }
    
    getCurrentPageData() {
        const data = {};
        
        // Extract data from various sources
        try {
            // Table data
            const tables = document.querySelectorAll('table[data-entity]');
            tables.forEach(table => {
                const entity = table.dataset.entity;
                const rows = Array.from(table.querySelectorAll('tbody tr')).slice(0, 5); // Limit to 5 rows
                data[entity] = rows.map(row => {
                    const cells = row.querySelectorAll('td');
                    return Array.from(cells).map(cell => cell.textContent.trim()).slice(0, 4); // Limit to 4 columns
                });
            });
            
            // Form data
            const forms = document.querySelectorAll('form[data-entity]');
            forms.forEach(form => {
                const entity = form.dataset.entity;
                const formData = new FormData(form);
                data[`${entity}_form`] = Object.fromEntries(formData.entries());
            });
            
            // Chart data (simplified)
            const charts = document.querySelectorAll('[data-chart-type]');
            charts.forEach(chart => {
                data.charts = data.charts || [];
                data.charts.push({
                    type: chart.dataset.chartType,
                    title: chart.dataset.chartTitle || 'Untitled Chart'
                });
            });
            
            // Current record IDs
            const currentId = this.extractCurrentRecordId();
            if (currentId) {
                data.current_id = currentId;
            }
            
        } catch (error) {
            console.warn('Error extracting page data:', error);
        }
        
        return data;
    }
    
    extractCurrentRecordId() {
        // Try various methods to extract current record ID
        const urlMatch = window.location.pathname.match(/\/(\d+)$/);
        if (urlMatch) return urlMatch[1];
        
        const idElement = document.querySelector('[data-record-id]');
        if (idElement) return idElement.dataset.recordId;
        
        const formId = document.querySelector('input[name="id"]');
        if (formId) return formId.value;
        
        return null;
    }
    
    async sendMessage() {
        const message = this.messageInput?.value?.trim();
        if (!message || this.isProcessing) return;
        
        this.isProcessing = true;
        this.updateSendButton(true);
        
        try {
            // Display user message
            this.displayUserMessage(message);
            
            // Clear input
            this.messageInput.value = '';
            this.autoResizeTextarea();
            
            // Show typing indicator
            this.showTypingIndicator();
            
            // Build current context
            const pageContext = this.buildCurrentContext();
            
            // Send to backend
            const response = await fetch(this.config.endpoints.chat, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    session_id: this.sessionId,
                    page_context: pageContext
                })
            });
            
            const data = await response.json();
            
            // Hide typing indicator
            this.hideTypingIndicator();
            
            if (data.success) {
                // Display AI response with enhancements
                await this.displayAIResponse(data);
                
                // Update context
                if (data.context) {
                    this.updateContextDisplay(data.context);
                }
                
                // Show agent consultations
                if (data.agents_consulted && data.agents_consulted.length > 0) {
                    this.showAgentConsultations(data.agents_consulted);
                }
                
                // Display action buttons
                if (data.actions && data.actions.length > 0) {
                    this.displayActionButtons(data.actions);
                }
                
                // Update user insights
                if (data.user_insights) {
                    this.updatePersonalizationDisplay(data.user_insights);
                }
                
            } else {
                this.showError(data.error || 'Failed to process message');
                if (data.fallback_response) {
                    this.displayAIMessage(data.fallback_response, { fallback: true });
                }
            }
            
        } catch (error) {
            console.error('Error sending message:', error);
            this.hideTypingIndicator();
            this.showError('Network error. Please check your connection and try again.');
        } finally {
            this.isProcessing = false;
            this.updateSendButton(false);
            this.messageInput?.focus();
        }
    }
    
    displayUserMessage(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message user-message';
        messageElement.innerHTML = `
            <div class="message-content">
                <div class="message-text">${this.escapeHtml(message)}</div>
                <div class="message-time">${this.formatTime(new Date())}</div>
            </div>
            <div class="message-avatar">
                <i class="fas fa-user"></i>
            </div>
        `;
        
        this.messagesContainer?.appendChild(messageElement);
        this.scrollToBottom();
        
        // Add to history
        this.messageHistory.push({
            type: 'user',
            content: message,
            timestamp: new Date()
        });
    }
    
    async displayAIResponse(data) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message ai-message';
        
        const isEnhanced = data.metadata && data.metadata.granite_model;
        const agentsUsed = data.agents_consulted || [];
        
        messageElement.innerHTML = `
            <div class="message-avatar ${isEnhanced ? 'enhanced' : ''}">
                <i class="fas fa-robot"></i>
                ${isEnhanced ? '<div class="enhancement-indicator" title="Enhanced AI Response"></div>' : ''}
            </div>
            <div class="message-content">
                <div class="message-header">
                    <span class="ai-name">SupplyChainX AI</span>
                    ${agentsUsed.length > 0 ? `<span class="agents-consulted" title="Consulted: ${agentsUsed.map(a => a.agent_name).join(', ')}"><i class="fas fa-users"></i> ${agentsUsed.length}</span>` : ''}
                    ${data.metadata ? `<span class="processing-time" title="Processing Time">${data.metadata.processing_time_ms}ms</span>` : ''}
                </div>
                <div class="message-text">${this.formatAIMessage(data.response)}</div>
                <div class="message-footer">
                    <div class="message-time">${this.formatTime(new Date())}</div>
                    ${data.context && data.context.confidence ? `<div class="confidence-indicator" title="Confidence: ${Math.round(data.context.confidence * 100)}%"><i class="fas fa-certificate"></i> ${Math.round(data.context.confidence * 100)}%</div>` : ''}
                </div>
            </div>
        `;
        
        this.messagesContainer?.appendChild(messageElement);
        
        // Animate message appearance
        messageElement.style.opacity = '0';
        messageElement.style.transform = 'translateY(20px)';
        
        await this.delay(100);
        
        messageElement.style.transition = `opacity ${this.config.ui.animationDuration}ms ease, transform ${this.config.ui.animationDuration}ms ease`;
        messageElement.style.opacity = '1';
        messageElement.style.transform = 'translateY(0)';
        
        this.scrollToBottom();
        
        // Add to history
        this.messageHistory.push({
            type: 'ai',
            content: data.response,
            metadata: data.metadata,
            agents_consulted: agentsUsed,
            timestamp: new Date()
        });
    }
    
    formatAIMessage(message) {
        // Enhanced formatting for AI messages
        let formatted = this.escapeHtml(message);
        
        // Format markdown-style elements
        formatted = formatted
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
        
        // Format lists
        formatted = formatted.replace(/^[-•]\s(.+)$/gm, '<li>$1</li>');
        if (formatted.includes('<li>')) {
            formatted = formatted.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
        }
        
        // Format emoji indicators
        formatted = formatted
            .replace(/📦/g, '<span class="emoji shipment">📦</span>')
            .replace(/🚨/g, '<span class="emoji alert">🚨</span>')
            .replace(/📊/g, '<span class="emoji analytics">📊</span>')
            .replace(/💡/g, '<span class="emoji insight">💡</span>');
        
        return formatted;
    }
    
    displayActionButtons(actions) {
        if (!this.actionButtons || actions.length === 0) return;
        
        this.actionButtons.innerHTML = '';
        this.actionButtons.style.display = 'block';
        
        const actionsHeader = document.createElement('div');
        actionsHeader.className = 'actions-header';
        actionsHeader.innerHTML = '<i class="fas fa-bolt"></i> Suggested Actions';
        this.actionButtons.appendChild(actionsHeader);
        
        const actionsGrid = document.createElement('div');
        actionsGrid.className = 'actions-grid';
        
        actions.forEach(action => {
            const button = document.createElement('button');
            button.className = `action-button action-${action.type}`;
            button.innerHTML = `
                <span class="action-label">${action.label}</span>
                ${action.description ? `<span class="action-description">${action.description}</span>` : ''}
            `;
            
            button.addEventListener('click', () => this.executeAction(action));
            actionsGrid.appendChild(button);
        });
        
        this.actionButtons.appendChild(actionsGrid);
        this.scrollToBottom();
    }
    
    executeAction(action) {
        console.log('Executing action:', action);
        
        switch (action.type) {
            case 'navigate':
                window.location.href = action.data;
                break;
                
            case 'search_shipment':
                this.searchShipment(action.data);
                break;
                
            case 'generate_report':
                this.generateReport(action.data);
                break;
                
            case 'show_urgent_items':
                this.showUrgentItems(action.data);
                break;
                
            case 'show_recent_activity':
                this.showRecentActivity(action.data);
                break;
                
            default:
                console.warn('Unknown action type:', action.type);
        }
    }
    
    showTypingIndicator() {
        if (this.typingIndicator) {
            this.typingIndicator.style.display = 'block';
            this.scrollToBottom();
        }
    }
    
    hideTypingIndicator() {
        if (this.typingIndicator) {
            this.typingIndicator.style.display = 'none';
        }
    }
    
    showAgentConsultations(consultations) {
        if (!this.agentDisplay || consultations.length === 0) return;
        
        this.agentDisplay.innerHTML = `
            <div class="agent-consultation">
                <i class="fas fa-users"></i>
                <span class="agent-text">Consulted ${consultations.length} expert agent${consultations.length > 1 ? 's' : ''}: ${consultations.map(c => c.agent_name).join(', ')}</span>
            </div>
        `;
        this.agentDisplay.style.display = 'block';
        
        // Hide after 3 seconds
        setTimeout(() => {
            if (this.agentDisplay) {
                this.agentDisplay.style.display = 'none';
            }
        }, 3000);
    }
    
    updateContextDisplay(context) {
        if (!this.contextDisplay) return;
        
        const contextText = this.container.querySelector('.context-text');
        if (contextText) {
            let displayText = 'General';
            
            if (context.page_info) {
                displayText = context.page_info.type || 'general';
                displayText = displayText.charAt(0).toUpperCase() + displayText.slice(1);
            } else if (context.description) {
                displayText = context.description;
            }
            
            contextText.textContent = displayText;
        }
        
        this.currentContext = context;
    }
    
    updateConnectionStatus(status) {
        this.connectionStatus = status;
        
        const statusDot = this.container.querySelector('.status-dot');
        const statusText = this.container.querySelector('.status-text');
        
        if (statusDot && statusText) {
            statusDot.className = `status-dot ${status}`;
            
            const statusMessages = {
                'connected': 'Connected',
                'connecting': 'Connecting...',
                'disconnected': 'Disconnected',
                'error': 'Connection Error'
            };
            
            statusText.textContent = statusMessages[status] || status;
        }
    }
    
    updateSendButton(isProcessing) {
        if (!this.sendButton) return;
        
        if (isProcessing) {
            this.sendButton.disabled = true;
            this.sendButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        } else {
            this.sendButton.disabled = false;
            this.sendButton.innerHTML = '<i class="fas fa-paper-plane"></i>';
        }
    }
    
    autoResizeTextarea() {
        if (!this.messageInput) return;
        
        this.messageInput.style.height = 'auto';
        const scrollHeight = this.messageInput.scrollHeight;
        const maxHeight = this.config.ui.maxMessageHeight;
        
        this.messageInput.style.height = Math.min(scrollHeight, maxHeight) + 'px';
        this.messageInput.style.overflowY = scrollHeight > maxHeight ? 'scroll' : 'hidden';
    }
    
    scrollToBottom() {
        if (!this.messagesContainer) return;
        
        const shouldScroll = this.messagesContainer.scrollTop + this.messagesContainer.clientHeight >= 
                            this.messagesContainer.scrollHeight - this.config.ui.autoScrollThreshold;
        
        if (shouldScroll) {
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        }
    }
    
    showError(message) {
        console.error('AI Assistant Error:', message);
        
        const errorElement = document.createElement('div');
        errorElement.className = 'message error-message';
        errorElement.innerHTML = `
            <div class="message-avatar error">
                <i class="fas fa-exclamation-triangle"></i>
            </div>
            <div class="message-content">
                <div class="message-text">${this.escapeHtml(message)}</div>
                <div class="message-time">${this.formatTime(new Date())}</div>
            </div>
        `;
        
        this.messagesContainer?.appendChild(errorElement);
        this.scrollToBottom();
    }
    
    displayWelcomeMessage(welcomeMessage, capabilities) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message ai-message welcome-message';
        
        messageElement.innerHTML = `
            <div class="message-avatar enhanced">
                <i class="fas fa-robot"></i>
                <div class="enhancement-indicator" title="Enhanced AI"></div>
            </div>
            <div class="message-content">
                <div class="message-header">
                    <span class="ai-name">SupplyChainX AI Assistant</span>
                    <span class="enhancement-badge">Enhanced</span>
                </div>
                <div class="message-text">${this.formatAIMessage(welcomeMessage)}</div>
                ${capabilities ? `
                    <div class="capabilities-preview">
                        <div class="capabilities-title">🚀 Enhanced Capabilities</div>
                        <div class="capabilities-list">
                            <span class="capability">🧠 Persistent Memory</span>
                            <span class="capability">🎯 Context Awareness</span>
                            <span class="capability">👥 Expert Agents</span>
                            <span class="capability">⚡ Real-time Analysis</span>
                        </div>
                    </div>
                ` : ''}
                <div class="message-time">${this.formatTime(new Date())}</div>
            </div>
        `;
        
        this.messagesContainer?.appendChild(messageElement);
        this.scrollToBottom();
    }
    
    // Utility methods
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    formatTime(date) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    getSessionDuration() {
        // Implementation for session duration tracking
        return 0;
    }
    
    getRecentUserActions() {
        // Implementation for tracking user actions
        return [];
    }
    
    // Event handlers
    onPageChange() {
        console.log('📍 Page changed, updating context...');
        this.updateContext();
    }
    
    onPageDataChange(newData) {
        console.log('📊 Page data changed, updating context...');
        this.currentContext.current_data = newData;
    }
    
    updateContext() {
        this.currentContext = this.buildCurrentContext();
        this.updateContextDisplay(this.currentContext);
    }
    
    handleKeyboardShortcuts(e) {
        // Ctrl/Cmd + K to focus message input
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            this.messageInput?.focus();
        }
        
        // Escape to minimize assistant
        if (e.key === 'Escape') {
            this.toggleMinimize();
        }
    }
    
    toggleMinimize() {
        this.container?.classList.toggle('minimized');
        
        const isMinimized = this.container?.classList.contains('minimized');
        const chatWidget = document.getElementById('chatWidget');
        const badge = document.getElementById('chatBadge');
        
        // Hide/show the floating trigger button based on assistant state
        if (chatWidget) {
            if (isMinimized) {
                // When minimized, show trigger button
                chatWidget.style.display = 'block';
            } else {
                // When expanded, hide trigger button to avoid overlap
                chatWidget.style.display = 'none';
            }
        }
        
        // Update badge indicator based on visibility
        if (badge) {
            const badgeCount = parseInt(badge.textContent.trim()) || 0;
            
            if (isMinimized && badgeCount > 0) {
                badge.classList.add('show');
            } else {
                badge.classList.remove('show');
            }
        }
        
        // Focus input when expanding
        if (!isMinimized) {
            this.messageInput?.focus();
            if (this.messagesContainer && this.messagesContainer.children.length === 0) {
                // Provide fallback welcome if somehow not initialized yet
                this.displayWelcomeMessage('Hello! I\'m your SupplyChainX AI Assistant. Ask me about shipments, risks, suppliers, routes or analytics to get started.');
            }
        }
    }
    
    // Additional methods for session management, preferences, etc.
    async switchSession(sessionId) {
        // Implementation for switching sessions
        console.log('Switching to session:', sessionId);
    }
    
    showPreferences() {
        // Implementation for showing preferences modal
        console.log('Showing preferences...');
    }
    
    setupAutoFeatures() {
        // Set initial state - assistant starts minimized, trigger button visible
        const chatWidget = document.getElementById('chatWidget');
        if (chatWidget) {
            chatWidget.style.display = 'block';
        }
        
        // Auto-save session state
        setInterval(() => this.autoSaveSession(), 60000); // Every minute
        
        // Monitor user activity
        this.setupActivityMonitoring();
    }
    
    autoSaveSession() {
        // Implementation for auto-saving session state
        if (this.sessionId && this.messageHistory.length > 0) {
            console.log('Auto-saving session...');
        }
    }
    
    setupActivityMonitoring() {
        // Monitor user activity for better context awareness
        let lastActivity = Date.now();
        
        ['click', 'keypress', 'scroll', 'mousemove'].forEach(eventType => {
            document.addEventListener(eventType, () => {
                lastActivity = Date.now();
            }, { passive: true });
        });
        
        // Check for inactivity
        setInterval(() => {
            const inactive = Date.now() - lastActivity > 300000; // 5 minutes
            if (inactive && this.connectionStatus === 'connected') {
                this.updateConnectionStatus('idle');
            } else if (!inactive && this.connectionStatus === 'idle') {
                this.updateConnectionStatus('connected');
            }
        }, 30000);
    }
}

// Initialize the enhanced AI assistant
window.enhancedAIAssistant = new EnhancedAIAssistant();

// Global toggle function (replaces separate initializer script)
window.toggleEnhancedAssistant = function() {
    const container = document.getElementById('ai-assistant-container');
    const chatWidget = document.getElementById('chatWidget');
    const badge = document.getElementById('chatBadge');
    
    if (!container) return;
    
    container.classList.toggle('minimized');
    const isMinimized = container.classList.contains('minimized');
    
    // Hide/show the floating trigger button based on assistant state
    if (chatWidget) {
        if (isMinimized) {
            // When minimized, show trigger button
            chatWidget.style.display = 'block';
        } else {
            // When expanded, hide trigger button to avoid overlap
            chatWidget.style.display = 'none';
        }
    }
    
    // Update badge visibility
    if (badge) {
        const badgeCount = parseInt(badge.textContent.trim()) || 0;
        if (isMinimized && badgeCount > 0) {
            badge.classList.add('show');
        } else {
            badge.classList.remove('show');
        }
    }
};

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = EnhancedAIAssistant;
}
