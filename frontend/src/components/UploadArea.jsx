import { useState, useRef, useCallback } from 'react';
import { Upload, FileSpreadsheet, X, Zap } from 'lucide-react';

export default function UploadArea({ files, csvPaths, onUpload, onRemove, onAnalyze }) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const handleFiles = useCallback((fileList) => {
    const csvFiles = Array.from(fileList).filter(f => f.name.endsWith('.csv'));
    if (csvFiles.length) onUpload(csvFiles);
  }, [onUpload]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div>
      <div
        className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <Upload size={48} color="var(--accent-green)" />
        <p>Drop CSV files here or click to browse</p>
        <p className="hint">Supports: Loans, Transactions, Borrowers, Collateral, Collections</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".csv"
          style={{ display: 'none' }}
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {files.length > 0 && (
        <>
          <div className="file-list">
            {files.map((f, i) => (
              <div key={i} className="file-chip">
                <FileSpreadsheet size={14} color="var(--accent-green)" />
                <span>{f.name}</span>
                <span className="size">{formatSize(f.size)}</span>
                <button onClick={(e) => { e.stopPropagation(); onRemove(i); }}>
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
            <button
              className="btn btn-primary"
              disabled={!csvPaths.length}
              onClick={onAnalyze}
            >
              <Zap size={18} />
              {csvPaths.length ? 'Generate Metrics' : 'Uploading...'}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
