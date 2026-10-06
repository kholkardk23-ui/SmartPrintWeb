import React, { useState, useMemo, useEffect } from 'react';
import {
  Sliders,
  ArrowLeft,
  Plus,
  Minus,
  CheckCircle2,
  FileText,
  Printer,
  CreditCard,
  AlertCircle,
  Loader2,
  Layers,
  Sparkles,
  Info,
  RotateCcw,
  Check,
} from 'lucide-react';
import { createOrder } from '../services/api';

/**
 * Format bytes to readable size string
 */
function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

/**
 * Client-side validation & page count calculation for custom page ranges.
 * Mirrors backend rules for instant user UX feedback.
 * Backend remains authoritative.
 */
function parseCustomRange(rangeStr, totalPages) {
  if (!rangeStr || !rangeStr.trim()) {
    return {
      isValid: false,
      error: 'Please enter page numbers or ranges (e.g. 1-3, 5).',
      count: 0,
      pages: [],
    };
  }

  const cleaned = rangeStr.trim();

  // Basic syntax check
  if (!/^[0-9\s,-]+$/.test(cleaned)) {
    return {
      isValid: false,
      error: 'Invalid characters in page range. Use numbers, hyphens, and commas only.',
      count: 0,
      pages: [],
    };
  }

  if (cleaned.startsWith(',') || cleaned.endsWith(',') || /,\s*,/.test(cleaned)) {
    return {
      isValid: false,
      error: 'Invalid format. Commas must separate page numbers or ranges.',
      count: 0,
      pages: [],
    };
  }

  const parts = cleaned.split(',').map((p) => p.trim());
  const selectedSet = new Set();

  for (const part of parts) {
    if (!part) {
      return {
        isValid: false,
        error: 'Empty section in page range.',
        count: 0,
        pages: [],
      };
    }

    if (part.includes('-')) {
      const match = part.match(/^(\d+)\s*-\s*(\d+)$/);
      if (!match) {
        return {
          isValid: false,
          error: `Invalid range format '${part}'. Expected format like '1-3'.`,
          count: 0,
          pages: [],
        };
      }

      const start = parseInt(match[1], 10);
      const end = parseInt(match[2], 10);

      if (start < 1) {
        return {
          isValid: false,
          error: `Page numbers must be 1 or greater. Got '${start}'.`,
          count: 0,
          pages: [],
        };
      }
      if (end < start) {
        return {
          isValid: false,
          error: `Start page (${start}) cannot be greater than end page (${end}).`,
          count: 0,
          pages: [],
        };
      }
      if (end > totalPages) {
        return {
          isValid: false,
          error: `Page range '${part}' exceeds total document pages (${totalPages}).`,
          count: 0,
          pages: [],
        };
      }

      for (let p = start; p <= end; p++) {
        selectedSet.add(p);
      }
    } else {
      if (!/^\d+$/.test(part)) {
        return {
          isValid: false,
          error: `Invalid page '${part}'. Must be numeric.`,
          count: 0,
          pages: [],
        };
      }

      const pageNum = parseInt(part, 10);
      if (pageNum < 1) {
        return {
          isValid: false,
          error: `Page numbers must be 1 or greater. Got '${pageNum}'.`,
          count: 0,
          pages: [],
        };
      }
      if (pageNum > totalPages) {
        return {
          isValid: false,
          error: `Page ${pageNum} exceeds total document pages (${totalPages}).`,
          count: 0,
          pages: [],
        };
      }

      selectedSet.add(pageNum);
    }
  }

  const sortedPages = Array.from(selectedSet).sort((a, b) => a - b);
  return {
    isValid: sortedPages.length > 0,
    error: sortedPages.length === 0 ? 'No pages selected.' : null,
    count: sortedPages.length,
    pages: sortedPages,
  };
}

