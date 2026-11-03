import React, { useState, useEffect } from 'react';
import PrintMachineAnimation from './PrintMachineAnimation';
import {
  CheckCircle2,
  Copy,
  Check,
  FileText,
  Layers,
  Printer,
  CreditCard,
  RotateCcw,
  Sparkles,
  Clock,
  ShieldCheck,
  ArrowLeft,
} from 'lucide-react';

export default function OrderSummaryCard({
  order,
  onReset,
  onBackToOptions,
  onProceedToPayment,
}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, []);

  if (!order) return null;

  const handleCopyOrderId = () => {
    if (order.order_id) {
      navigator.clipboard.writeText(order.order_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const currencySymbol = order.currency === 'INR' ? '₹' : order.currency;
  const isPaid =
    order.status === 'CONFIRMED' ||
    order.status === 'PAID' ||
    order.status === 'PRINTING' ||
    order.status === 'COMPLETED' ||
    order.payment_status === 'PAID' ||
    order.payment_status === 'SUCCESS' ||
    Boolean(order.is_paid);

  return (
    <div className="w-full max-w-xl mx-auto animate-fade-in pb-8">
      {/* Top Status */}
      <div className="mb-4 flex items-center justify-between">
        <button
          type="button"
          onClick={onBackToOptions}
          className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-semibold text-slate-600 hover:text-brand-600 transition-colors p-1 cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Adjust Options</span>
        </button>

        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-bold border border-emerald-200 shadow-sm">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
          <span>{isPaid ? 'Step 4 of 4 • Payment Verified & Printing' : 'Order Created • Payment Pending'}</span>
        </span>
      </div>

      {/* Dynamic Print Machine Animation (Active on User's Web when Payment is Verified) */}
      {isPaid && (
        <PrintMachineAnimation
          order={order}
          onReset={onReset}
        />
      )}

      {/* Main Order Confirmation Card */}
      <div className="bg-white rounded-3xl border border-slate-200/90 p-6 sm:p-8 shadow-card">
        {/* Success Header */}
        <div className="text-center pb-6 border-b border-slate-100">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 mb-3.5 shadow-sm">
            <CheckCircle2 className="w-8 h-8" />
          </div>
          <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">
            {isPaid ? 'Payment Successful! Your Order Is Confirmed.' : 'Order Created Successfully!'}
          </h2>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 font-medium">
            {isPaid
              ? 'Your UPI payment was verified and your order is confirmed on the kiosk'
              : 'Your print order is verified and waiting for payment'}
          </p>

          {/* Order ID Pill with Copy */}
          <div className="mt-4 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-slate-50 border border-slate-200 text-xs font-mono text-slate-700 max-w-full">
            <span className="text-slate-400 font-sans font-medium">Order ID:</span>
            <span className="font-bold text-slate-900 truncate">{order.order_id}</span>
            <button
              id="copy-order-id-btn"
              type="button"
              onClick={handleCopyOrderId}
              className="p-1 text-slate-400 hover:text-brand-600 hover:bg-white rounded transition-colors cursor-pointer"
              title="Copy Order ID"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5 text-emerald-600" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
        </div>

        {/* Order Details Specification Grid */}
        <div className="my-6">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
            Authoritative Order Summary
          </h3>

          <div className="bg-slate-50/90 rounded-2xl border border-slate-200/80 divide-y divide-slate-200/70 text-xs sm:text-sm overflow-hidden">
            {/* Filename */}
            <div className="p-3.5 sm:p-4 flex items-center justify-between gap-3">
              <span className="text-slate-500 font-medium flex items-center gap-2">
                <FileText className="w-4 h-4 text-slate-400 shrink-0" />
                <span>Document:</span>
              </span>
              <span
                className="font-bold text-slate-900 text-right truncate max-w-[220px] sm:max-w-[280px]"
                title={order.filename || (order.documents && order.documents[0]?.filename)}
              >
                {order.filename || (order.documents && order.documents.map(d => d.filename).join(', ')) || 'Print Document'}
              </span>
            </div>

            {/* Selected Pages & Range */}
            <div className="p-3.5 sm:p-4 flex items-center justify-between gap-3">
              <span className="text-slate-500 font-medium flex items-center gap-2">
                <Layers className="w-4 h-4 text-brand-500 shrink-0" />
                <span>Selected Pages:</span>
              </span>
              <span className="font-semibold text-slate-800 text-right">
                <span className="font-extrabold text-brand-700 bg-brand-50 border border-brand-200 px-2 py-0.5 rounded-full text-xs mr-1.5">
                  {order.selected_page_count} {order.selected_page_count === 1 ? 'page' : 'pages'}
                </span>
                <span className="text-slate-500 text-xs">
                  ({order.page_range === 'all' ? 'All Pages' : `Range: ${order.page_range}`})
                </span>
              </span>
            </div>

            {/* Copies */}
            <div className="p-3.5 sm:p-4 flex items-center justify-between gap-3">
              <span className="text-slate-500 font-medium flex items-center gap-2">
                <Printer className="w-4 h-4 text-slate-400 shrink-0" />
                <span>Copies:</span>
              </span>
              <span className="font-bold text-slate-900">
                {order.copies} {order.copies === 1 ? 'copy' : 'copies'}
              </span>
            </div>

            {/* Color Mode */}
            <div className="p-3.5 sm:p-4 flex items-center justify-between gap-3">
              <span className="text-slate-500 font-medium">Color Mode:</span>
              <span
                className={`font-bold px-2.5 py-0.5 rounded-full text-xs ${
                  order.color_mode === 'color'
                    ? 'bg-amber-50 text-amber-800 border border-amber-200'
                    : 'bg-slate-200/80 text-slate-800'
                }`}
              >
                {order.color_mode === 'color' ? 'Color' : 'Black & White'}
              </span>
            </div>

            {/* Print Sides / Duplex */}
            <div className="p-3.5 sm:p-4 flex items-center justify-between gap-3">
              <span className="text-slate-500 font-medium">Print Sides:</span>
              <span className="font-semibold text-slate-800">
                {order.duplex ? 'Double Side (Duplex)' : 'Single Side'}
              </span>
            </div>

            {/* Physical Sheet Count */}
            <div className="p-3.5 sm:p-4 flex items-center justify-between gap-3">
              <span className="text-slate-500 font-medium">Physical Sheets:</span>
              <span className="font-extrabold text-slate-900 bg-white border border-slate-200 px-2.5 py-0.5 rounded-md">
                {order.physical_sheet_count} {order.physical_sheet_count === 1 ? 'sheet' : 'sheets'}
              </span>
            </div>

            {/* Price per Page */}
            <div className="p-3.5 sm:p-4 flex items-center justify-between gap-3">
              <span className="text-slate-500 font-medium">Price per Page:</span>
              <span className="font-semibold text-slate-700">
                {currencySymbol}{Number(order.price_per_page || 0).toFixed(2)}
              </span>
            </div>

            {/* Order Status */}
            <div className="p-3.5 sm:p-4 flex items-center justify-between gap-3">
              <span className="text-slate-500 font-medium flex items-center gap-1.5">
                <Clock className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>Order Status:</span>
              </span>
              <span
                className={`inline-flex items-center gap-1.5 font-bold px-3 py-0.5 rounded-full text-xs ${
                  isPaid
                    ? 'text-emerald-700 bg-emerald-50 border border-emerald-200'
                    : 'text-amber-800 bg-amber-50 border border-amber-200'
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    isPaid ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse'
                  }`}
                />
                {order.status}
              </span>
            </div>
          </div>
        </div>

        {/* Total Price Card */}
        <div className="p-5 rounded-2xl bg-slate-900 text-white flex items-center justify-between mb-6 shadow-md shadow-slate-900/10">
          <div>
            <span className="text-xs font-medium text-slate-400 block uppercase tracking-wider">
              {isPaid ? 'Total Amount Paid' : 'Total Amount'}
            </span>
            <span className="text-xs text-slate-300">
              {order.selected_page_count} pages × {order.copies} {order.copies === 1 ? 'copy' : 'copies'} × {currencySymbol}{order.price_per_page}
            </span>
          </div>
          <div className="text-right">
            <span className="text-2xl sm:text-3xl font-black text-white tracking-tight">
              {currencySymbol}{Number(order.total_amount || 0).toFixed(2)}
            </span>
            <span className="block text-[11px] font-semibold text-brand-400">
              {order.currency}
            </span>
          </div>
        </div>

        {/* Payment Confirmation Receipt or Pending Box */}
        {isPaid ? (
          <div className="mb-6 p-4 rounded-2xl bg-emerald-50/80 border border-emerald-200 text-xs text-emerald-900 shadow-xs">
            <div className="flex items-center gap-2 font-bold text-emerald-800 text-sm mb-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>UPI Payment Verified Successfully</span>
            </div>
            <p className="text-emerald-700 leading-relaxed font-medium">
              Payment of <strong>{currencySymbol}{Number(order.total_amount || 0).toFixed(2)}</strong> has been verified.
              {order.payment_reference && (
                <span className="block mt-1 font-mono text-[11px] text-emerald-800">
                  Ref: {order.payment_reference}
                </span>
              )}
              Your document is queued for printing. Please collect your printout at the kiosk tray.
            </p>
          </div>
        ) : (
          <div className="mb-6 p-4 rounded-2xl bg-amber-50/80 border border-amber-200 text-xs text-amber-900 flex items-center justify-between gap-3">
            <div>
              <p className="font-bold text-amber-900">Payment Pending</p>
              <p className="text-amber-700 text-[11px] mt-0.5">
                Complete payment via dynamic UPI to send this order to the printer.
              </p>
            </div>
            {onProceedToPayment && (
              <button
                type="button"
                onClick={onProceedToPayment}
                className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs shadow-xs cursor-pointer shrink-0"
              >
                Pay Now
              </button>
            )}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-3">
          {!isPaid && onProceedToPayment ? (
            <button
              id="proceed-to-payment-btn"
              type="button"
              onClick={onProceedToPayment}
              className="flex-1 inline-flex items-center justify-center gap-2 py-4 px-6 rounded-2xl font-bold text-base text-white bg-emerald-600 hover:bg-emerald-700 active:scale-[0.99] transition-all shadow-md shadow-emerald-600/25 cursor-pointer"
            >
              <CreditCard className="w-5 h-5" />
              <span>Proceed to UPI Payment ({currencySymbol}{Number(order.total_amount || 0).toFixed(2)})</span>
            </button>
          ) : (
            <button
              id="start-new-order-btn"
              type="button"
              onClick={onReset}
              className="flex-1 inline-flex items-center justify-center gap-2 py-4 px-6 rounded-2xl font-bold text-base text-white bg-brand-600 hover:bg-brand-700 active:scale-[0.99] transition-all shadow-md shadow-brand-600/25 cursor-pointer"
            >
              <RotateCcw className="w-4 h-4" />
              <span>Start New Print Order</span>
            </button>
          )}

          <button
            id="adjust-options-btn"
            type="button"
            onClick={onBackToOptions}
            className="w-full sm:w-auto px-5 py-3.5 rounded-2xl font-semibold text-sm text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 transition-colors cursor-pointer"
          >
            Adjust Options
          </button>
        </div>
      </div>
    </div>
  );
}
