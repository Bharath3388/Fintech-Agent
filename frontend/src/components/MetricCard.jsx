import { useState, useRef, useEffect, useMemo } from 'react';
import { ChevronDown, ChevronUp, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

export default function MetricCard({ metric, chart }) {
  const [expanded, setExpanded] = useState(false);
  const iframeRef = useRef(null);

  const statusIcon = {
    ok: <CheckCircle size={14} />,
    not_available: <AlertTriangle size={14} />,
    error: <XCircle size={14} />,
  };

  const hasChart = chart && !chart.error && chart.html_snippet;
  const hasPlotlyJson = chart && !chart.error && chart.plotly_json;

  // Build a self-contained HTML document for the iframe
  const chartHtml = useMemo(() => {
    if (!hasChart) return null;
    // Strip integrity/crossorigin attrs so Plotly CDN loads in sandboxed iframe
    const snippet = chart.html_snippet
      .replace(/\s*integrity="[^"]*"/g, '')
      .replace(/\s*crossorigin="[^"]*"/g, '')
      .replace(/width:\s*\d+px/g, 'width:100%');
    return `<!DOCTYPE html>
<html><head>
<style>body{margin:0;padding:0;background:#1a1a2e;overflow:auto}
.js-plotly-plot,.plot-container{width:100%!important}
.svg-container{width:100%!important}</style>
</head><body>${snippet}</body></html>`;
  }, [chart, hasChart]);

  // Reason for non-computable metrics
  const reason = metric.status !== 'ok'
    ? metric.data?.reason || metric.data?.error || metric.llm_insight || 'Not available'
    : null;

  return (
    <div className="metric-card">
      <div className="metric-header">
        <div>
          <span className="metric-id">{metric.metric_id}</span>
          <div className="metric-name">{metric.name}</div>
        </div>
        <span className={`status-badge ${metric.status}`}>
          {statusIcon[metric.status]} {metric.status === 'ok' ? 'Computed' : metric.status === 'not_available' ? 'Skipped' : 'Error'}
        </span>
      </div>

      {/* Reason for skip/error */}
      {reason && <div className="metric-reason">{reason}</div>}

      {/* Insight */}
      {metric.status === 'ok' && metric.llm_insight && (
        <div className="metric-insight">
          {metric.llm_insight.length > 200 && !expanded
            ? metric.llm_insight.slice(0, 200) + '...'
            : metric.llm_insight}
          {metric.llm_insight.length > 200 && (
            <button
              onClick={() => setExpanded(!expanded)}
              style={{
                background: 'none', border: 'none', color: 'var(--accent-blue)',
                cursor: 'pointer', fontSize: 12, marginLeft: 4,
              }}
            >
              {expanded ? 'less' : 'more'}
            </button>
          )}
        </div>
      )}

      {/* Interactive chart */}
      {hasChart && (
        <div className="chart-wrapper">
          <iframe
            ref={iframeRef}
            srcDoc={chartHtml}
            title={`${metric.metric_id} chart`}
            sandbox="allow-scripts"
            style={{ width: '100%', minHeight: 420, border: 'none', borderRadius: 8 }}
          />
        </div>
      )}

      {/* Chart error */}
      {chart && chart.error && (
        <div className="chart-error" style={{ marginTop: 10 }}>
          Chart generation failed: {chart.error}
        </div>
      )}
    </div>
  );
}
