import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Printer,
  CheckCircle2,
  Sparkles,
  RotateCcw,
  FileText,
  Layers,
  ArrowRight,
  ShieldCheck,
  Check,
} from 'lucide-react';
import { updateOrderStatus } from '../services/api';

export default function PrintMachineAnimation({ order, onReset, onComplete }) {
  // Calculate total physical sheets to simulate
  const totalSheets = useMemo(() => {
    if (!order) return 1;
    if (order.physical_sheet_count) return order.physical_sheet_count;
    const pages = order.selected_page_count || 1;
    const duplexFactor = order.duplex ? 2 : 1;
    const copies = order.copies || 1;
    return Math.max(1, Math.ceil(pages / duplexFactor) * copies);
  }, [order]);

  const maxAnimSheets = Math.min(totalSheets, 3);

  const [currentSheet, setCurrentSheet] = useState(1);
  const [phase, setPhase] = useState('warming'); // 'warming' | 'printing' | 'completed'
  const [progress, setProgress] = useState(0);
  const [sheetCycle, setSheetCycle] = useState(0); // triggers re-animation of the sheet
  const animTimerRef = useRef(null);

  const filename = useMemo(() => {
    if (!order) return 'Document.pdf';
    if (order.filename) return order.filename;
    if (order.documents && order.documents.length > 0) {
      return order.documents[0].filename || 'Document.pdf';
    }
    return 'Document.pdf';
  }, [order]);

  const isColor = order?.color_mode === 'color';
  const orderNumber = order?.order_number || order?.order_id || 'SP-ORDER';

  // Run the smooth printing sequence
  const startSequence = () => {
    if (animTimerRef.current) clearInterval(animTimerRef.current);
    setPhase('warming');
    setProgress(5);
    setCurrentSheet(1);
    setSheetCycle((c) => c + 1);

    // Warm up for 900ms then start printing
    const tWarm = setTimeout(() => {
      setPhase('printing');
      let currentProgress = 10;
      let sheetNum = 1;

      animTimerRef.current = setInterval(() => {
        currentProgress += 4;
        setProgress((prev) => Math.min(currentProgress, 96));

        // Advance sheet if multi-page
        if (currentProgress >= 45 && sheetNum < maxAnimSheets && currentProgress < 85) {
          sheetNum += 1;
          setCurrentSheet(sheetNum);
          setSheetCycle((c) => c + 1);
        }

        // Finish printing sequence
        if (currentProgress >= 100) {
          clearInterval(animTimerRef.current);
          setProgress(100);
          setPhase('completed');
          const ordId = order?.order_id || order?.id || order?.order_number;
          if (ordId) {
            updateOrderStatus(ordId, 'COMPLETED').catch(() => {});
          }
          if (onComplete) onComplete();
        }
      }, 160);
    }, 900);

    return () => {
      clearTimeout(tWarm);
      if (animTimerRef.current) clearInterval(animTimerRef.current);
    };
  };

  useEffect(() => {
    const cleanup = startSequence();
    return () => {
      if (cleanup) cleanup();
      if (animTimerRef.current) clearInterval(animTimerRef.current);
    };
  }, []);

  const handleReplay = () => {
    startSequence();
  };

  const handleSkip = () => {
    if (animTimerRef.current) clearInterval(animTimerRef.current);
    setProgress(100);
    setCurrentSheet(totalSheets);
    setPhase('completed');
    const ordId = order?.order_id || order?.id || order?.order_number;
    if (ordId) {
      updateOrderStatus(ordId, 'COMPLETED').catch(() => {});
    }
    if (onComplete) onComplete();
  };

  return (
    <div className="w-full bg-white rounded-3xl border border-slate-200/90 shadow-xl overflow-hidden mb-6 transition-all">
      {/* Top Banner: Stage Status & Replay */}
      <div className="px-5 sm:px-7 py-4 bg-gradient-to-r from-slate-50 via-white to-slate-50 border-b border-slate-100 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-brand-50 border border-brand-200 text-brand-600 flex items-center justify-center shadow-xs">
            <Printer className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs sm:text-sm font-extrabold text-slate-900 tracking-tight">
                SmartPrint Kiosk Printer
              </span>
              <span
                className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border transition-colors ${
                  phase === 'completed'
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : 'bg-brand-50 text-brand-700 border-brand-200 animate-pulse'
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    phase === 'completed' ? 'bg-emerald-500' : 'bg-brand-500 animate-ping'
                  }`}
                />
                {phase === 'completed' ? 'PRINT COMPLETE' : 'PRINTING IN PROGRESS'}
              </span>
            </div>
            <p className="text-[11px] text-slate-500 font-mono">
              Order: {orderNumber} • {totalSheets} {totalSheets === 1 ? 'sheet' : 'sheets'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {phase === 'completed' ? (
            <button
              type="button"
              onClick={handleReplay}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200/80 text-slate-700 text-xs font-bold transition-all border border-slate-200 cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5 text-brand-600" />
              <span>Watch Again</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSkip}
              className="px-2.5 py-1 rounded-lg text-[11px] font-semibold text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
            >
              Skip
            </button>
          )}
        </div>
      </div>

      {/* Main Visual Arena: Tactile Modern Printer & Paper Movement */}
      <div className="p-6 sm:p-8 bg-gradient-to-b from-slate-50/60 via-slate-100/40 to-white flex flex-col items-center justify-center relative select-none">
        {/* Subtle decorative background circles */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 bg-brand-50/60 rounded-full blur-3xl pointer-events-none" />

        {/* ========================================================= */}
        {/* THE PRINTER MACHINE ASSEMBLY */}
        {/* ========================================================= */}
        <div className="w-full max-w-[360px] sm:max-w-[400px] flex flex-col items-center relative">
          
          {/* 1. TOP PAPER FEED HOPPER (Blank Paper Stack entering from top) */}
          <div className="relative w-44 sm:w-52 h-14 flex items-end justify-center z-0">
            {/* Rear Tray Wall */}
            <div className="absolute bottom-0 w-48 sm:w-56 h-12 bg-slate-200/90 rounded-t-xl border border-slate-300/80 shadow-xs" />

            {/* Paper Stack angled inside hopper */}
            <div className="relative w-36 sm:w-44 h-12 bg-white rounded-t-lg shadow-sm border border-slate-200 flex flex-col items-center justify-start overflow-hidden">
              <div className="w-full h-1 bg-slate-100 border-b border-slate-200/60" />
              
              {/* Paper feed-in animation: top sheet pulled down into slot */}
              {phase === 'printing' && (
                <div
                  key={`feed-${sheetCycle}`}
                  className="w-full h-full bg-gradient-to-b from-white via-white to-slate-100 border-t border-brand-300 animate-paper-feed"
                />
              )}
            </div>

            {/* Hopper feeder guide rollers */}
            <div className="absolute -bottom-1 w-40 sm:w-48 h-2 bg-slate-300 rounded-full border border-slate-400/40 z-10" />
          </div>

          {/* 2. MAIN PRINTER CHASSIS (Sleek Apple/HP-style White & Slate Body) */}
          <div className="w-full bg-gradient-to-b from-white via-slate-50 to-slate-100 rounded-3xl p-5 border border-slate-200 shadow-xl relative z-10">
            {/* Top Gloss Highlight Edge */}
            <div className="absolute top-0 inset-x-6 h-[1.5px] bg-gradient-to-r from-transparent via-white to-transparent" />

            {/* Printer Top Face: Control Bar & Status Display */}
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-200/70">
              {/* Brand Badge & Hardware Lights */}
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-brand-600 text-white flex items-center justify-center font-black text-xs shadow-xs">
                  SP
                </div>
                <div>
                  <span className="block text-[11px] font-black text-slate-800 tracking-tight uppercase">
                    SmartPrint Pro
                  </span>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    {/* Status LED */}
                    <span
                      className={`w-2 h-2 rounded-full transition-all duration-300 ${
                        phase === 'completed'
                          ? 'bg-emerald-500 shadow-[0_0_8px_#10b981]'
                          : phase === 'printing'
                          ? 'bg-brand-500 animate-pulse shadow-[0_0_8px_#3b82f6]'
                          : 'bg-amber-400'
                      }`}
                    />
                    <span className="text-[9px] font-bold text-slate-400 font-mono">
                      {phase === 'completed' ? 'READY' : 'PRINTING'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Digital OLED/LCD Pill */}
              <div className="px-3 py-1.5 rounded-xl bg-slate-900 text-white border border-slate-800 shadow-inner flex items-center gap-2 font-mono text-[10px]">
                <span className="text-cyan-400 font-bold">
                  {phase === 'warming' && 'INITIALIZING'}
                  {phase === 'printing' && `PAGE ${currentSheet}/${totalSheets}`}
                  {phase === 'completed' && 'JOB FINISHED'}
                </span>
                <span className="text-slate-600">|</span>
                <span className="text-emerald-400 font-bold">{progress}%</span>
              </div>
            </div>

            {/* 3. PRINTER OUTPUT CAVITY (Dark Slot where paper emerges) */}
            <div className="relative bg-slate-900 rounded-2xl p-3 border border-slate-800/90 shadow-inner min-h-[170px] sm:min-h-[190px] flex flex-col items-center justify-start overflow-hidden">
              
              {/* Internal Mechanical Roller Cylinders */}
              <div className="w-full flex items-center justify-around py-1 border-b border-slate-800 mb-2">
                {[1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className="w-12 h-2.5 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center overflow-hidden"
                  >
                    <div
                      className={`w-full h-[2px] bg-slate-500 ${
                        phase === 'printing' ? 'animate-roller-spin' : ''
                      }`}
                    />
                  </div>
                ))}
              </div>

              {/* Horizontal Cyan Laser Scan Line (fuses toner as paper slides out) */}
              {phase === 'printing' && (
                <div className="absolute top-11 w-32 h-[3px] bg-gradient-to-r from-transparent via-cyan-400 to-transparent blur-[1px] animate-laser-sweep z-30 pointer-events-none" />
              )}

              {/* 4. THE PRINTED PDF DOCUMENT (Gliding out with real content!) */}
              <div
                key={`sheet-${sheetCycle}`}
                className={`w-[88%] sm:w-[84%] bg-white rounded-xl p-3.5 sm:p-4 text-slate-800 border border-slate-200/90 shadow-2xl relative transition-all duration-700 ${
                  phase === 'printing'
                    ? 'animate-paper-eject'
                    : phase === 'completed'
                    ? 'translate-y-0 opacity-100 ring-2 ring-emerald-500/40 shadow-emerald-500/10'
                    : 'translate-y-[-50px] opacity-25'
                }`}
              >
                {/* Paper Header */}
                <div className="flex items-center justify-between pb-2 border-b border-slate-100 mb-2.5">
                  <div className="flex items-center gap-1.5 overflow-hidden">
                    <div className="w-4 h-4 rounded bg-rose-500 text-white flex items-center justify-center text-[8px] font-black shrink-0">
                      PDF
                    </div>
                    <span className="text-[11px] font-bold text-slate-900 truncate max-w-[130px] sm:max-w-[170px]">
                      {filename}
                    </span>
                  </div>
                  <span className="text-[9px] font-mono font-bold text-slate-400">
                    Sheet {currentSheet} of {totalSheets}
                  </span>
                </div>

                {/* Printed Document Mock Content */}
                <div className="space-y-1.5">
                  {/* Document Title skeleton */}
                  <div className="h-2.5 bg-slate-800 rounded-sm w-3/4" />

                  {/* Body text lines */}
                  <div className="h-1.5 bg-slate-200 rounded-sm w-full" />
                  <div className="h-1.5 bg-slate-200 rounded-sm w-5/6" />

                  {/* Colored Graph / B&W Chart depending on Color Mode */}
                  <div
                    className={`h-7 rounded-lg p-1.5 flex items-end gap-1.5 my-2 border ${
                      isColor
                        ? 'bg-brand-50/70 border-brand-200/60'
                        : 'bg-slate-100/90 border-slate-200'
                    }`}
                  >
                    <div
                      className={`w-3.5 rounded-t transition-all duration-300 ${
                        isColor ? 'bg-brand-500' : 'bg-slate-600'
                      }`}
                      style={{ height: `${Math.min(progress, 80)}%` }}
                    />
                    <div
                      className={`w-3.5 rounded-t transition-all duration-300 ${
                        isColor ? 'bg-cyan-500' : 'bg-slate-500'
                      }`}
                      style={{ height: `${Math.min(progress, 60)}%` }}
                    />
                    <div
                      className={`w-3.5 rounded-t transition-all duration-300 ${
                        isColor ? 'bg-emerald-500' : 'bg-slate-400'
                      }`}
                      style={{ height: `${Math.min(progress, 95)}%` }}
                    />
                    <div
                      className={`w-3.5 rounded-t transition-all duration-300 ${
                        isColor ? 'bg-amber-500' : 'bg-slate-700'
                      }`}
                      style={{ height: `${Math.min(progress, 45)}%` }}
                    />
                    <span className="text-[8px] font-mono text-slate-400 ml-auto self-center font-bold">
                      {isColor ? 'RGB COLOR' : 'MONOCHROME'}
                    </span>
                  </div>

                  {/* Text lines */}
                  <div className="h-1.5 bg-slate-200 rounded-sm w-full" />
                  <div className="h-1.5 bg-slate-300 rounded-sm w-2/3" />
                </div>

                {/* Footer Security Authentication Strip */}
                <div className="mt-2.5 pt-1.5 border-t border-slate-100 flex items-center justify-between text-[8px] text-slate-400 font-mono">
                  <span>SMARTPRINT AUTHENTICATED</span>
                  <span className="text-emerald-600 font-bold flex items-center gap-0.5">
                    <Check className="w-2.5 h-2.5" /> VERIFIED
                  </span>
                </div>
              </div>
            </div>

            {/* 5. PRINTER OUTPUT CATCH TRAY (Lower Lip) */}
            <div className="mt-2 w-full flex items-center justify-center">
              <div className="w-56 sm:w-64 h-3.5 bg-gradient-to-b from-slate-200 to-slate-300 rounded-b-2xl border-b border-slate-300 shadow-md flex items-center justify-center">
                <div className="w-20 h-1 bg-slate-400/60 rounded-full" />
              </div>
            </div>
          </div>
        </div>

        {/* ========================================================= */}
        {/* LIVE PRINT PROGRESS BAR & STATUS */}
        {/* ========================================================= */}
        <div className="w-full max-w-md mt-6 flex flex-col items-center text-center">
          {/* Animated Status Pill */}
          <div className="mb-2">
            {phase === 'completed' ? (
              <span className="inline-flex items-center gap-1.5 px-3.5 py-1 rounded-full bg-emerald-100/80 text-emerald-800 font-bold text-xs border border-emerald-300 shadow-xs">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>Document Printed Successfully!</span>
              </span>
            ) : phase === 'warming' ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-50 text-brand-700 font-bold text-xs border border-brand-200">
                <Printer className="w-4 h-4 text-brand-600 animate-pulse" />
                <span>Warming up printer & spooling PDF...</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-50 text-brand-700 font-bold text-xs border border-brand-200">
                <Printer className="w-4 h-4 text-brand-600 animate-pulse" />
                <span>
                  Printing Sheet {currentSheet} of {totalSheets} ({progress}%)
                </span>
              </span>
            )}
          </div>

          {/* Progress Track */}
          <div className="w-full bg-slate-200/90 rounded-full h-2.5 overflow-hidden border border-slate-300/60 my-1.5 shadow-inner">
            <div
              className={`h-full transition-all duration-200 rounded-full ${
                phase === 'completed'
                  ? 'bg-gradient-to-r from-emerald-500 to-teal-500'
                  : 'bg-gradient-to-r from-brand-600 via-brand-500 to-cyan-500'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>

          {/* Page breakdown */}
          <div className="w-full flex items-center justify-between text-[11px] font-mono text-slate-500 px-1 font-semibold">
            <span>
              {phase === 'completed'
                ? `All ${totalSheets} ${totalSheets === 1 ? 'sheet' : 'sheets'} ready`
                : `Sheet ${currentSheet} of ${totalSheets}`}
            </span>
            <span>{progress}% complete</span>
          </div>
        </div>
      </div>

      {/* ========================================================= */}
      {/* COMPLETION CELEBRATION & PICKUP BANNER */}
      {/* ========================================================= */}
      {phase === 'completed' && (
        <div className="px-5 sm:px-7 py-4 bg-gradient-to-r from-emerald-50 via-teal-50/70 to-emerald-50 border-t border-emerald-200 flex flex-col sm:flex-row items-center justify-between gap-3 animate-fade-in">
          <div className="flex items-center gap-3 text-center sm:text-left">
            <div className="w-10 h-10 rounded-2xl bg-emerald-500 text-white flex items-center justify-center shadow-md shadow-emerald-500/25 shrink-0 mx-auto sm:mx-0">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs sm:text-sm font-extrabold text-emerald-950">
                Your printout is ready at Tray 1!
              </p>
              <p className="text-[11px] text-emerald-700 font-medium">
                Please collect your document from the SmartPrint kiosk collection tray.
              </p>
            </div>
          </div>

          {onReset && (
            <button
              type="button"
              onClick={onReset}
              className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition-all shadow-md shadow-emerald-600/20 shrink-0 cursor-pointer"
            >
              Print Another File
            </button>
          )}
        </div>
      )}
    </div>
  );
}
