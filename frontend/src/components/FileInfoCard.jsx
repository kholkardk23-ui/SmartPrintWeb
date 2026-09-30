import React from 'react';
import { FileText, CheckCircle2, Trash2, Layers, HardDrive } from 'lucide-react';

function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export default function FileInfoCard({ files, onRemoveFile, onClearAll }) {
  if (!files || files.length === 0) return null;

  const totalPages = files.reduce((acc, f) => acc + (f.page_count || 0), 0);
  const totalBytes = files.reduce((acc, f) => acc + (f.file_size || 0), 0);

  return (
    <div className="w-full max-w-xl mx-auto bg-white rounded-2xl border border-slate-200/90 p-5 sm:p-6 shadow-card transition-all">
      {/* Header Summary Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-4 mb-4 border-b border-slate-100">
        <div>
          <h3 className="text-base sm:text-lg font-bold text-slate-900">
            Uploaded Files ({files.length})
          </h3>
          <p className="text-xs sm:text-sm text-slate-500 font-medium mt-0.5 flex items-center gap-2">
            <span className="flex items-center gap-1">
              <Layers className="w-3.5 h-3.5 text-brand-600" />
              {totalPages} {totalPages === 1 ? 'page total' : 'pages total'}
            </span>
            <span>•</span>
            <span className="flex items-center gap-1">
              <HardDrive className="w-3.5 h-3.5 text-slate-400" />
              {formatFileSize(totalBytes)}
            </span>
          </p>
        </div>

        {files.length > 1 && (
          <button
            type="button"
            onClick={onClearAll}
            className="text-xs font-semibold text-slate-400 hover:text-rose-600 transition-colors px-2 py-1 rounded-lg hover:bg-rose-50 cursor-pointer"
          >
            Remove All
          </button>
        )}
      </div>

      {/* List of Uploaded Documents */}
      <div className="space-y-3">
        {files.map((file, index) => (
          <div
            key={file.file_id || index}
            className="flex items-start justify-between gap-3 p-3.5 rounded-xl bg-slate-50/80 hover:bg-slate-50 border border-slate-200/60 transition-colors"
          >
            <div className="flex items-start gap-3 min-w-0 flex-1">
              <div className="w-10 h-10 rounded-lg bg-brand-50 border border-brand-100 flex items-center justify-center text-brand-600 shrink-0 mt-0.5">
                <FileText className="w-5 h-5" />
              </div>

              <div className="min-w-0 flex-1">
                <p
                  className="text-sm font-bold text-slate-800 truncate"
                  title={file.original_filename}
                >
                  {file.original_filename}
                </p>

                <div className="mt-1 flex flex-wrap items-center gap-2.5 text-xs text-slate-500 font-medium">
                  <span>{formatFileSize(file.file_size)}</span>
                  <span className="inline-block w-1 h-1 rounded-full bg-slate-300" />
                  <span className="text-brand-700 font-semibold bg-brand-50 px-2 py-0.5 rounded border border-brand-100">
                    {file.page_count} {file.page_count === 1 ? 'page' : 'pages'}
                  </span>
                </div>

                <div className="mt-1.5 flex items-center gap-1 text-[11px] font-medium text-emerald-600">
                  <CheckCircle2 className="w-3 h-3" />
                  <span>Uploaded successfully</span>
                </div>
              </div>
            </div>

            {/* Remove individual file button */}
            <button
              type="button"
              onClick={() => onRemoveFile(file.file_id)}
              className="inline-flex items-center gap-1 text-xs font-semibold text-rose-500 hover:text-rose-700 hover:bg-rose-50 p-1.5 rounded-lg transition-colors cursor-pointer shrink-0"
              title="Remove this document"
            >
              <Trash2 className="w-4 h-4" />
              <span className="hidden sm:inline">Remove</span>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
