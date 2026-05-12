import { useState, useCallback, useEffect } from 'react';
import UploadArea from './components/UploadArea';
import ProgressTracker from './components/ProgressTracker';
import ResultsDashboard from './components/ResultsDashboard';
import ChatSidebar from './components/ChatSidebar';
import AuthPage from './components/AuthPage';
import { Activity, LogOut } from 'lucide-react';

const API = '/api';
// SSE requires direct connection — Vite's proxy buffers streaming responses
const BACKEND = 'http://localhost:8000';

// ── Auth helpers ──────────────────────────────────────────────────────────
function getStoredAuth() {
  try {
    const raw = localStorage.getItem('auth');
    if (raw) return JSON.parse(raw);
  } catch {}
  return null;
}

function storeAuth(auth) {
  localStorage.setItem('auth', JSON.stringify(auth));
}

function clearAuth() {
  localStorage.removeItem('auth');
}

function authHeaders(token) {
  return { Authorization: `Bearer ${token}` };
}

export default function App() {
  const [auth, setAuth] = useState(getStoredAuth);
  const [files, setFiles] = useState([]);
  const [csvPaths, setCsvPaths] = useState([]);
  const [phase, setPhase] = useState('upload'); // upload | running | done
  const [progress, setProgress] = useState([]);
  const [activeAgent, setActiveAgent] = useState('');
  const [stageStatus, setStageStatus] = useState({});
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);

  const STAGES = [
    { key: 'SchemaDiscovery-AI', label: 'File Discovery' },
    { key: 'SchemaDiscovery-AI-map', label: 'Schema Mapping' },
    { key: 'DataValidation-AI', label: 'Validation' },
    { key: 'MetricComputation-AI', label: 'Metrics' },
    { key: 'Visualization-AI', label: 'Charts' },
  ];

  const handleUpload = useCallback(async (selectedFiles) => {
    setFiles(selectedFiles);
    const formData = new FormData();
    selectedFiles.forEach(f => formData.append('files', f));

    try {
      const resp = await fetch(`${API}/upload`, {
        method: 'POST',
        headers: authHeaders(auth?.token),
        body: formData,
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setCsvPaths(data.csv_paths);
    } catch (e) {
      if (e.message.includes('401')) { handleLogout(); return; }
      setError(`Upload failed: ${e.message}`);
    }
  }, [auth]);

  const handleSSEEvent = useCallback((event) => {
    // Skip Orchestrator for stage tracking (it fires first/last, not a real pipeline stage)
    const isOrchestrator = event.agent === 'Orchestrator';

    if (event.type === 'agent_start' && !isOrchestrator) {
      setActiveAgent(event.agent);
      setStageStatus(prev => {
        const next = { ...prev };
        // Handle SchemaDiscovery two-phase: discovery then mapping
        if (event.agent === 'SchemaDiscovery-AI') {
          if (!next['SchemaDiscovery-AI'] || next['SchemaDiscovery-AI'] === 'completed') {
            // Second time SchemaDiscovery fires, or first time
            if (next['SchemaDiscovery-AI'] === 'completed') {
              next['SchemaDiscovery-AI-map'] = 'active';
            } else {
              next['SchemaDiscovery-AI'] = 'active';
            }
          }
        } else {
          next[event.agent] = 'active';
        }
        return next;
      });
    }

    // Mark step failures
    if (event.type === 'step_fail' && !isOrchestrator) {
      setStageStatus(prev => ({ ...prev, [event.agent]: 'error' }));
    }

    // Handle SchemaDiscovery step transitions
    // Step 2 done = file discovery complete, Step 3/4 = schema mapping
    if (event.type === 'step_end' && event.agent === 'SchemaDiscovery-AI') {
      if (event.step >= 3) {
        setStageStatus(prev => {
          const next = { ...prev };
          if (next['SchemaDiscovery-AI'] !== 'completed') {
            next['SchemaDiscovery-AI'] = 'completed';
          }
          next['SchemaDiscovery-AI-map'] = 'active';
          return next;
        });
      }
    }

    // Mark agent success
    if (event.type === 'success' && !isOrchestrator) {
      setStageStatus(prev => {
        const next = { ...prev };
        if (event.agent === 'SchemaDiscovery-AI') {
          next['SchemaDiscovery-AI'] = 'completed';
          next['SchemaDiscovery-AI-map'] = 'completed';
        } else {
          next[event.agent] = 'completed';
        }
        return next;
      });
    }

    // Track progress log (include Orchestrator info for visibility)
    if (['agent_start', 'step_start', 'step_end', 'step_fail', 'info', 'success', 'warning', 'error'].includes(event.type)) {
      setProgress(prev => [...prev, event]);
    }

    // Detect final result event from SSE (has summary + metrics)
    if (event.summary !== undefined && event.metrics !== undefined) {
      setResult(event);
      if (event.session_id) setSessionId(event.session_id);
      setPhase('done');
      setStageStatus(prev => {
        const next = { ...prev };
        Object.keys(next).forEach(k => { if (next[k] === 'active') next[k] = 'completed'; });
        return next;
      });
    }
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (!csvPaths.length) return;
    setPhase('running');
    setProgress([]);
    setStageStatus({});
    setResult(null);
    setError(null);

    try {
      const resp = await fetch(`${BACKEND}/analyze/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(auth?.token),
        },
        body: JSON.stringify({ csv_paths: csvPaths }),
      });

      if (!resp.ok) {
        const err = await resp.text();
        setError(err);
        setPhase('upload');
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let gotResult = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE events are delimited by double newlines
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const dataLine = part.split('\n').find(l => l.startsWith('data: '));
          if (dataLine) {
            try {
              const event = JSON.parse(dataLine.slice(6));
              handleSSEEvent(event);
              if (event.summary !== undefined && event.metrics !== undefined) {
                gotResult = true;
              }
            } catch { /* skip parse errors */ }
          }
        }
      }
      // Process any remaining buffer after stream ends
      if (buffer.trim()) {
        const dataLine = buffer.split('\n').find(l => l.startsWith('data: '));
        if (dataLine) {
          try {
            const event = JSON.parse(dataLine.slice(6));
            handleSSEEvent(event);
            if (event.summary !== undefined && event.metrics !== undefined) {
              gotResult = true;
            }
          } catch { /* skip parse errors */ }
        }
      }

      // If stream ended without a result, show an error
      if (!gotResult) {
        setError('Pipeline stream ended unexpectedly. Check the backend logs.');
        setPhase('upload');
      }
    } catch (e) {
      setError(`Connection error: ${e.message}`);
      setPhase('upload');
    }
  }, [csvPaths, handleSSEEvent, auth]);

  const handleReset = useCallback(() => {
    setFiles([]);
    setCsvPaths([]);
    setPhase('upload');
    setProgress([]);
    setStageStatus({});
    setResult(null);
    setError(null);
    setActiveAgent('');
    setSessionId(null);
    setChatOpen(false);
  }, []);

  const handleAuth = useCallback((authData) => {
    setAuth(authData);
    storeAuth(authData);
  }, []);

  const handleLogout = useCallback(() => {
    clearAuth();
    setAuth(null);
    handleReset();
  }, [handleReset]);

  // If not authenticated, show login/signup
  if (!auth) {
    return <AuthPage onAuth={handleAuth} />;
  }

  return (
    <div className="app-container">
      <header className="app-header">
        <Activity size={32} color="var(--accent-green)" />
        <div>
          <h1>Fintech Loan Portfolio Agent</h1>
          <p className="subtitle">AI-Powered Analytics </p>
        </div>
        <div className="header-user">
          <span className="header-username">{auth.username}</span>
          <button className="btn-logout" onClick={handleLogout} title="Logout">
            <LogOut size={16} /> Logout
          </button>
        </div>
      </header>

      {error && (
        <div className="card" style={{ borderColor: 'var(--accent-red)' }}>
          <p style={{ color: 'var(--accent-red)' }}>{error}</p>
        </div>
      )}

      {phase === 'upload' && (
        <UploadArea
          files={files}
          csvPaths={csvPaths}
          onUpload={handleUpload}
          onRemove={(idx) => {
            setFiles(prev => prev.filter((_, i) => i !== idx));
            setCsvPaths(prev => prev.filter((_, i) => i !== idx));
          }}
          onAnalyze={handleAnalyze}
        />
      )}

      {phase === 'running' && (
        <ProgressTracker
          stages={STAGES}
          stageStatus={stageStatus}
          activeAgent={activeAgent}
          progress={progress}
        />
      )}

      {phase === 'done' && result && (
        <div className={`main-with-sidebar ${chatOpen ? 'sidebar-open' : ''}`}>
          <div className="main-content">
            <ResultsDashboard result={result} onReset={handleReset} />
          </div>
          {sessionId && (
            <ChatSidebar
              sessionId={sessionId}
              open={chatOpen}
              onToggle={() => setChatOpen(o => !o)}
              authToken={auth?.token}
            />
          )}
        </div>
      )}
    </div>
  );
}
