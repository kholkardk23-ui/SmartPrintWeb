import React from 'react';
import { X, Sparkles, Sliders, Check } from 'lucide-react';

export default function Stage2NoticeModal({ isOpen, onClose }) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
      <div
        className="relative w-full max-w-md bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden"
        role="dialog"
        aria-modal="true"
      >
        {/* Modal Header */}
        <div className="bg-brand-50/80 px-6 py-4 border-b border-brand-100 flex items-center justify-between">
          <div className="flex items-center gap-2 text-brand-800 font-bold text-base">
            <Sparkles className="w-5 h-5 text-brand-600" />
            <span>Next Stage Preview</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-brand-100/50 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 text-center">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-brand-100/60 flex items-center justify-center text-brand-600 mb-4">
            <Sliders className="w-7 h-7" />
          </div>

          <h3 className="text-xl font-bold text-slate-900 mb-2">
            Printing options are coming in the next stage.
          </h3>

          <p className="text-sm text-slate-600 mb-5 leading-relaxed font-medium">
            Stage 1 has verified your document upload and page count. Printing preferences and payment will follow in the next release.
          </p>

          <div className="bg-slate-50 rounded-2xl p-4 text-left border border-slate-200/70 mb-6 space-y-2 text-xs sm:text-sm text-slate-600">
            <p className="font-bold text-slate-800 mb-1">Upcoming in Stage 2 & 3:</p>
            <div className="flex items-center gap-2">
              <Check className="w-4 h-4 text-brand-600 shrink-0" />
              <span>Color vs. Black & White selection</span>
            </div>
            <div className="flex items-center gap-2">
              <Check className="w-4 h-4 text-brand-600 shrink-0" />
              <span>Copies, duplex (double-sided), & page range</span>
            </div>
            <div className="flex items-center gap-2">
              <Check className="w-4 h-4 text-brand-600 shrink-0" />
              <span>Instant price calculation & UPI Payment</span>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="w-full py-3.5 px-4 rounded-xl font-bold text-sm text-white bg-brand-600 hover:bg-brand-700 transition-colors cursor-pointer"
          >
            Got It
          </button>
        </div>
      </div>
    </div>
  );
}
