import { useState, useCallback } from 'react';
import UploadArea from './components/UploadArea';
import ProgressTracker from './components/ProgressTracker';
import ResultsDashboard from './components/ResultsDashboard';
import { Activity } from 'lucide-react';

const API = '/api';
// SSE requires direct connection — Vite's proxy buffers streaming responses
const BACKEND = 'http://localhost:8000';

export default function App() {
  const [files, setFiles] = useState([]);
  const [csvPaths, setCsvPaths] = useState([]);
  const [phase, setPhase] = useState('upload'); // upload | running | done
  const [progress, setProgress] = useState([]);
  const [activeAgent, setActiveAgent] = useState('');
  const [stageStatus, setStageStatus] = useState({});
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

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
      const resp = await fetch(`${API}/upload`, { method: 'POST', body: formData });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setCsvPaths(data.csv_paths);
    } catch (e) {
      setError(`Upload failed: ${e.message}`);
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
        headers: { 'Content-Type': 'application/json' },
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

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6);
            try {
              const event = JSON.parse(jsonStr);
              handleSSEEvent(event);
            } catch { /* skip parse errors */ }
          }
        }
      }
    } catch (e) {
      setError(`Connection error: ${e.message}`);
      setPhase('upload');
    }
  }, [csvPaths]);

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
      setPhase('done');
      setStageStatus(prev => {
        const next = { ...prev };
        Object.keys(next).forEach(k => { if (next[k] === 'active') next[k] = 'completed'; });
        return next;
      });
    }
  }, []);

  const handleReset = useCallback(() => {
    setFiles([]);
    setCsvPaths([]);
    setPhase('upload');
    setProgress([]);
    setStageStatus({});
    setResult(null);
    setError(null);
    setActiveAgent('');
  }, []);

  return (
    <div className="app-container">
      <header className="app-header">
        <Activity size={32} color="var(--accent-green)" />
        <div>
          <h1>Fintech Loan Portfolio Agent</h1>
          <p className="subtitle">AI-Powered Analytics • Google Gemini • LangGraph</p>
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
        <ResultsDashboard result={result} onReset={handleReset} />
      )}
    </div>
  );
}
