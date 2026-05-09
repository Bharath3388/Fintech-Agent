import { useEffect, useRef } from 'react';
import { CheckCircle, Loader, AlertCircle, Circle } from 'lucide-react';

export default function ProgressTracker({ stages, stageStatus, activeAgent, progress }) {
  const logRef = useRef(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [progress]);

  const getStageIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle size={18} />;
      case 'active': return <Loader size={18} className="spin" />;
      case 'error': return <AlertCircle size={18} />;
      default: return <Circle size={18} />;
    }
  };

  const getStageClass = (key) => {
    return stageStatus[key] || '';
  };

  return (
    <div className="progress-container">
      <div className="card">
        <div className="card-title">
          <Loader size={18} color="var(--accent-green)" style={{ animation: 'spin 1s linear infinite' }} />
          Pipeline Running — {activeAgent || 'Initializing...'}
        </div>

        {/* Stage indicators */}
        <div className="pipeline-stages">
          {stages.map((s, i) => (
            <div key={s.key} className={`stage ${getStageClass(s.key)}`}>
              {i < stages.length - 1 && <div className="stage-connector" />}
              <div className="stage-dot">{getStageIcon(getStageClass(s.key))}</div>
              <div className="stage-label">{s.label}</div>
            </div>
          ))}
        </div>

        {/* Live log feed */}
        <div className="log-feed" ref={logRef}>
          {progress.map((entry, i) => (
            <div key={i} className={`log-entry ${entry.type}`}>
              <span className="agent">[{entry.agent}]</span>
              <span className="msg">
                {entry.type === 'step_start' && `Step ${entry.step}: ${entry.description}...`}
                {entry.type === 'step_end' && `Step ${entry.step}: Done (${entry.duration}s) ${entry.summary || ''}`}
                {entry.type === 'step_fail' && `Step ${entry.step}: FAILED — ${entry.error}`}
                {entry.type === 'info' && entry.message}
                {entry.type === 'success' && `✔ ${entry.message}`}
                {entry.type === 'warning' && `⚠ ${entry.message}`}
                {entry.type === 'error' && `✖ ${entry.message}`}
              </span>
            </div>
          ))}
          {progress.length === 0 && (
            <div className="log-entry">
              <span className="msg" style={{ color: 'var(--text-muted)' }}>
                Waiting for pipeline to start...
              </span>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .spin { animation: spin 1s linear infinite; }
      `}</style>
    </div>
  );
}
