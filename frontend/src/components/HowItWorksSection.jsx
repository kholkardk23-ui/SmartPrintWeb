import React from 'react';
import { UploadCloud, Sliders, CreditCard, Printer, CheckCircle2 } from 'lucide-react';

const steps = [
  {
    number: '1',
    icon: UploadCloud,
    title: 'Upload PDF',
    desc: 'Select or drag & drop your document. Our server calculates page counts instantly.',
    isReady: true,
  },
  {
    number: '2',
    icon: Sliders,
    title: 'Choose printing options',
    desc: 'Pick color or black & white, page ranges, copies, and duplex settings.',
    isCurrent: true,
  },
  {
    number: '3',
    icon: CreditCard,
    title: 'Pay with UPI',
    desc: 'Pay directly on your phone using any UPI app (GPay, PhonePe, Paytm).',
    comingSoon: true,
  },
  {
    number: '4',
    icon: Printer,
    title: 'Collect your print',
    desc: 'The kiosk releases your printed document immediately.',
    comingSoon: true,
  },
];

export default function HowItWorksSection() {
  return (
    <section className="w-full max-w-xl mx-auto mt-12 mb-6">
      <div className="text-center mb-6">
        <h3 className="text-lg sm:text-xl font-bold text-slate-900">
          How it works
        </h3>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          Simple self-service printing in 4 easy steps
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {steps.map((step) => {
          const Icon = step.icon;
          return (
            <div
              key={step.number}
              className={`p-4 rounded-2xl border transition-all ${
                step.isCurrent
                  ? 'bg-brand-50/60 border-brand-200 shadow-sm'
                  : 'bg-white border-slate-200/80'
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div
                  className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                    step.isCurrent
                      ? 'bg-brand-600 text-white shadow-sm shadow-brand-500/30'
                      : step.isReady
                      ? 'bg-emerald-100 text-emerald-700'
                      : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>

                {step.isCurrent ? (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold text-brand-700 bg-brand-100/80 px-2 py-0.5 rounded-full uppercase tracking-wider">
                    <CheckCircle2 className="w-3 h-3" /> Step 2 Active
                  </span>
                ) : step.isReady ? (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                    <CheckCircle2 className="w-3 h-3" /> Ready
                  </span>
                ) : (
                  <span className="inline-flex items-center text-[10px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                    Coming Soon
                  </span>
                )}
              </div>

              <h4 className="font-bold text-sm text-slate-800">
                {step.number}. {step.title}
              </h4>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                {step.desc}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
