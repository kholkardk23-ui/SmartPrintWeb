import React from 'react';
import { X, QrCode, UploadCloud, CreditCard, Printer } from 'lucide-react';

const steps = [
  {
    icon: QrCode,
    title: '1. Scan QR Code',
    desc: 'Scan the QR code displayed on the SmartPrint machine screen using your mobile phone.',
  },
  {
    icon: UploadCloud,
    title: '2. Upload Document',
    desc: 'Upload your PDF document (up to 50 MB). Our server inspects and counts pages automatically.',
  },
  {
    icon: CreditCard,
    title: '3. Choose & Pay',
    desc: 'Select color, duplex, or copies, and make a quick payment using any UPI app (GPay, PhonePe, Paytm).',
  },
  {
    icon: Printer,
    title: '4. Collect Printout',
    desc: 'The printer starts immediately. Collect your fresh documents right from the dispenser tray.',
  },
];

export default function HowItWorksModal({ isOpen, onClose }) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
      <div
        className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden"
        role="dialog"
        aria-modal="true"
      >
        <div className="bg-brand-50/80 px-6 py-4 border-b border-brand-100 flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">
            How SmartPrint Works
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-brand-100/50 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
          {steps.map((step, idx) => {
            const Icon = step.icon;
            return (
              <div key={idx} className="flex items-start gap-3.5 p-3 rounded-xl bg-slate-50 border border-slate-200/60">
                <div className="w-10 h-10 rounded-lg bg-brand-100 flex items-center justify-center text-brand-600 shrink-0">
                  <Icon className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="font-bold text-sm text-slate-900">{step.title}</h4>
                  <p className="text-xs sm:text-sm text-slate-600 mt-0.5 leading-relaxed">{step.desc}</p>
                </div>
              </div>
            );
          })}
        </div>

        <div className="p-4 bg-slate-50 border-t border-slate-200 text-center">
          <button
            type="button"
            onClick={onClose}
            className="w-full py-2.5 px-4 rounded-xl font-semibold text-sm text-white bg-brand-600 hover:bg-brand-700 transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
