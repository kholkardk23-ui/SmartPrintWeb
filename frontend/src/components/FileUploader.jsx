import React, { useState, useRef } from 'react';
import { UploadCloud, FileUp, AlertCircle, Loader2, FileText, X, Files } from 'lucide-react';

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB per file

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

export default function FileUploader({
  onFilesSelected,
  isUploading,
  uploadProgress,
  uploadingFiles,
  errorMessage,
  onClearError,
  compact = false,
}) {
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const validateAndProcessFiles = (fileList) => {
    onClearError();
    if (!fileList || fileList.length === 0) return;

    const validFiles = [];
    const errorItems = [];

    Array.from(fileList).forEach((file) => {
      const hasPdfExtension = file.name.toLowerCase().endsWith('.pdf');
      const isPdfMime = file.type === 'application/pdf' || file.type === '';

      if (!hasPdfExtension && !isPdfMime) {
        errorItems.push(`"${file.name}" is not a PDF file.`);
        return;
      }

      if (file.size > MAX_FILE_SIZE_BYTES) {
        errorItems.push(`"${file.name}" exceeds the 10 MB limit.`);
        return;
      }

      if (file.size === 0) {
        errorItems.push(`"${file.name}" is an empty file.`);
        return;
      }

      validFiles.push(file);
    });

    if (errorItems.length > 0) {
      const msg =
        errorItems.length === 1
          ? `Please select a valid PDF file (max 10 MB): ${errorItems[0]}`
          : `Some files could not be uploaded:\n• ${errorItems.join('\n• ')}`;
      onFilesSelected(null, msg);
      return;
    }

    if (validFiles.length > 0) {
      onFilesSelected(validFiles, null);
    }
  };

  const handleFileChange = (e) => {
    const files = e.target.files;
    validateAndProcessFiles(files);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isUploading) {
      setIsDragOver(true);
    }
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    if (isUploading) return;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndProcessFiles(e.dataTransfer.files);
    }
  };

  const triggerFileInput = () => {
    if (!isUploading && fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  // Compact variant when a document is already uploaded
  if (compact) {
    return (
      <div className="w-full max-w-xl mx-auto">
        <input
          ref={fileInputRef}
          id="pdf-upload-input-compact"
          type="file"
          multiple
          accept="application/pdf,.pdf"
          onChange={handleFileChange}
          disabled={isUploading}
          className="hidden"
        />
        <button
          type="button"
          onClick={triggerFileInput}
          disabled={isUploading}
          className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-2xl border-2 border-dashed border-brand-300 hover:border-brand-500 bg-brand-50/50 hover:bg-brand-50 text-brand-700 font-bold text-sm transition-all cursor-pointer shadow-sm"
        >
          {isUploading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin text-brand-600" />
              <span>Uploading... {uploadProgress}%</span>
            </>
          ) : (
            <>
              <Files className="w-4 h-4 text-brand-600" />
              <span>+ Add More Documents</span>
            </>
          )}
        </button>

        {errorMessage && (
          <div
            role="alert"
            className="mt-3 p-3.5 rounded-2xl bg-red-50 border border-red-200 flex items-start gap-2.5 text-red-800 text-xs sm:text-sm animate-fade-in shadow-sm"
          >
            <AlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
            <div className="flex-1 whitespace-pre-line">{errorMessage}</div>
            <button
              type="button"
              onClick={onClearError}
              className="text-red-400 hover:text-red-600 p-1"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    );
  }

  const totalUploadingBytes = uploadingFiles
    ? uploadingFiles.reduce((acc, f) => acc + (f.size || 0), 0)
    : 0;

  return (
    <div className="w-full max-w-xl mx-auto">
      {/* Large Upload Card */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative rounded-3xl border-2 border-dashed transition-all duration-200 bg-white p-6 sm:p-10 text-center shadow-card ${
          isDragOver
            ? 'border-brand-500 bg-brand-50/50 scale-[1.01]'
            : 'border-slate-300 hover:border-brand-400'
        } ${isUploading ? 'opacity-95' : ''}`}
      >
        <input
          ref={fileInputRef}
          id="pdf-upload-input"
          type="file"
          multiple
          accept="application/pdf,.pdf"
          onChange={handleFileChange}
          disabled={isUploading}
          className="hidden"
        />

        {/* Cloud Upload Icon */}
        <div className="mx-auto w-16 h-16 sm:w-20 sm:h-20 rounded-2xl bg-brand-50 border border-brand-100 flex items-center justify-center text-brand-600 mb-5 shadow-inner">
          {isUploading ? (
            <Loader2 className="w-8 h-8 sm:w-10 sm:h-10 animate-spin text-brand-600" />
          ) : (
            <UploadCloud className="w-8 h-8 sm:w-10 sm:h-10 text-brand-600" />
          )}
        </div>

        {/* Active Uploading State Display */}
        {isUploading && uploadingFiles && uploadingFiles.length > 0 ? (
          <div className="max-w-md mx-auto my-5 p-4 rounded-2xl bg-brand-50/70 border border-brand-200/80 text-left animate-fade-in">
            <div className="flex items-center justify-between gap-3 mb-2">
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-brand-600 shrink-0" />
                <span className="text-sm font-bold text-slate-900">
                  Uploading {uploadingFiles.length === 1 ? uploadingFiles[0].name : `${uploadingFiles.length} files`}
                </span>
              </div>
              <span className="text-xs font-semibold text-slate-500">
                {formatBytes(totalUploadingBytes)}
              </span>
            </div>

            {/* List of files being uploaded if multiple */}
            {uploadingFiles.length > 1 && (
              <div className="space-y-1 mb-3 max-h-24 overflow-y-auto">
                {uploadingFiles.map((file, idx) => (
                  <div key={idx} className="text-xs text-slate-600 truncate flex items-center justify-between">
                    <span className="truncate max-w-[200px]">• {file.name}</span>
                    <span className="text-[11px] text-slate-400">{formatBytes(file.size)}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Progress Bar */}
            <div className="w-full bg-white rounded-full h-2.5 overflow-hidden border border-brand-200 mt-2">
              <div
                className="bg-brand-600 h-full rounded-full transition-all duration-200"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <div className="mt-1.5 flex justify-between text-[11px] font-semibold text-brand-800">
              <span>Sending to server</span>
              <span>{uploadProgress}%</span>
            </div>
          </div>
        ) : (
          /* Choose PDF Action Area */
          <div className="flex flex-col items-center">
            <button
              id="choose-pdf-button"
              type="button"
              onClick={triggerFileInput}
              disabled={isUploading}
              className="w-full sm:w-auto min-w-[220px] inline-flex items-center justify-center gap-2.5 px-8 py-4 rounded-2xl text-base font-bold text-white bg-brand-600 hover:bg-brand-700 active:scale-[0.98] transition-all shadow-md shadow-brand-600/25 cursor-pointer touch-manipulation"
            >
              <FileUp className="w-5 h-5" />
              <span>Choose PDF</span>
            </button>

            <p className="text-sm sm:text-base text-slate-500 mt-3 font-medium">
              or drag and drop your file here
            </p>
          </div>
        )}

        <p className="text-xs text-slate-400 mt-5 pt-4 border-t border-slate-100">
          PDF format only • Maximum file size: 10 MB
        </p>
      </div>

      {/* Error Alert Display */}
      {errorMessage && (
        <div
          role="alert"
          className="mt-4 p-4 rounded-2xl bg-red-50 border border-red-200 flex items-start gap-3 text-red-800 text-sm animate-fade-in shadow-sm"
        >
          <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold text-red-900">Upload Issue</p>
            <p className="text-red-700 mt-0.5 whitespace-pre-line">{errorMessage}</p>
          </div>
          <button
            type="button"
            onClick={onClearError}
            className="text-red-400 hover:text-red-600 p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
