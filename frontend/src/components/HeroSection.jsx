import React from 'react';
import { ShieldCheck, Zap, FileText } from 'lucide-react';

export default function HeroSection() {
  return (
    <section className="text-center pt-4 pb-2 sm:pt-8 sm:pb-4">
      {/* Brand Kiosk Badge */}
      <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-50 border border-brand-200/80 text-brand-700 text-xs font-semibold mb-3 shadow-sm">
        <Zap className="w-3.5 h-3.5 text-brand-600 fill-brand-600" />
        <span>SmartPrint Self-Service Station</span>
      </div>

      {/* Main Heading */}
      <h1 className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-slate-900 tracking-tight max-w-2xl mx-auto leading-tight sm:leading-snug">
        Upload Your <span className="text-brand-600">Document</span>
      </h1>

      {/* Tagline / Description */}
      <p className="mt-2.5 text-base sm:text-lg text-slate-600 max-w-xl mx-auto leading-relaxed">
        Upload your PDF to get started.
      </p>

      {/* Spec Pills */}
      <div className="mt-4 flex flex-wrap items-center justify-center gap-2 sm:gap-4 text-xs font-medium text-slate-500">
        <span className="flex items-center gap-1 bg-white px-3 py-1 rounded-full border border-slate-200/80 shadow-sm">
          <FileText className="w-3.5 h-3.5 text-brand-600" /> PDF Format Only
        </span>
        <span className="flex items-center gap-1 bg-white px-3 py-1 rounded-full border border-slate-200/80 shadow-sm">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> Max 50 MB per file
        </span>
      </div>
    </section>
  );
}
