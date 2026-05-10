import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Bot, User, X, ChevronRight, ChevronLeft, Loader, MessageSquare, Sparkles } from 'lucide-react';

const BACKEND = 'http://localhost:8000';

const SUGGESTED = [
  'What is the total portfolio outstanding?',
  'What is the collection efficiency?',
  'What percentage of loans are in DPD 90+?',
  'What is the weighted average interest rate?',
  'Show the DPD transition from Current bucket',
  'How many active loans are there?',
  'What is the WART of the portfolio?',
];

function MessageBubble({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`chat-bubble-row ${isUser ? 'user' : 'assistant'}`}>
      <div className="chat-avatar">
        {isUser ? <User size={14} /> : <Bot size={14} />}
      </div>
      <div className={`chat-bubble ${isUser ? 'user' : 'assistant'}`}>
        <pre className="chat-text">{msg.content}</pre>
        {msg.loading && (
          <div className="chat-loading">
            <span /><span /><span />
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatSidebar({ sessionId, open, onToggle }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '👋 Hello! I\'m your Portfolio Analyst AI.\n\nAsk me anything about the analysed loan portfolio — metrics, DPD trends, collection efficiency, or any other insights.',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const sendMessage = useCallback(async (text) => {
    const question = (text || input).trim();
    if (!question || loading) return;

    setInput('');
    const userMsg = { role: 'user', content: question };
    const loadingMsg = { role: 'assistant', content: '', loading: true };

    setMessages(prev => [...prev, userMsg, loadingMsg]);
    setLoading(true);

    // Build history (exclude the loading placeholder)
    const history = messages
      .filter(m => !m.loading)
      .map(m => ({ role: m.role, content: m.content }));

    try {
      const resp = await fetch(`${BACKEND}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, question, history }),
      });

      const data = await resp.json();
      const answer = resp.ok
        ? (data.answer || 'No response received.')
        : (data.detail || 'An error occurred.');

      setMessages(prev => [
        ...prev.slice(0, -1), // remove loading placeholder
        { role: 'assistant', content: answer },
      ]);
    } catch (e) {
      setMessages(prev => [
        ...prev.slice(0, -1),
        { role: 'assistant', content: `Connection error: ${e.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, messages, sessionId]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearChat = () => {
    setMessages([{
      role: 'assistant',
      content: '👋 Chat cleared. Ask me anything about the portfolio!',
    }]);
  };

  return (
    <>
      {/* Toggle button (always visible) */}
      <button
        className="chat-toggle-btn"
        onClick={onToggle}
        title={open ? 'Close chat' : 'Ask AI about your portfolio'}
      >
        {open ? <ChevronRight size={18} /> : (
          <>
            <MessageSquare size={18} />
            <span className="chat-toggle-label">Ask AI</span>
          </>
        )}
      </button>

      {/* Sidebar panel */}
      <aside className={`chat-sidebar ${open ? 'open' : ''}`}>
        {/* Header */}
        <div className="chat-header">
          <div className="chat-header-left">
            <div className="chat-header-icon">
              <Sparkles size={16} />
            </div>
            <div>
              <div className="chat-header-title">Portfolio AI Chat</div>
              <div className="chat-header-sub">Powered by Gemini</div>
            </div>
          </div>
          <div className="chat-header-actions">
            <button className="chat-icon-btn" onClick={clearChat} title="Clear chat">
              <X size={14} />
            </button>
            <button className="chat-icon-btn" onClick={onToggle} title="Close">
              <ChevronRight size={16} />
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="chat-messages">
          {messages.map((msg, i) => (
            <MessageBubble key={i} msg={msg} />
          ))}
          <div ref={endRef} />
        </div>

        {/* Suggested questions (only when no user messages yet) */}
        {messages.filter(m => m.role === 'user').length === 0 && (
          <div className="chat-suggestions">
            <div className="chat-suggestions-label">Suggested questions</div>
            <div className="chat-suggestions-list">
              {SUGGESTED.map((q, i) => (
                <button
                  key={i}
                  className="chat-suggestion-btn"
                  onClick={() => sendMessage(q)}
                  disabled={loading}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input area */}
        <div className="chat-input-area">
          <div className="chat-input-row">
            <textarea
              ref={inputRef}
              className="chat-input"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about the portfolio..."
              rows={2}
              disabled={loading}
            />
            <button
              className="chat-send-btn"
              onClick={() => sendMessage()}
              disabled={loading || !input.trim()}
              title="Send (Enter)"
            >
              {loading ? <Loader size={16} className="spin" /> : <Send size={16} />}
            </button>
          </div>
          <div className="chat-input-hint">Press Enter to send · Shift+Enter for new line</div>
        </div>
      </aside>
    </>
  );
}
