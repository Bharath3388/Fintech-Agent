import { useState, useMemo, useRef, useEffect } from 'react';
import { RotateCcw, BarChart3, Table, FileText, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import MetricCard from './MetricCard';

export default function ResultsDashboard({ result, onReset }) {
  const [tab, setTab] = useState('metrics');

  const summary = result.summary || {};
  const metrics = result.metrics || {};
  const charts = result.charts || {};
  const schema = result.schema || {};

  const sortedMetrics = useMemo(() => {
    return Object.entries(metrics).sort(([a], [b]) => a.localeCompare(b));
  }, [metrics]);

  return (
    <div>
      {/* Action bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 600 }}>Analysis Results</h2>
        <button className="btn btn-secondary" onClick={onReset}>
          <RotateCcw size={16} /> New Analysis
        </button>
      </div>

      {/* Summary stats */}
      <div className="summary-bar">
        <div className="summary-stat ok">
          <div className="value">{summary.ok || 0}</div>
          <div className="label">Computed</div>
        </div>
        <div className="summary-stat skip">
          <div className="value">{summary.skipped || 0}</div>
          <div className="label">Skipped</div>
        </div>
        <div className="summary-stat err">
          <div className="value">{summary.errors || 0}</div>
          <div className="label">Errors</div>
        </div>
        <div className="summary-stat chart">
          <div className="value">{summary.charts_generated || 0}</div>
          <div className="label">Charts</div>
        </div>
        <div className="summary-stat" style={{ borderColor: 'var(--accent-purple)' }}>
          <div className="value" style={{ color: 'var(--accent-purple)' }}>
            {schema.fields_mapped || 0}
          </div>
          <div className="label">Fields Mapped</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        <button className={`tab ${tab === 'metrics' ? 'active' : ''}`} onClick={() => setTab('metrics')}>
          <BarChart3 size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
          Metrics & Charts
        </button>
        <button className={`tab ${tab === 'schema' ? 'active' : ''}`} onClick={() => setTab('schema')}>
          <Table size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
          Schema Mapping
        </button>
        <button className={`tab ${tab === 'log' ? 'active' : ''}`} onClick={() => setTab('log')}>
          <FileText size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
          Agent Log
        </button>
      </div>

      {/* Tab content */}
      {tab === 'metrics' && (
        <div className="metrics-grid">
          {sortedMetrics.map(([mid, m]) => (
            <MetricCard key={mid} metric={m} chart={charts[mid]} />
          ))}
        </div>
      )}

      {tab === 'schema' && <SchemaTab schema={schema} />}
      {tab === 'log' && <LogTab logs={result.agent_log || []} />}
    </div>
  );
}

function SchemaTab({ schema }) {
  const mappings = schema.field_mappings || {};
  const nonComputable = schema.non_computable_metrics || {};

  return (
    <div>
      {/* File classification */}
      <div className="card">
        <div className="card-title">File Classification</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
          {['loan_file', 'transaction_file', 'borrower_file', 'collateral_file', 'collections_file'].map(key => (
            <div key={key} style={{
              padding: '10px 14px', borderRadius: 8,
              background: schema[key] ? 'rgba(74, 222, 128, 0.08)' : 'rgba(239, 68, 68, 0.05)',
              border: `1px solid ${schema[key] ? 'rgba(74,222,128,0.2)' : 'var(--border)'}`,
            }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                {key.replace('_file', '').replace('_', ' ')}
              </div>
              <div style={{ fontSize: 13, marginTop: 4, color: schema[key] ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                {schema[key] || 'Not detected'}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Field mappings */}
      <div className="card">
        <div className="card-title">Field Mappings ({Object.keys(mappings).length})</div>
        <div style={{ maxHeight: 400, overflowY: 'auto' }}>
          <table className="schema-table">
            <thead>
              <tr><th>Canonical Field</th><th>File</th><th>Column</th><th>Confidence</th></tr>
            </thead>
            <tbody>
              {Object.entries(mappings).sort().map(([canonical, m]) => (
                <tr key={canonical}>
                  <td style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{canonical}</td>
                  <td>{m.file}</td>
                  <td style={{ fontFamily: 'monospace' }}>{m.column}</td>
                  <td className={`confidence-${m.confidence}`}>{m.confidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Non-computable metrics */}
      {Object.keys(nonComputable).length > 0 && (
        <div className="card">
          <div className="card-title">
            <AlertTriangle size={16} color="var(--accent-orange)" />
            Non-Computable Metrics
          </div>
          {Object.entries(nonComputable).map(([mid, reason]) => (
            <div key={mid} className="metric-reason" style={{ marginBottom: 8 }}>
              <strong>{mid}</strong>: {reason}
            </div>
          ))}
        </div>
      )}

      {/* LLM Assessment */}
      {schema.llm_assessment && (
        <div className="card">
          <div className="card-title">AI Assessment</div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
            {schema.llm_assessment}
          </p>
        </div>
      )}
    </div>
  );
}

function LogTab({ logs }) {
  const ref = useRef(null);
  useEffect(() => { ref.current?.scrollTo(0, ref.current.scrollHeight); }, [logs]);

  return (
    <div className="card">
      <div className="card-title">Agent Activity Log</div>
      <div className="log-feed" ref={ref} style={{ maxHeight: 500 }}>
        {logs.map((msg, i) => (
          <div key={i} className={`log-entry ${msg.includes('ERROR') ? 'error' : msg.includes('OK') ? 'success' : ''}`}>
            <span className="msg">{msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
