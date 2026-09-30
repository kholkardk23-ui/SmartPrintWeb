import React from 'react';
import { CheckCircle2, ArrowRight, RotateCcw, FileText, Layers, HardDrive, Check, Trash2 } from 'lucide-react';

function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export default function DocumentReadyCard({ files, onContinue, onReset, onRemoveFile }) {
  if (!files || files.length === 0) return null;

  const isMultiple = files.length > 1;
  const totalPages = files.reduce((acc, f) => acc + (f.page_count || 0), 0);
  const totalBytes = files.reduce((acc, f) => acc + (f.file_size || 0), 0);

  return (
    <div className="w-full max-w-xl mx-auto bg-white rounded-3xl border border-slate-200/90 p-6 sm:p-8 shadow-card animate-fade-in">
      {/* Upload Successful Banner */}
      <div className="flex items-center justify-between gap-2.5 pb-4 mb-5 border-b border-slate-100">
        <div className="flex items-center gap-2.5 text-emerald-600 font-bold text-lg sm:text-xl">
          <div className="w-8 h-8 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
          </div>
          <span>✓ Upload Successful</span>
        </div>

        {isMultiple && (
          <span className="text-xs font-bold text-brand-700 bg-brand-50 border border-brand-200 px-2.5 py-1 rounded-full">
            {files.length} Files
          </span>
        )}
      </div>

      {/* Main Metadata Display */}
      <div className="bg-slate-50/80 rounded-2xl border border-slate-200/70 divide-y divide-slate-200/60 overflow-hidden text-sm sm:text-base mb-5">
        {/* File Name(s) */}
        <div className="p-4 flex items-center justify-between gap-3">
          <span className="text-slate-500 font-medium flex items-center gap-2">
            <FileText className="w-4 h-4 text-slate-400 shrink-0" />
            <span>{isMultiple ? 'Files:' : 'File:'}</span>
          </span>
          <span
            className="font-bold text-slate-900 text-right truncate max-w-[220px] sm:max-w-[280px]"
            title={isMultiple ? `${files.length} documents uploaded` : files[0].original_filename}
          >
            {isMultiple ? `${files.length} documents uploaded` : files[0].original_filename}
          </span>
        </div>

        {/* Pages (backend-calculated) */}
        <div className="p-4 flex items-center justify-between gap-3">
          <span className="text-slate-500 font-medium flex items-center gap-2">
            <Layers className="w-4 h-4 text-brand-500 shrink-0" />
            <span>Pages:</span>
          </span>
          <span className="font-extrabold text-brand-700 bg-brand-50 border border-brand-200 px-3 py-0.5 rounded-full text-sm">
            {totalPages}
          </span>
        </div>

        {/* Size */}
        <div className="p-4 flex items-center justify-between gap-3">
          <span className="text-slate-500 font-medium flex items-center gap-2">
            <HardDrive className="w-4 h-4 text-slate-400 shrink-0" />
            <span>Size:</span>
          </span>
          <span className="font-semibold text-slate-700">
            {formatFileSize(totalBytes)}
          </span>
        </div>

        {/* Status */}
        <div className="p-4 flex items-center justify-between gap-3">
          <span className="text-slate-500 font-medium flex items-center gap-2">
            <Check className="w-4 h-4 text-emerald-500 shrink-0" />
            <span>Status:</span>
          </span>
          <span className="inline-flex items-center gap-1.5 font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-0.5 rounded-full text-xs sm:text-sm">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            Ready
          </span>
        </div>
      </div>

      {/* Itemized List if Multiple Files */}
      {isMultiple && (
        <div className="mb-5 space-y-2">
          <p className="text-xs font-bold text-slate-500 uppercase tracking-wider px-1">
            Uploaded Documents
          </p>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {files.map((file, idx) => (
              <div
                key={file.file_id || idx}
                className="flex items-center justify-between gap-3 p-3 rounded-xl bg-white border border-slate-200 text-xs sm:text-sm"
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  <div className="w-7 h-7 rounded-lg bg-brand-50 flex items-center justify-center text-brand-600 shrink-0">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-slate-800 truncate" title={file.original_filename}>
                      {file.original_filename}
                    </p>
                    <p className="text-[11px] text-slate-500">
                      {file.page_count} {file.page_count === 1 ? 'page' : 'pages'} • {formatFileSize(file.file_size)}
                    </p>
                  </div>
                </div>

                {onRemoveFile && (
                  <button
                    type="button"
                    onClick={() => onRemoveFile(file.file_id)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                    title="Remove file"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <button
          id="continue-button"
          type="button"
          onClick={onContinue}
          className="w-full flex-1 inline-flex items-center justify-center gap-2 py-4 px-6 rounded-2xl font-bold text-base text-white bg-brand-600 hover:bg-brand-700 active:scale-[0.99] transition-all shadow-md shadow-brand-600/25 cursor-pointer touch-manipulation"
        >
          <span>Continue</span>
          <ArrowRight className="w-5 h-5" />
        </button>

        <button
          type="button"
          onClick={onReset}
          className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 py-4 px-5 rounded-2xl font-semibold text-sm text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200/80 transition-colors cursor-pointer"
        >
          <RotateCcw className="w-4 h-4" />
          <span>Upload Another</span>
        </button>
      </div>
    </div>
  );
}
