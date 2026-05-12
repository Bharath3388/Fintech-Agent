import { useState, useRef, useMemo, useCallback } from 'react';
import { CheckCircle, XCircle, AlertTriangle, ExternalLink } from 'lucide-react';

export default function MetricCard({ metric, chart }) {
  const [expanded, setExpanded] = useState(false);
  const iframeRef = useRef(null);

  const statusIcon = {
    ok: <CheckCircle size={14} />,
    not_available: <AlertTriangle size={14} />,
    error: <XCircle size={14} />,
  };

  const hasChart = chart && !chart.error && chart.html_snippet;

  // Build a self-contained HTML document for the iframe
  const chartHtml = useMemo(() => {
    if (!hasChart) return null;
    const snippet = chart.html_snippet
      .replace(/\s*integrity="[^"]*"/g, '')
      .replace(/\s*crossorigin="[^"]*"/g, '')
      .replace(/width:\s*\d+px/g, 'width:100%');
    return `<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<style>body{margin:0;padding:0;background:#1a1a2e;overflow:auto}
.js-plotly-plot,.plot-container{width:100%!important}
.svg-container{width:100%!important}</style>
</head><body>${snippet}</body></html>`;
  }, [chart, hasChart]);

  // Open the chart in a new browser tab as a standalone full-page HTML
  const openInNewPage = useCallback(() => {
    if (!chartHtml) return;
    // Make it look good full-screen: force responsive sizing
    const fullPageHtml = chartHtml
      .replace('overflow:auto', 'overflow:hidden')
      .replace(
        '</style>',
        `
.js-plotly-plot,.plot-container,.svg-container{width:100vw!important;height:100vh!important}
.plotly-graph-div{width:100vw!important;height:100vh!important}
</style>`,
      );
    const blob = new Blob([fullPageHtml], { type: 'text/html' });
    const url  = URL.createObjectURL(blob);
    const win  = window.open(url, '_blank');
    // Revoke the object URL after the tab has loaded to free memory
    if (win) win.addEventListener('load', () => URL.revokeObjectURL(url), { once: true });
    else URL.revokeObjectURL(url); // popup blocked fallback
  }, [chartHtml]);

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
          <div className="chart-toolbar">
            <button
              className="chart-open-btn"
              onClick={openInNewPage}
              title="Open chart in new tab (full screen)"
            >
              <ExternalLink size={13} />
              Open in new page
            </button>
          </div>
          <iframe
            ref={iframeRef}
            srcDoc={chartHtml}
            title={`${metric.metric_id} chart`}
            sandbox="allow-scripts"
            style={{ width: '100%', minHeight: 420, border: 'none', borderRadius: '0 0 8px 8px' }}
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
