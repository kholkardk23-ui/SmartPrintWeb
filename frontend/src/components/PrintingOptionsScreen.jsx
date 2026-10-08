import React, { useState, useMemo } from 'react';
import {
  Sliders,
  ArrowLeft,
  Plus,
  Minus,
  CheckCircle2,
  FileText,
  Printer,
  AlertCircle,
  Loader2,
  Info,
  RotateCcw,
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
 * Client-side page range validation.
 *
 * Example:
 * 1-3,5
 *
 * Returns:
 * {
 *   isValid: true,
 *   count: 4,
 *   pages: [1,2,3,5]
 * }
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

  // Only numbers, spaces, commas and hyphens
  if (!/^[0-9\s,-]+$/.test(cleaned)) {
    return {
      isValid: false,
      error:
        'Invalid characters. Use numbers, commas, spaces, and hyphens only.',
      count: 0,
      pages: [],
    };
  }

  if (
    cleaned.startsWith(',') ||
    cleaned.endsWith(',') ||
    /,\s*,/.test(cleaned)
  ) {
    return {
      isValid: false,
      error: 'Invalid format. Commas must separate page numbers or ranges.',
      count: 0,
      pages: [],
    };
  }

  const parts = cleaned.split(',');
  const selectedSet = new Set();

  for (const rawPart of parts) {
    const part = rawPart.trim();

    if (!part) {
      return {
        isValid: false,
        error: 'Empty section in page range.',
        count: 0,
        pages: [],
      };
    }

    // Range such as 1-5
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
          error: `Page range '${part}' exceeds this PDF's ${totalPages} pages.`,
          count: 0,
          pages: [],
        };
      }

      for (let page = start; page <= end; page++) {
        selectedSet.add(page);
      }
    } else {
      // Single page such as 5
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
          error: `Page ${pageNum} exceeds this PDF's ${totalPages} pages.`,
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
  /**
   * Always work with a safe array.
   */
  const safeFiles = Array.isArray(files) ? files : [];

  /**
   * Configuration
   */
  const [copies, setCopies] = useState(1);
  const [colorMode, setColorMode] = useState('bw');
  const [duplex, setDuplex] = useState(false);
  const [pageRangeType, setPageRangeType] = useState('all');
  const [customRange, setCustomRange] = useState('');

  /**
   * UI state
   */
  const [isCreatingOrder, setIsCreatingOrder] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  /**
   * Price per page
   *
   * B&W  = ₹3
   * Color = ₹10
   */
  const pricePerPage = colorMode === 'bw' ? 3 : 10;

  /**
   * TOTAL PAGES FROM ALL UPLOADED PDF FILES
   *
   * Example:
   *
   * PDF 1 = 12 pages
   * PDF 2 = 8 pages
   *
   * totalDocPages = 20
   */
  const totalDocPages = useMemo(() => {
    return safeFiles.reduce((total, file) => {
      return total + Number(file?.page_count || 0);
    }, 0);
  }, [safeFiles]);

  /**
   * Validate custom page range against EVERY PDF.
   *
   * Example:
   *
   * PDF 1 = 12 pages
   * PDF 2 = 8 pages
   *
   * Custom range = 1-3
   *
   * Result:
   * PDF 1 -> 3 pages
   * PDF 2 -> 3 pages
   * Total  -> 6 pages
   */
  const customRangeValidation = useMemo(() => {
    if (pageRangeType !== 'custom') {
      return {
        isValid: true,
        error: null,
        count: totalDocPages,
        pages: [],
      };
    }

    if (!customRange.trim()) {
      return {
        isValid: false,
        error: 'Please enter the page range you want to print.',
        count: 0,
        pages: [],
      };
    }

    let totalSelected = 0;

    for (let index = 0; index < safeFiles.length; index++) {
      const file = safeFiles[index];
      const pageCount = Number(file?.page_count || 0);

      const validation = parseCustomRange(customRange, pageCount);

      if (!validation.isValid) {
        const filename =
          file?.original_filename ||
          file?.filename ||
          `Document ${index + 1}`;

        return {
          isValid: false,
          error: `${filename}: ${validation.error}`,
          count: 0,
          pages: [],
        };
      }

      totalSelected += validation.count;
    }

    return {
      isValid: totalSelected > 0,
      error: totalSelected > 0 ? null : 'No pages selected.',
      count: totalSelected,
      pages: [],
    };
  }, [pageRangeType, customRange, safeFiles, totalDocPages]);

  /**
   * TOTAL SELECTED PAGES FROM ALL PDFs
   */
  const selectedPageCount = useMemo(() => {
    if (!safeFiles.length) return 0;

    if (pageRangeType === 'all') {
      return totalDocPages;
    }

    return customRangeValidation.isValid
      ? customRangeValidation.count
      : 0;
  }, [
    safeFiles.length,
    pageRangeType,
    totalDocPages,
    customRangeValidation,
  ]);

  /**
   * Physical sheets
   *
   * Single side:
   * 20 pages = 20 sheets
   *
   * Duplex:
   * 20 pages = 10 sheets
   */
  const estimatedSheets = useMemo(() => {
    if (!selectedPageCount) return 0;

    const pagesPerSheet = duplex ? 2 : 1;

    return Math.ceil(selectedPageCount / pagesPerSheet) * copies;
  }, [selectedPageCount, duplex, copies]);

  /**
   * TOTAL PRICE FOR ALL PDF FILES
   *
   * Example:
   *
   * 20 pages × 1 copy × ₹3
   * = ₹60
   */
  const estimatedTotalPrice = useMemo(() => {
    return selectedPageCount * copies * pricePerPage;
  }, [selectedPageCount, copies, pricePerPage]);

  /**
   * Change number of copies
   */
  const handleCopiesChange = (delta) => {
    setCopies((previous) => {
      const next = previous + delta;

      return Math.min(100, Math.max(1, next));
    });
  };

  /**
   * Direct copies input
   */
  const handleCopiesInput = (event) => {
    const value = parseInt(event.target.value, 10);

    if (Number.isNaN(value)) {
      setCopies(1);
      return;
    }

    setCopies(Math.min(100, Math.max(1, value)));
  };

  /**
   * CREATE ONE ORDER CONTAINING ALL PDFs
   */
  const handleCreateOrder = async () => {
    setErrorMessage(null);

    /**
     * Make sure at least one PDF exists.
     */
    if (!safeFiles.length) {
      setErrorMessage(
        'No PDF documents found. Please upload at least one PDF file.'
      );
      return;
    }

    /**
     * Make sure every PDF has a valid file ID.
     */
    const invalidFile = safeFiles.find(
      (file) => !file || !file.file_id
    );

    if (invalidFile) {
      setErrorMessage(
        'One or more uploaded PDFs are invalid. Please upload the files again.'
      );
      return;
    }

    /**
     * Custom range validation
     */
    if (pageRangeType === 'custom') {
      if (!customRange.trim()) {
        setErrorMessage(
          'Please enter the page range you want to print (e.g. 1-3, 5).'
        );
        return;
      }

      if (!customRangeValidation.isValid) {
        setErrorMessage(
          customRangeValidation.error || 'Invalid page range.'
        );
        return;
      }
    }

    /**
     * Make sure pages exist.
     */
    if (selectedPageCount <= 0) {
      setErrorMessage('No printable pages were selected.');
      return;
    }

    /**
     * IMPORTANT:
     *
     * Send ALL PDF file IDs in ONE order.
     */
    const payload = {
      file_ids: safeFiles.map((file) => file.file_id),

      copies: Number(copies),

      color_mode: colorMode,

      duplex: Boolean(duplex),

      page_range:
        pageRangeType === 'all'
          ? 'all'
          : customRange.trim(),
    };

    setIsCreatingOrder(true);

    try {
      /**
       * Backend remains authoritative for final pricing.
       */
      const order = await createOrder(payload);

      if (onOrderCreated) {
        onOrderCreated(order);
      }
    } catch (error) {
      console.error('Create order error:', error);

      setErrorMessage(
        error?.message ||
          error?.response?.data?.detail ||
          'Failed to create print order. Please check your options and try again.'
      );
    } finally {
      setIsCreatingOrder(false);
    }
  };

  /**
   * No PDFs uploaded
   */
  if (!safeFiles.length) {
    return (
      <div className="w-full max-w-xl mx-auto animate-fade-in">
        <div className="bg-white rounded-3xl border border-slate-200 p-8 text-center shadow-card">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600 mb-4">
            <AlertCircle className="w-7 h-7" />
          </div>

          <h3 className="text-xl font-bold text-slate-900 mb-2">
            No Documents Available
          </h3>

          <p className="text-slate-600 font-medium text-sm mb-6">
            Please upload one or more PDF documents before selecting
            printing options.
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
              Configure printing for all uploaded PDFs
            </p>
          </div>
        </div>

        {/* ALL DOCUMENTS SUMMARY */}
        <div className="mb-6 p-4 rounded-2xl bg-brand-50/60 border border-brand-100">
          <div className="flex items-center justify-between gap-3">

            <div className="flex items-center gap-3 min-w-0">
              <div className="w-11 h-11 rounded-xl bg-white border border-brand-200 flex items-center justify-center text-brand-600 shadow-sm shrink-0">
                <FileText className="w-5 h-5" />
              </div>

              <div className="min-w-0">
                <p className="text-xs font-bold text-brand-800 uppercase tracking-wide">
                  Documents Ready to Print
                </p>

                <p className="text-sm font-bold text-slate-800 mt-1">
                  {safeFiles.length}{' '}
                  {safeFiles.length === 1 ? 'PDF' : 'PDFs'} selected
                </p>

                <p className="text-xs text-slate-500 mt-0.5">
                  All uploaded documents will be printed together
                </p>
              </div>
            </div>

            <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-white border border-brand-200 text-xs font-bold text-brand-700 whitespace-nowrap">
              {totalDocPages} pages
            </span>

          </div>
        </div>

        {/* FILE LIST */}
        <div className="mb-6 rounded-2xl border border-slate-200 bg-slate-50/60 overflow-hidden">

          <div className="px-4 py-3 border-b border-slate-200 bg-white">
            <p className="text-xs font-bold text-slate-700 uppercase tracking-wide">
              Uploaded Documents
            </p>
          </div>

          <div className="max-h-44 overflow-y-auto divide-y divide-slate-200">
            {safeFiles.map((file, index) => (
              <div
                key={file.file_id || index}
                className="px-4 py-3 flex items-center gap-3"
              >
                <div className="w-9 h-9 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-brand-600 shrink-0">
                  <FileText className="w-4 h-4" />
                </div>

                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-800 truncate">
                    {file.original_filename ||
                      file.filename ||
                      `Document ${index + 1}`}
                  </p>

                  <p className="text-xs text-slate-500">
                    {Number(file.page_count || 0)} pages
                    {file.size
                      ? ` • ${formatFileSize(file.size)}`
                      : ''}
                  </p>
                </div>

                <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
              </div>
            ))}
          </div>
        </div>

        {/* 1. PAGE RANGE */}
        <div className="mb-6">

          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-bold text-slate-800">
              Page Range
            </label>

            <span className="text-xs font-semibold text-slate-500">
              {pageRangeType === 'all'
                ? `All ${totalDocPages} pages`
                : customRangeValidation.isValid
                ? `${selectedPageCount} pages selected`
                : 'Custom range'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">

            {/* ALL PAGES */}
            <button
              id="page-range-all"
              type="button"
              disabled={isCreatingOrder}
              onClick={() => {
                setPageRangeType('all');
                setCustomRange('');
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
                All {totalDocPages} pages
              </span>
            </button>

            {/* CUSTOM RANGE */}
            <button
              id="page-range-custom"
              type="button"
              disabled={isCreatingOrder}
              onClick={() => {
                setPageRangeType('custom');
                setErrorMessage(null);
              }}
              className={`p-3.5 rounded-2xl border-2 text-sm font-bold transition-all flex flex-col items-center justify-center gap-1 ${
                pageRangeType === 'custom'
                  ? 'border-brand-500 bg-brand-50/70 text-brand-700 shadow-sm'
                  : 'border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <span>Custom Range</span>

              <span className="text-[11px] font-normal text-slate-500">
                Same range for every PDF
              </span>
            </button>

          </div>

          {/* CUSTOM RANGE INPUT */}
          {pageRangeType === 'custom' && (
            <div className="mt-3 p-3.5 rounded-2xl bg-slate-50 border border-slate-200 animate-fade-in">

              <label
                htmlFor="custom-range-input"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                Enter page numbers or ranges:
              </label>

              <input
                id="custom-range-input"
                type="text"
                value={customRange}
                disabled={isCreatingOrder}
                onChange={(event) => {
                  setCustomRange(event.target.value);
                  setErrorMessage(null);
                }}
                placeholder="Examples: 1-3 or 1,3,5 or 1-3,5"
                className={`w-full px-4 py-2.5 rounded-xl border text-sm font-medium focus:outline-none transition-all ${
                  customRange &&
                  !customRangeValidation.isValid
                    ? 'border-rose-300 bg-rose-50/30 focus:border-rose-500 focus:ring-2 focus:ring-rose-200 text-rose-900'
                    : 'border-slate-300 bg-white focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-slate-900'
                }`}
              />

              {customRange &&
              !customRangeValidation.isValid ? (
                <p className="mt-2 text-xs font-medium text-rose-600 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />

                  <span>{customRangeValidation.error}</span>
                </p>
              ) : customRange &&
                customRangeValidation.isValid ? (
                <div className="mt-2 flex items-center justify-between text-xs text-emerald-700 bg-emerald-50 px-3 py-1.5 rounded-lg border border-emerald-200">
                  <span className="font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />

                    Valid range for all PDFs:
                    {' '}
                    {selectedPageCount} pages
                  </span>
                </div>
              ) : (
                <p className="mt-1.5 text-[11px] text-slate-500">
                  This range will be applied to every uploaded PDF.
                  Total pages across all PDFs: {totalDocPages}.
                </p>
              )}

            </div>
          )}

        </div>

        {/* 2. COPIES */}
        <div className="mb-6">

          <label className="block text-sm font-bold text-slate-800 mb-2">
            Number of Copies
          </label>

          <div className="flex items-center justify-between p-3.5 rounded-2xl border border-slate-200/90 bg-slate-50/50">

            <div>
              <p className="text-sm font-semibold text-slate-800">
                Print Sets
              </p>

              <p className="text-xs text-slate-500">
                Between 1 and 100 copies
              </p>
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

        {/* 3. COLOR MODE */}
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

            {/* BLACK & WHITE */}
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
                <span className="font-bold text-sm text-slate-900">
                  Black & White
                </span>

                <span className="text-xs font-bold text-slate-700 bg-slate-200/80 px-2 py-0.5 rounded-full">
                  ₹3 / page
                </span>
              </div>

              <p className="text-xs text-slate-500 mt-1">
                Standard grayscale monochrome print
              </p>

              {colorMode === 'bw' && (
                <div className="absolute top-2.5 right-2.5 w-2 h-2 rounded-full bg-brand-600" />
              )}
            </button>

            {/* COLOR */}
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
                <span className="font-bold text-sm text-slate-900">
                  Color
                </span>

                <span className="text-xs font-bold text-brand-700 bg-brand-100 px-2 py-0.5 rounded-full">
                  ₹10 / page
                </span>
              </div>

              <p className="text-xs text-slate-500 mt-1">
                Vibrant high-resolution color print
              </p>

              {colorMode === 'color' && (
                <div className="absolute top-2.5 right-2.5 w-2 h-2 rounded-full bg-brand-600" />
              )}
            </button>

          </div>
        </div>

        {/* 4. DUPLEX */}
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

            {/* SINGLE SIDE */}
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
              <p className="font-bold text-sm text-slate-900">
                Single Side
              </p>

              <p className="text-xs text-slate-500 mt-1">
                1 page per physical sheet
              </p>
            </button>

            {/* DOUBLE SIDE */}
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
                <span className="font-bold text-sm text-slate-900">
                  Double Side
                </span>

                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded">
                  Duplex
                </span>
              </div>

              <p className="text-xs text-slate-500 mt-1">
                2 pages per physical sheet
              </p>
            </button>

          </div>
        </div>

        {/* 5. PRINT JOB SUMMARY */}
        <div className="p-5 rounded-2xl bg-slate-900 text-white mb-5 shadow-lg shadow-slate-900/10">

          <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">

            <div className="flex items-center gap-2">
              <Printer className="w-5 h-5 text-brand-400" />

              <span className="font-bold text-sm sm:text-base">
                Print Job Summary
              </span>
            </div>

            <span className="text-xs font-semibold text-slate-400 bg-slate-800 px-2.5 py-0.5 rounded-full">
              Live Preview
            </span>

          </div>

          <div className="space-y-2 text-xs sm:text-sm">

            {/* DOCUMENTS */}
            <div className="flex justify-between text-slate-300">
              <span>Documents:</span>

              <span className="font-semibold text-white">
                {safeFiles.length} PDF
                {safeFiles.length === 1 ? '' : 's'}
              </span>
            </div>

            {/* TOTAL PAGES */}
            <div className="flex justify-between text-slate-300">
              <span>Selected Pages:</span>

              <span className="font-semibold text-white text-right">
                {selectedPageCount} page
                {selectedPageCount === 1 ? '' : 's'}
                {pageRangeType === 'custom'
                  ? ` (${customRange.trim()})`
                  : ' (All PDFs)'}
              </span>
            </div>

            {/* COPIES */}
            <div className="flex justify-between text-slate-300">
              <span>Copies:</span>

              <span className="font-semibold text-white">
                {copies}
              </span>
            </div>

            {/* COLOR */}
            <div className="flex justify-between text-slate-300">
              <span>Color Mode:</span>

              <span className="font-semibold text-white">
                {colorMode === 'bw'
                  ? 'Black & White (₹3/page)'
                  : 'Color (₹10/page)'}
              </span>
            </div>

            {/* SIDES */}
            <div className="flex justify-between text-slate-300">
              <span>Sides:</span>

              <span className="font-semibold text-white">
                {duplex ? 'Double Sided' : 'Single Sided'}
              </span>
            </div>

            {/* SHEETS */}
            <div className="flex justify-between text-slate-300">
              <span>Physical Sheets:</span>

              <span className="font-semibold text-white">
                ~{estimatedSheets} sheet
                {estimatedSheets === 1 ? '' : 's'}
              </span>
            </div>

            {/* TOTAL */}
            <div className="pt-3 mt-3 border-t border-slate-800 flex items-center justify-between">

              <div>
                <span className="font-bold text-sm block">
                  Estimated Total
                </span>

                <span className="text-[11px] text-slate-400 font-medium">
                  {selectedPageCount} pages × {copies}{' '}
                  {copies === 1 ? 'copy' : 'copies'} × ₹
                  {pricePerPage}
                </span>
              </div>

              <div className="text-right">

                <span className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                  ₹{estimatedTotalPrice.toFixed(2)}
                </span>

                <span className="block text-[10px] text-slate-400 font-medium">
                  INR
                </span>

              </div>
            </div>

          </div>
        </div>

        {/* BACKEND AUTHORITATIVE NOTICE */}
        <div className="mb-5 p-3 rounded-2xl bg-slate-50 border border-slate-200 flex items-start gap-2.5 text-xs text-slate-600">

          <Info className="w-4 h-4 text-brand-600 mt-0.5 shrink-0" />

          <p className="leading-relaxed">
            <strong className="text-slate-800 font-semibold">
              Authoritative Pricing:
            </strong>{' '}
            The estimated amount shown above is calculated for your
            convenience. The final order total and sheet counts are
            authoritatively computed and validated by the SmartPrint
            backend when you create the print order.
          </p>

        </div>

        {/* ERROR */}
        {errorMessage && (
          <div className="mb-5 p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs sm:text-sm font-medium flex items-start gap-3 animate-fade-in">

            <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />

            <div className="flex-1">
              <p className="font-bold text-rose-900">
                Order Creation Error
              </p>

              <p className="mt-0.5 leading-relaxed">
                {errorMessage}
              </p>
            </div>

          </div>
        )}

        {/* ACTION BUTTONS */}
        <div className="flex flex-col sm:flex-row gap-3">

          {/* UPLOAD NEW */}
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

          {/* CREATE ORDER */}
          <button
            id="create-order-button"
            type="button"
            onClick={handleCreateOrder}
            disabled={
              isCreatingOrder ||
              selectedPageCount <= 0 ||
              (pageRangeType === 'custom' &&
                !customRangeValidation.isValid)
            }
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