import React from 'react';
import { Printer, HelpCircle } from 'lucide-react';

export default function Header({ onOpenHowItWorks }) {
  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200/80 transition-all shadow-sm">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        {/* Brand Logo & Name */}
        <div className="flex items-center gap-2.5">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-600 to-brand-700 flex items-center justify-center text-white shadow-md shadow-brand-500/20">
            <Printer className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-extrabold text-xl tracking-tight text-slate-900">
                Smart<span className="text-brand-600">Print</span>
              </span>
              <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-brand-50 text-brand-700 border border-brand-200">
                Stage 2
              </span>
            </div>
            <p className="text-[11px] text-slate-500 font-medium hidden sm:block">
              Print Smart. Print Simple.
            </p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex items-center gap-1 sm:gap-2">
          <a
            href="#home"
            className="px-3 py-1.5 text-sm font-medium text-slate-700 hover:text-brand-600 rounded-lg hover:bg-slate-100 transition-colors"
          >
            Home
          </a>
          <button
            type="button"
            onClick={onOpenHowItWorks}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-brand-600 hover:text-brand-700 bg-brand-50/80 hover:bg-brand-100/70 rounded-lg border border-brand-200/60 transition-colors"
          >
            <HelpCircle className="w-4 h-4" />
            <span>How It Works</span>
          </button>
        </nav>
      </div>
    </header>
  );
}