export default function PrintingOptionsScreen({
  files,
  onBack,
  onReset,
  onOrderCreated,
}) {
  // Support file selection if multiple files were uploaded, default to first
  const [selectedFileIndex, setSelectedFileIndex] = useState(0);
  const activeFile = files && files.length > 0 ? files[selectedFileIndex] || files[0] : null;

  // Configuration state with default values per specifications
  const [copies, setCopies] = useState(1);
  const [colorMode, setColorMode] = useState('bw'); // 'bw' or 'color'
  const [duplex, setDuplex] = useState(false); // false = single side, true = double side
  const [pageRangeType, setPageRangeType] = useState('all'); // 'all' or 'custom'
  const [customRange, setCustomRange] = useState('');

  // UI status state
  const [isCreatingOrder, setIsCreatingOrder] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  const totalDocPages = activeFile?.page_count || 1;

  // Calculate parsed custom range validation
  const customRangeValidation = useMemo(() => {
    if (pageRangeType !== 'custom') return { isValid: true, count: totalDocPages, error: null };
    return parseCustomRange(customRange, totalDocPages);
  }, [pageRangeType, customRange, totalDocPages]);

  // Selected page count (estimated on frontend)
  const selectedPageCount = useMemo(() => {
    if (pageRangeType === 'all') return totalDocPages;
    return customRangeValidation.isValid ? customRangeValidation.count : 0;
  }, [pageRangeType, totalDocPages, customRangeValidation]);

  // Pricing constants (INR per page)
  const pricePerPage = colorMode === 'color' ? 10.0 : 3.0;

  // Estimated physical sheets calculation:
  // Single side: pages * copies
  // Double side: Math.ceil(pages / 2) * copies
  const estimatedSheets = useMemo(() => {
    if (selectedPageCount <= 0) return 0;
    const sheetsPerCopy = duplex ? Math.ceil(selectedPageCount / 2) : selectedPageCount;
    return sheetsPerCopy * copies;
  }, [selectedPageCount, duplex, copies]);

  // Estimated total price in frontend (clearly noted as estimate)
  const estimatedTotalPrice = useMemo(() => {
    return selectedPageCount * copies * pricePerPage;
  }, [selectedPageCount, copies, pricePerPage]);

  // Change copies count with boundary safety (1-100)
  const handleCopiesChange = (delta) => {
    setCopies((prev) => {
      const next = prev + delta;
      return Math.min(100, Math.max(1, next));
    });
  };

  const handleCopiesInput = (e) => {
    const val = parseInt(e.target.value, 10);
    if (isNaN(val)) {
      setCopies(1);
    } else {
      setCopies(Math.min(100, Math.max(1, val)));
    }
  };

  // Submit order to authoritative backend
  const handleCreateOrder = async () => {
    setErrorMessage(null);

    if (!activeFile || !activeFile.file_id) {
      setErrorMessage('No valid uploaded document found. Please upload a PDF file first.');
      return;
    }

    // Frontend validation for custom page range
    if (pageRangeType === 'custom') {
      if (!customRange.trim()) {
        setErrorMessage('Please enter the page range you want to print (e.g. 1-3, 5).');
        return;
      }
      if (!customRangeValidation.isValid) {
        setErrorMessage(customRangeValidation.error || 'Invalid page range format.');
        return;
      }
    }

    const payload = {
  file_ids: files.map((file) => file.file_id),
  copies: Number(copies),
  color_mode: colorMode,
  duplex: Boolean(duplex),
  page_range: pageRangeType === 'all' ? 'all' : customRange.trim(),
};

    setIsCreatingOrder(true);

    try {
      // Authoritative order creation via POST /api/orders
      const order = await createOrder(payload);

      if (onOrderCreated) {
        onOrderCreated(order);
      }
    } catch (err) {
      setErrorMessage(
        err.message || 'Failed to create print order. Please check your options and try again.'
      );
    } finally {
      setIsCreatingOrder(false);
    }
  };

  if (!activeFile) {
    return (
      <div className="w-full max-w-xl mx-auto animate-fade-in">
        <div className="bg-white rounded-3xl border border-slate-200 p-8 text-center shadow-card">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600 mb-4">
            <AlertCircle className="w-7 h-7" />
          </div>
          <h3 className="text-xl font-bold text-slate-900 mb-2">No Document Available</h3>
          <p className="text-slate-600 font-medium text-sm mb-6">
            Please upload a PDF document before selecting printing options.
          </p>
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-2 px-6 py-3.5 rounded-2xl bg-brand-600 text-white font-bold hover:bg-brand-700 transition-colors shadow-md shadow-brand-500/20"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Go to Upload</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-xl mx-auto animate-fade-in pb-8">
      {/* Top Breadcrumb & Status */}
      <div className="mb-4 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          disabled={isCreatingOrder}
          className="inline-flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-brand-600 transition-colors disabled:opacity-50 p-1"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Document</span>
        </button>

        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-bold border border-emerald-200 shadow-sm">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
          <span>Step 2 of 4 • Options</span>
        </span>
      </div>

      {/* Main Card */}
      <div className="bg-white rounded-3xl border border-slate-200/90 p-5 sm:p-8 shadow-card">
        {/* Header */}
        <div className="flex items-center gap-3.5 mb-6 pb-5 border-b border-slate-100">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-brand-50 to-brand-100/80 border border-brand-200/60 flex items-center justify-center text-brand-600 shadow-sm shrink-0">
            <Sliders className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight">
              Printing Options
            </h2>
            <p className="text-xs sm:text-sm text-slate-500 font-medium">
              Configure copies, color, duplex, and pages
            </p>
          </div>
        </div>

        {/* Multi-document switcher (if user uploaded multiple files) */}
        {files && files.length > 1 && (
          <div className="mb-5 p-3 rounded-2xl bg-brand-50/60 border border-brand-100">
            <label className="block text-xs font-bold text-brand-900 mb-1.5 uppercase tracking-wider">
              Select Document to Print ({files.length} available):
            </label>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {files.map((f, idx) => (
                <button
                  key={f.file_id || idx}
                  type="button"
                  onClick={() => setSelectedFileIndex(idx)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold shrink-0 transition-all ${
                    selectedFileIndex === idx
                      ? 'bg-brand-600 text-white shadow-sm'
                      : 'bg-white text-slate-700 hover:bg-slate-100 border border-slate-200'
                  }`}
                >
                  Doc {idx + 1}: {f.original_filename?.slice(0, 15)}...
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Uploaded Document Info Card */}
        <div className="p-4 rounded-2xl bg-slate-50/90 border border-slate-200/80 mb-6 transition-all">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <div className="w-11 h-11 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-brand-600 shadow-sm shrink-0">
                <FileText className="w-6 h-6" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-bold text-slate-900 text-sm sm:text-base truncate" title={activeFile.original_filename}>
                  {activeFile.original_filename}
                </p>
                <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-500 font-medium">
                  <span className="inline-flex items-center gap-1 text-brand-700 font-semibold">
                    <Layers className="w-3.5 h-3.5" />
                    {totalDocPages} {totalDocPages === 1 ? 'page' : 'pages'}
                  </span>
                  <span>•</span>
                  <span>{formatFileSize(activeFile.file_size)}</span>
                </div>
              </div>
            </div>

            <span className="hidden sm:inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
              <Check className="w-3 h-3" /> Verified
            </span>
          </div>
        </div>

        {/* 1. Page Range Section */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-bold text-slate-800">
              Page Range
            </label>
            <span className="text-xs font-semibold text-slate-500">
              {pageRangeType === 'all'
                ? `All ${totalDocPages} pages`
                : customRangeValidation.isValid
                ? `${selectedPageCount} page${selectedPageCount === 1 ? '' : 's'} selected`
                : 'Custom range'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <button
              id="page-range-all"
              type="button"
              disabled={isCreatingOrder}
              onClick={() => {
                setPageRangeType('all');
                setErrorMessage(null);
              }}
              className={`p-3.5 rounded-2xl border-2 text-sm font-bold transition-all flex flex-col items-center justify-center gap-1 ${
                pageRangeType === 'all'
                  ? 'border-brand-500 bg-brand-50/70 text-brand-700 shadow-sm'
                  : 'border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <span>All Pages</span>
              <span className="text-[11px] font-normal text-slate-500">
                1 to {totalDocPages}
              </span>
            </button>

            <button
              id="page-range-custom"
              type="button"
              disabled={isCreatingOrder}
              onClick={() => setPageRangeType('custom')}
              className={`p-3.5 rounded-2xl border-2 text-sm font-bold transition-all flex flex-col items-center justify-center gap-1 ${
                pageRangeType === 'custom'
                  ? 'border-brand-500 bg-brand-50/70 text-brand-700 shadow-sm'
                  : 'border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <span>Custom Range</span>
              <span className="text-[11px] font-normal text-slate-500">
                Select specific pages
              </span>
            </button>
          </div>

          {/* Custom Range Input Area */}
          {pageRangeType === 'custom' && (
            <div className="mt-3 p-3.5 rounded-2xl bg-slate-50 border border-slate-200 animate-fade-in">
              <label htmlFor="custom-range-input" className="block text-xs font-semibold text-slate-700 mb-1.5">
                Enter page numbers or ranges:
              </label>
              <input
                id="custom-range-input"
                type="text"
                value={customRange}
                disabled={isCreatingOrder}
                onChange={(e) => {
                  setCustomRange(e.target.value);
                  setErrorMessage(null);
                }}
                placeholder="Examples: 1-3 or 1,3,5 or 1-3,5,8-10"
                className={`w-full px-4 py-2.5 rounded-xl border text-sm font-medium focus:outline-none transition-all ${
                  customRange && !customRangeValidation.isValid
                    ? 'border-rose-300 bg-rose-50/30 focus:border-rose-500 focus:ring-2 focus:ring-rose-200 text-rose-900'
                    : 'border-slate-300 bg-white focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-slate-900'
                }`}
              />

              {/* Validation helper or error message */}
              {customRange && !customRangeValidation.isValid ? (
                <p className="mt-2 text-xs font-medium text-rose-600 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  <span>{customRangeValidation.error}</span>
                </p>
              ) : customRange && customRangeValidation.isValid ? (
                <div className="mt-2 flex items-center justify-between text-xs text-emerald-700 bg-emerald-50 px-3 py-1.5 rounded-lg border border-emerald-200">
                  <span className="font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Valid range: {selectedPageCount} {selectedPageCount === 1 ? 'page' : 'pages'}
                  </span>
                  <span className="text-[11px] text-emerald-600 truncate max-w-[200px]">
                    Pages: {customRangeValidation.pages.join(', ')}
                  </span>
                </div>
              ) : (
                <p className="mt-1.5 text-[11px] text-slate-500">
                  Separate page numbers with commas or use hyphens for ranges (e.g. 1-3, 5, 8-10). Total pages: {totalDocPages}.
                </p>
              )}
            </div>
          )}
        </div>

        {/* 2. Copies Section */}
        <div className="mb-6">
          <label className="block text-sm font-bold text-slate-800 mb-2">
            Number of Copies
          </label>

          <div className="flex items-center justify-between p-3.5 rounded-2xl border border-slate-200/90 bg-slate-50/50">
            <div>
              <p className="text-sm font-semibold text-slate-800">Print Sets</p>
              <p className="text-xs text-slate-500">Between 1 and 100 copies</p>
            </div>

            <div className="flex items-center gap-3">
              <button
                id="decrease-copies"
                type="button"
                onClick={() => handleCopiesChange(-1)}
                disabled={copies <= 1 || isCreatingOrder}
                className="w-10 h-10 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-slate-700 hover:bg-slate-100 active:scale-95 disabled:opacity-40 disabled:hover:bg-white disabled:cursor-not-allowed transition-all shadow-xs"
                title="Decrease copies"
              >
                <Minus className="w-4 h-4" />
              </button>

              <input
                id="copies-input"
                type="number"
                min="1"
                max="100"
                value={copies}
                disabled={isCreatingOrder}
                onChange={handleCopiesInput}
                className="w-14 text-center font-extrabold text-lg bg-white border border-slate-200 rounded-xl py-1.5 text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />

              <button
                id="increase-copies"
                type="button"
                onClick={() => handleCopiesChange(1)}
                disabled={copies >= 100 || isCreatingOrder}
                className="w-10 h-10 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-slate-700 hover:bg-slate-100 active:scale-95 disabled:opacity-40 disabled:hover:bg-white disabled:cursor-not-allowed transition-all shadow-xs"
                title="Increase copies"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* 3. Color Mode Section */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-bold text-slate-800">
              Color Mode
            </label>
            <span className="text-xs font-semibold text-slate-500">
              Authoritative pricing applied
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <button
              id="color-mode-bw"
              type="button"
              disabled={isCreatingOrder}
              onClick={() => setColorMode('bw')}
              className={`p-4 rounded-2xl border-2 text-left transition-all relative ${
                colorMode === 'bw'
                  ? 'border-brand-500 bg-brand-50/70 shadow-sm ring-2 ring-brand-100'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm text-slate-900">Black & White</span>
                <span className="text-xs font-bold text-slate-700 bg-slate-200/80 px-2 py-0.5 rounded-full">
                  ₹3 / page
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">Standard grayscale monochrome print</p>
              {colorMode === 'bw' && (
                <div className="absolute top-2.5 right-2.5 w-2 h-2 rounded-full bg-brand-600" />
              )}
            </button>

            <button
              id="color-mode-color"
              type="button"
              disabled={isCreatingOrder}
              onClick={() => setColorMode('color')}
              className={`p-4 rounded-2xl border-2 text-left transition-all relative ${
                colorMode === 'color'
                  ? 'border-brand-500 bg-brand-50/70 shadow-sm ring-2 ring-brand-100'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm text-slate-900">Color</span>
                <span className="text-xs font-bold text-brand-700 bg-brand-100 px-2 py-0.5 rounded-full">
                  ₹10 / page
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">Vibrant high-resolution color print</p>
              {colorMode === 'color' && (
                <div className="absolute top-2.5 right-2.5 w-2 h-2 rounded-full bg-brand-600" />
              )}
            </button>
          </div>
        </div>

        {/* 4. Duplex (Sides) Section */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-bold text-slate-800">
              Print Sides (Duplex)
            </label>
            <span className="text-xs font-semibold text-slate-500">
              {duplex ? 'Paper saving enabled' : 'Single sided'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <button
              id="duplex-single"
              type="button"
              disabled={isCreatingOrder}
              onClick={() => setDuplex(false)}
              className={`p-4 rounded-2xl border-2 text-left transition-all ${
                !duplex
                  ? 'border-brand-500 bg-brand-50/70 shadow-sm ring-2 ring-brand-100'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <p className="font-bold text-sm text-slate-900">Single Side</p>
              <p className="text-xs text-slate-500 mt-1">1 page per physical sheet</p>
            </button>

            <button
              id="duplex-double"
              type="button"
              disabled={isCreatingOrder}
              onClick={() => setDuplex(true)}
              className={`p-4 rounded-2xl border-2 text-left transition-all ${
                duplex
                  ? 'border-brand-500 bg-brand-50/70 shadow-sm ring-2 ring-brand-100'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm text-slate-900">Double Side</span>
                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded">
                  Duplex
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">2 pages per physical sheet</p>
            </button>
          </div>
        </div>

        {/* 5. Live Price & Configuration Summary */}
        <div className="p-5 rounded-2xl bg-slate-900 text-white mb-5 shadow-lg shadow-slate-900/10">
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Printer className="w-5 h-5 text-brand-400" />
              <span className="font-bold text-sm sm:text-base">Print Job Summary</span>
            </div>
            <span className="text-xs font-semibold text-slate-400 bg-slate-800 px-2.5 py-0.5 rounded-full">
              Live Preview
            </span>
          </div>

          <div className="space-y-2 text-xs sm:text-sm">
            <div className="flex justify-between text-slate-300">
              <span>Selected Pages:</span>
              <span className="font-semibold text-white">
                {selectedPageCount} page{selectedPageCount === 1 ? '' : 's'}
                {pageRangeType === 'custom' && customRange.trim() ? ` (${customRange.trim()})` : ' (All)'}
              </span>
            </div>

            <div className="flex justify-between text-slate-300">
              <span>Copies:</span>
              <span className="font-semibold text-white">{copies}</span>
            </div>

            <div className="flex justify-between text-slate-300">
              <span>Color Mode:</span>
              <span className="font-semibold text-white">
                {colorMode === 'bw' ? 'Black & White (₹3/page)' : 'Color (₹10/page)'}
              </span>
            </div>

            <div className="flex justify-between text-slate-300">
              <span>Sides:</span>
              <span className="font-semibold text-white">
                {duplex ? 'Double Sided' : 'Single Sided'}
              </span>
            </div>

            <div className="flex justify-between text-slate-300">
              <span>Physical Sheets:</span>
              <span className="font-semibold text-white">
                ~{estimatedSheets} sheet{estimatedSheets === 1 ? '' : 's'}
              </span>
            </div>

            <div className="pt-3 mt-3 border-t border-slate-800 flex items-center justify-between">
              <div>
                <span className="font-bold text-sm block">Estimated Total</span>
                <span className="text-[11px] text-slate-400 font-medium">
                  {selectedPageCount} pages × {copies} {copies === 1 ? 'copy' : 'copies'} × ₹{pricePerPage}
                </span>
              </div>

              <div className="text-right">
                <span className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                  ₹{estimatedTotalPrice.toFixed(2)}
                </span>
                <span className="block text-[10px] text-slate-400 font-medium">INR</span>
              </div>
            </div>
          </div>
        </div>

        {/* Backend Authoritative Notice */}
        <div className="mb-5 p-3 rounded-2xl bg-slate-50 border border-slate-200 flex items-start gap-2.5 text-xs text-slate-600">
          <Info className="w-4 h-4 text-brand-600 mt-0.5 shrink-0" />
          <p className="leading-relaxed">
            <strong className="text-slate-800 font-semibold">Authoritative Pricing:</strong> The estimated amount shown above is calculated for your convenience. The final order total and sheet counts are authoritatively computed and validated by the SmartPrint backend upon clicking Create Print Order.
          </p>
        </div>

        {/* Error Notification Alert */}
        {errorMessage && (
          <div className="mb-5 p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs sm:text-sm font-medium flex items-start gap-3 animate-fade-in">
            <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-bold text-rose-900">Order Creation Error</p>
              <p className="mt-0.5 leading-relaxed">{errorMessage}</p>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-3">
          <button
            id="reset-button"
            type="button"
            onClick={onReset}
            disabled={isCreatingOrder}
            className="w-full sm:w-auto px-5 py-3.5 rounded-2xl font-semibold text-sm text-slate-700 bg-slate-100 hover:bg-slate-200 active:scale-[0.99] transition-all disabled:opacity-50 flex items-center justify-center gap-1.5 cursor-pointer"
          >
            <RotateCcw className="w-4 h-4 text-slate-500" />
            <span>Upload New</span>
          </button>

          <button
            id="create-order-button"
            type="button"
            onClick={handleCreateOrder}
            disabled={isCreatingOrder || (pageRangeType === 'custom' && !customRangeValidation.isValid)}
            className="flex-1 inline-flex items-center justify-center gap-2 py-4 px-6 rounded-2xl font-bold text-base text-white bg-brand-600 hover:bg-brand-700 active:scale-[0.99] transition-all shadow-md shadow-brand-600/25 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
          >
            {isCreatingOrder ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                <span>Creating Order...</span>
              </>
            ) : (
              <>
                <Printer className="w-5 h-5" />
                <span>Create Print Order</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
