import React, { useState, useEffect, useMemo } from 'react';
import {
  ShieldCheck,
  ArrowLeft,
  Copy,
  Check,
  FileText,
  Layers,
  Printer,
  Loader2,
  AlertCircle,
  Lock,
  Clock,
  Sparkles,
  QrCode,
  Smartphone,
} from 'lucide-react';
import { getPayUCheckoutUrl } from '../services/api';

/**
 * Extract list of document names from an order object safely.
 */
function getDocumentNames(order) {
  if (Array.isArray(order?.documents) && order.documents.length > 0) {
    return order.documents.map(
      (doc, i) => doc?.filename || `Document ${i + 1}`
    );
  }
  if (Array.isArray(order?.files) && order.files.length > 0) {
    return order.files.map(
      (f, i) => f?.filename || f?.original_filename || `Document ${i + 1}`
    );
  }
  if (order?.filename) {
    return [order.filename];
  }
  return ['Uploaded Document'];
}

export default function PayUPaymentScreen({
  order,
  onBackToOptions,
  onCancel,
}) {
  const [isRedirecting, setIsRedirecting] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, []);

  // Check URL query parameters for return errors
  useEffect(() => {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const urlError = urlParams.get('error');
      const urlStatus = (urlParams.get('payment_status') || '').toLowerCase();
      if (urlError) {
        setErrorMessage(decodeURIComponent(urlError));
      } else if (urlStatus === 'failure' || urlStatus === 'failed') {
        setErrorMessage('Payment was declined or cancelled. You can retry with PayU below.');
      } else if (urlStatus === 'cancelled') {
        setErrorMessage('Payment was cancelled at PayU gateway. You can re-attempt payment below.');
      }
    } catch (e) {}
  }, []);

  const orderId = order?.id || order?.order_id || order?.order_number;
  const orderNumberDisplay =
    order?.order_number || order?.order_id || (order?.id ? `SP-${order.id.slice(0, 8)}` : 'SP-000000');
  const currencySymbol = order?.currency === 'INR' ? '₹' : order?.currency || '₹';
  const totalAmountFormatted = Number(order?.total_amount || 0).toFixed(2);
  const pageCount = order?.selected_page_count || order?.page_count || 1;
  const copies = Number(order?.copies || 1);
  const isColor = String(order?.color_mode || '').toLowerCase().includes('color');
  const isDuplex = Boolean(order?.duplex);
  const documentNames = useMemo(() => getDocumentNames(order), [order]);

  const handleCopyOrderId = () => {
    if (orderNumberDisplay) {
      navigator.clipboard.writeText(orderNumberDisplay);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handlePayViaPayU = () => {
    if (!orderId || isRedirecting) return;
    setErrorMessage(null);
    setIsRedirecting(true);

    try {
      const checkoutUrl = getPayUCheckoutUrl(orderId);
      // Redirect customer to PayU Hosted Checkout
      window.location.href = checkoutUrl;
    } catch (err) {
      console.error('Failed to initiate PayU checkout:', err);
      setErrorMessage(
        err?.message || 'Could not initiate PayU checkout session. Please try again.'
      );
      setIsRedirecting(false);
    }
  };

  return (
    <div className="w-full max-w-xl mx-auto animate-fade-in pb-10">
      {/* Top Navigation & Step Indicator */}
      <div className="mb-4 flex items-center justify-between">
        <button
          type="button"
          onClick={onBackToOptions}
          disabled={isRedirecting}
          className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-semibold text-slate-600 hover:text-brand-600 transition-colors disabled:opacity-50 p-1 cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Adjust Options</span>
        </button>

        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-bold border border-emerald-200 shadow-sm">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
          <span>Step 3 of 4 • PayU UPI Payment</span>
        </span>
      </div>

      {/* Main Payment Card */}
      <div className="bg-white rounded-3xl border border-slate-200/90 p-5 sm:p-7 shadow-card">
        {/* Header with SmartPrint Brand and Security Badge */}
        <div className="pb-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200 mb-1.5">
              <Lock className="w-3 h-3 text-emerald-600" />
              <span>SmartPrint • 256-Bit Encrypted UPI</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight">
              PAYMENT SUMMARY
            </h2>
            <p className="text-xs text-slate-500 font-medium">
              Review your print configuration and proceed to UPI payment.
            </p>
          </div>

          {/* Real-time Order Status Tag */}
          <div className="self-start sm:self-center inline-flex items-center gap-2 px-3 py-1.5 rounded-2xl bg-amber-50 border border-amber-200 text-amber-800 text-xs font-bold">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
            </span>
            <span>PAYMENT PENDING</span>
          </div>
        </div>

        {/* Highlight Gradient Card: Order ID & Amount */}
        <div className="my-5 p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900 to-emerald-950 text-white shadow-md shadow-slate-900/10 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Order Number:
              </span>
              <span className="font-mono font-black text-white text-sm sm:text-base tracking-wide">
                {orderNumberDisplay}
              </span>
              <button
                type="button"
                onClick={handleCopyOrderId}
                className="text-slate-400 hover:text-white transition-colors p-0.5"
                title="Copy Order Number"
              >
                {copied ? (
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
            <p className="text-xs text-slate-300 mt-1.5 flex flex-wrap items-center gap-1.5 sm:gap-2">
              <span>{pageCount} {pageCount === 1 ? 'page' : 'pages'}</span>
              <span>•</span>
              <span>{copies} {copies === 1 ? 'copy' : 'copies'}</span>
              <span>•</span>
              <span className="font-semibold text-emerald-300">{isColor ? 'Colour' : 'B&W'}</span>
              <span>•</span>
              <span>{isDuplex ? 'Duplex' : 'Single-side'}</span>
            </p>
          </div>

          <div className="text-right">
            <span className="text-xs font-bold text-slate-400 block uppercase tracking-wider">
              Total Amount
            </span>
            <span className="text-2xl sm:text-3xl font-black text-white tracking-tight">
              {currencySymbol}{totalAmountFormatted}
            </span>
            <span className="block text-[10px] font-bold text-emerald-400 uppercase tracking-wider">
              Exact Payable
            </span>
          </div>
        </div>

        {/* Uploaded Document Details */}
        <div className="my-5">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
            <FileText className="w-3.5 h-3.5 text-slate-500" />
            <span>Document Details</span>
          </h3>

          <div className="bg-slate-50 rounded-2xl border border-slate-200/90 divide-y divide-slate-200/70 overflow-hidden text-xs sm:text-sm">
            {documentNames.map((name, index) => (
              <div
                key={`${name}-${index}`}
                className="p-3.5 flex items-center justify-between gap-3"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="px-2 py-0.5 rounded-md bg-rose-100 text-rose-700 font-extrabold text-[10px] uppercase shrink-0">
                    PDF
                  </span>
                  <span className="font-semibold text-slate-800 truncate" title={name}>
                    {name}
                  </span>
                </div>
                <span className="text-slate-400 font-medium text-xs shrink-0">
                  Document {index + 1}
                </span>
              </div>
            ))}

            {/* Print Specification Breakdown */}
            <div className="p-3.5 grid grid-cols-2 sm:grid-cols-4 gap-3 bg-white/70 text-xs">
              <div>
                <span className="text-slate-400 block font-medium">Pages</span>
                <strong className="text-slate-900 font-bold">{pageCount}</strong>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Copies</span>
                <strong className="text-slate-900 font-bold">{copies}</strong>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Color Type</span>
                <strong className="text-slate-900 font-bold">
                  {isColor ? 'Colour' : 'Black & White'}
                </strong>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Print Sides</span>
                <strong className="text-slate-900 font-bold">
                  {isDuplex ? 'Double-sided' : 'Single-sided'}
                </strong>
              </div>
            </div>
          </div>
        </div>

        {/* UPI Payment via PayU Banner */}
        <div className="my-5 p-4 rounded-2xl bg-gradient-to-r from-emerald-50/80 via-teal-50/60 to-slate-50 border border-emerald-200/90 text-xs text-slate-700">
          <div className="flex items-center justify-between mb-2">
            <span className="font-extrabold text-slate-900 flex items-center gap-1.5 text-xs sm:text-sm">
              <Sparkles className="w-4 h-4 text-emerald-600" />
              <span>UPI Payment via PayU</span>
            </span>
            <span className="text-[10px] font-bold text-emerald-800 bg-emerald-100/90 px-2.5 py-0.5 rounded-full border border-emerald-200">
              UPI Only
            </span>
          </div>

          <p className="text-slate-600 leading-relaxed mb-3">
            SmartPrint accepts <strong>UPI payments only</strong>. Complete your payment using any supported UPI app, UPI ID, or dynamic QR code powered by PayU:
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 font-semibold text-[11px]">
            <div className="p-3 rounded-xl bg-white border border-slate-200 flex items-center gap-3 shadow-xs">
              <div className="w-8 h-8 rounded-lg bg-purple-50 flex items-center justify-center shrink-0">
                <Smartphone className="w-4 h-4 text-[#5f259f]" />
              </div>
              <div className="min-w-0">
                <span className="block font-bold text-slate-900">UPI Intent</span>
                <small className="text-[10px] text-slate-400 truncate block">GPay, PhonePe, Paytm, BHIM</small>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-white border border-slate-200 flex items-center gap-3 shadow-xs">
              <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center shrink-0">
                <Lock className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="min-w-0">
                <span className="block font-bold text-slate-900">UPI ID / Collect</span>
                <small className="text-[10px] text-slate-400 truncate block">VPA / Instant approval</small>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-white border border-slate-200 flex items-center gap-3 shadow-xs">
              <div className="w-8 h-8 rounded-lg bg-teal-50 flex items-center justify-center shrink-0">
                <QrCode className="w-4 h-4 text-teal-600" />
              </div>
              <div className="min-w-0">
                <span className="block font-bold text-slate-900">UPI QR Code</span>
                <small className="text-[10px] text-slate-400 truncate block">Scan & Pay via any app</small>
              </div>
            </div>
          </div>

          <div className="mt-3 pt-2.5 border-t border-emerald-100 flex items-center gap-2 text-[10px] text-slate-500">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-slate-400 shrink-0"></span>
            <span>Cards, Net Banking, Wallets, and EMI are disabled for this transaction. Only UPI is accepted.</span>
          </div>
        </div>

        {/* Error Message Notice if any */}
        {errorMessage && (
          <div className="mb-5 p-4 rounded-2xl bg-rose-50 border-2 border-rose-300 text-rose-900 text-xs sm:text-sm animate-fade-in">
            <div className="flex items-start gap-2.5">
              <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="font-bold">Payment Notice</p>
                <p className="mt-0.5 leading-relaxed">{errorMessage}</p>
              </div>
            </div>
          </div>
        )}

        {/* Tablet Kiosk Real-Time Sync Indicator */}
        <div className="mb-5 p-3 rounded-2xl bg-slate-50 border border-slate-200 text-xs text-slate-600 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-amber-600 shrink-0" />
            <span>
              Order saved on server • Tablet kiosk shows <strong>PAYMENT PENDING</strong>
            </span>
          </div>
          <span className="text-[10px] font-mono font-bold text-slate-500 bg-white px-2 py-0.5 rounded-md border border-slate-200">
            Kiosk Synced
          </span>
        </div>

        {/* Primary Action Buttons */}
        <div className="flex flex-col gap-3">
          {/* Prominent "Pay via UPI" Button */}
          <button
            id="pay-via-upi-button"
            type="button"
            onClick={handlePayViaPayU}
            disabled={isRedirecting}
            className="w-full inline-flex items-center justify-center gap-2.5 py-4 px-6 rounded-2xl font-black text-base text-white bg-emerald-600 hover:bg-emerald-700 active:scale-[0.99] transition-all shadow-md shadow-emerald-600/25 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
          >
            {isRedirecting ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                <span>Opening PayU UPI Checkout...</span>
              </>
            ) : (
              <>
                <Smartphone className="w-5 h-5" />
                <span>Pay via UPI ({currencySymbol}{totalAmountFormatted})</span>
              </>
            )}
          </button>

          {/* Secondary Options Button */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onBackToOptions}
              disabled={isRedirecting}
              className="flex-1 py-3 px-4 rounded-xl text-xs sm:text-sm font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 transition-colors cursor-pointer disabled:opacity-50"
            >
              Adjust Print Options
            </button>

            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                disabled={isRedirecting}
                className="py-3 px-4 rounded-xl text-xs sm:text-sm font-semibold text-slate-500 hover:text-slate-800 transition-colors cursor-pointer disabled:opacity-50"
              >
                Cancel Order
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

