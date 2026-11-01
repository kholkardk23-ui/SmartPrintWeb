import React, { useState, useEffect, useRef, useMemo } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  Check,
  ShieldCheck,
  Clock,
  Sparkles,
  Loader2,
  AlertCircle,
  ExternalLink,
  RefreshCw,
  QrCode,
  Smartphone,
  Receipt,
  FileText,
  Printer,
  Layers,
} from 'lucide-react';
import { startPayment, verifyPayment, getPaymentStatus } from '../services/api';

const PAYMENT_TIMEOUT_SECONDS = 600; // 10 minutes

export default function UPIPaymentScreen({
  order,
  onPaymentSuccess,
  onBackToOptions,
  onCancel,
  isTablet = false,
}) {
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, []);

  const [paymentData, setPaymentData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [referenceId, setReferenceId] = useState('');
  const [errorMessage, setErrorMessage] = useState(null);
  const [copiedField, setCopiedField] = useState(null);
  const [timeLeft, setTimeLeft] = useState(PAYMENT_TIMEOUT_SECONDS);
  const [isPaid, setIsPaid] = useState(false);

  const orderIdentifier = order?.order_id || order?.id || order?.order_number;
  const pollingTimerRef = useRef(null);

  // Initialize Dynamic UPI payment
  const initializePayment = async () => {
    if (!orderIdentifier) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      const data = await startPayment(orderIdentifier);
      setPaymentData(data);
      if (data.payment_status === 'PAID' || data.is_paid || data.status === 'PRINTING' || data.status === 'COMPLETED') {
        setIsPaid(true);
        if (onPaymentSuccess) {
          onPaymentSuccess({ ...order, ...data, status: 'PRINTING' });
        }
      }
    } catch (err) {
      console.error('Failed to start payment:', err);
      // Fallback client-side dynamic UPI generation if offline or demo
      const upiId = 'smartprint@upi';
      const upiName = 'SmartPrint Kiosk';
      const amount = Number(order?.total_amount || 0).toFixed(2);
      const orderNum = order?.order_number || order?.order_id || orderIdentifier || 'SP-ORDER';
      const fallbackUri = `upi://pay?pa=${upiId}&pn=${encodeURIComponent(
        upiName
      )}&am=${amount}&cu=INR&tn=${encodeURIComponent(
        `SmartPrint ${orderNum}`
      )}&tr=${orderNum}`;

      setPaymentData({
        order_id: orderIdentifier,
        order_number: orderNum,
        amount: Number(order?.total_amount || 0),
        currency: order?.currency || 'INR',
        payment_status: 'PAYMENT_PENDING',
        upi_id: upiId,
        upi_name: upiName,
        upi_uri: fallbackUri,
        qr_data: fallbackUri,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    initializePayment();
  }, [orderIdentifier]);

  // Session countdown timer
  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Real-time polling to detect payment verification
  useEffect(() => {
    if (isPaid || !orderIdentifier) return;

    pollingTimerRef.current = setInterval(async () => {
      try {
        const statusRes = await getPaymentStatus(orderIdentifier);
        if (
          statusRes &&
          (statusRes.is_paid ||
            statusRes.status === 'PAID' ||
            statusRes.status === 'PRINTING' ||
            statusRes.status === 'COMPLETED' ||
            statusRes.payment_status === 'PAID')
        ) {
          clearInterval(pollingTimerRef.current);
          setIsPaid(true);
          setTimeout(() => {
            if (onPaymentSuccess) {
              onPaymentSuccess({
                ...order,
                ...statusRes,
                status: 'PRINTING',
              });
            }
          }, 350);
        }
      } catch (e) {
        // Silent polling error (expected if connection blips)
      }
    }, 3000);

    return () => {
      if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
    };
  }, [orderIdentifier, isPaid, order, onPaymentSuccess]);

  // Format timer into MM:SS
  const formattedTime = useMemo(() => {
    const minutes = Math.floor(timeLeft / 60);
    const seconds = timeLeft % 60;
    return `${minutes.toString().padStart(2, '0')}:${seconds
      .toString()
      .padStart(2, '0')}`;
  }, [timeLeft]);

  // Copy helper
  const handleCopy = (text, fieldName) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedField(fieldName);
    setTimeout(() => setCopiedField(null), 2000);
  };

  // Payment Verification Handler
  const handleVerifyPayment = async (customRef = null) => {
    setErrorMessage(null);
    setVerifying(true);
    const refToUse = customRef !== null ? customRef : referenceId.trim();

    try {
      const result = await verifyPayment(orderIdentifier, refToUse || null);
      setIsPaid(true);
      if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
      setTimeout(() => {
        if (onPaymentSuccess) {
          onPaymentSuccess({
            ...order,
            ...result,
            status: 'PRINTING',
          });
        }
      }, 350);
    } catch (err) {
      console.error('Payment verification failed:', err);
      setErrorMessage(
        err?.response?.data?.detail ||
          err?.message ||
          'Payment verification failed. Please try again or simulate approval.'
      );
    } finally {
      setVerifying(false);
    }
  };

  const dynamicUpiUri = paymentData?.upi_uri || paymentData?.qr_data || '';
  const currencySymbol = order?.currency === 'INR' ? '₹' : order?.currency || '₹';
  const totalAmountFormatted = Number(order?.total_amount || 0).toFixed(2);

  return (
    <div className={`w-full ${isTablet ? 'max-w-2xl' : 'max-w-xl'} mx-auto animate-fade-in ${isTablet ? 'pb-4' : 'pb-10'}`}>
      {/* Top Breadcrumb & Step Indicator */}
      <div className="mb-4 flex items-center justify-between">
        <button
          type="button"
          onClick={onCancel || onBackToOptions}
          disabled={verifying}
          className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-semibold text-slate-600 hover:text-brand-600 transition-colors disabled:opacity-50 p-1 cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{isTablet ? 'Cancel / Return to Welcome' : 'Adjust Options'}</span>
        </button>

        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand-50 text-brand-700 text-xs font-bold border border-brand-200 shadow-sm">
          <Sparkles className="w-3.5 h-3.5 text-brand-600" />
          <span>{isTablet ? 'Tablet Kiosk • Dynamic UPI Scanner' : 'Step 3 of 4 • Dynamic UPI Payment'}</span>
        </span>
      </div>

      {/* Main Payment Card */}
      <div className="bg-white rounded-3xl border border-slate-200/90 p-5 sm:p-7 shadow-card">
        {/* Card Header with Countdown */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-100 gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200 mb-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              <span>NPCI UPI Secured</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight">
              Pay via Dynamic UPI
            </h2>
            <p className="text-xs text-slate-500 font-medium">
              {isTablet
                ? 'Scan the QR code below with any UPI app on your phone to complete payment.'
                : 'Amount is pre-filled. Scan or tap to complete payment.'}
            </p>
          </div>

          {/* Session Timer */}
          <div
            className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-2xl border text-xs font-mono font-bold self-start sm:self-center ${
              timeLeft < 120
                ? 'bg-rose-50 border-rose-200 text-rose-700 animate-pulse'
                : 'bg-slate-50 border-slate-200 text-slate-700'
            }`}
          >
            <Clock className="w-3.5 h-3.5 text-slate-500" />
            <span>Time Left: {formattedTime}</span>
          </div>
        </div>

        {/* Order Amount Highlight Box */}
        <div className="my-5 p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900 to-brand-950 text-white shadow-md shadow-slate-900/10 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Order {order?.order_number || order?.order_id || 'SP-000000'}
              </span>
              <button
                type="button"
                onClick={() => handleCopy(order?.order_number || order?.order_id, 'orderId')}
                className="text-slate-400 hover:text-white transition-colors"
                title="Copy Order ID"
              >
                {copiedField === 'orderId' ? (
                  <Check className="w-3 h-3 text-emerald-400" />
                ) : (
                  <Copy className="w-3 h-3" />
                )}
              </button>
            </div>
            <p className="text-xs text-slate-300 mt-1 flex flex-wrap items-center gap-2">
              <span>{order?.selected_page_count || order?.page_count || 1} pages</span>
              <span>•</span>
              <span>{order?.copies || 1} {order?.copies === 1 ? 'copy' : 'copies'}</span>
              <span>•</span>
              <span className="capitalize">{String(order?.color_mode || '').toLowerCase().includes('color') ? 'Color' : 'B&W'}</span>
              <span>•</span>
              <span>{order?.duplex ? 'Duplex' : 'Single'}</span>
            </p>
          </div>

          <div className="text-right">
            <span className="text-2xl sm:text-3xl font-black text-white tracking-tight">
              {currencySymbol}{totalAmountFormatted}
            </span>
            <span className="block text-[10px] font-bold text-brand-400 uppercase tracking-wider">
              Exact Amount
            </span>
          </div>
        </div>

        {/* QR Code Presentation Area */}
        <div className="flex flex-col items-center justify-center py-4 bg-slate-50/70 rounded-2xl border border-slate-200/80 my-4 text-center">
          {loading ? (
            <div className="h-64 flex flex-col items-center justify-center gap-3">
              <Loader2 className="w-8 h-8 text-brand-600 animate-spin" />
              <p className="text-xs font-semibold text-slate-600">
                Generating dynamic UPI QR code...
              </p>
            </div>
          ) : timeLeft === 0 ? (
            <div className="h-64 flex flex-col items-center justify-center gap-3 p-6 text-center">
              <AlertCircle className="w-10 h-10 text-rose-500" />
              <p className="text-sm font-bold text-slate-800">
                Payment Session Expired
              </p>
              <p className="text-xs text-slate-500 max-w-xs">
                Your payment session has timed out. Click below to regenerate a fresh QR code.
              </p>
              <button
                type="button"
                onClick={() => {
                  setTimeLeft(PAYMENT_TIMEOUT_SECONDS);
                  initializePayment();
                }}
                className="mt-2 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-600 text-white font-bold text-xs hover:bg-brand-700 transition-colors cursor-pointer"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Refresh QR Code</span>
              </button>
            </div>
          ) : (
            <>
              {/* Dynamic QR Code Frame */}
              <div className="relative p-3.5 bg-white rounded-2xl shadow-sm border border-slate-200 inline-block">
                <QRCodeSVG
                  value={dynamicUpiUri}
                  size={isTablet ? 250 : 210}
                  level="H"
                  includeMargin={true}
                  imageSettings={{
                    src: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="%232563eb" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/></svg>',
                    height: 28,
                    width: 28,
                    excavate: true,
                  }}
                />
              </div>

              {/* Scan Prompt */}
              <p className="text-xs sm:text-sm font-extrabold text-slate-900 mt-3">
                Scan with any UPI App
              </p>
              <p className="text-[11px] text-slate-500 font-medium mt-0.5">
                Amount ₹{totalAmountFormatted} will be automatically locked in your UPI app
              </p>

              {/* Supported UPI Apps Pills */}
              <div className="mt-3 flex flex-wrap items-center justify-center gap-1.5 px-4">
                {['Google Pay', 'PhonePe', 'Paytm', 'BHIM', 'Navi', 'Cred'].map((appName) => (
                  <span
                    key={appName}
                    className="inline-flex items-center px-2 py-0.5 rounded-md bg-white border border-slate-200 text-[10px] font-bold text-slate-600 shadow-2xs"
                  >
                    {appName}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Direct Mobile Tap-to-Pay Button (User Mobile Website) */}
        {dynamicUpiUri && timeLeft > 0 && !isTablet && (
          <div className="my-4">
            <a
              href={dynamicUpiUri}
              className="w-full inline-flex items-center justify-center gap-2 py-3.5 px-5 rounded-2xl font-bold text-sm text-white bg-emerald-600 hover:bg-emerald-700 active:scale-[0.99] transition-all shadow-md shadow-emerald-600/20 text-center cursor-pointer"
            >
              <Smartphone className="w-4 h-4" />
              <span>Tap to Pay on Mobile (GPay / PhonePe / Paytm)</span>
              <ExternalLink className="w-3.5 h-3.5 ml-0.5" />
            </a>
            <p className="text-[10px] text-center text-slate-400 mt-1.5 font-medium">
              If browsing on mobile, tapping above will launch your installed UPI app directly
            </p>
          </div>
        )}

        {/* Tablet Kiosk Phone Scan Prompt */}
        {dynamicUpiUri && timeLeft > 0 && isTablet && (
          <div className="my-4 p-3.5 rounded-2xl bg-brand-50/70 border border-brand-100 flex items-center justify-center gap-2.5 text-brand-800 text-xs font-semibold text-center">
            <Smartphone className="w-4 h-4 text-brand-600 shrink-0" />
            <span>Open Google Pay, PhonePe, Paytm, or any UPI app on your phone and scan the QR code above.</span>
          </div>
        )}

        {/* UPI Details Grid (Payee ID & Reference) */}
        <div className="my-5 rounded-2xl border border-slate-200 bg-slate-50/70 divide-y divide-slate-200 text-xs">
          <div className="p-3 sm:p-3.5 flex items-center justify-between">
            <span className="text-slate-500 font-medium">Payee UPI ID:</span>
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold text-slate-900">
                {paymentData?.upi_id || 'smartprint@upi'}
              </span>
              <button
                type="button"
                onClick={() => handleCopy(paymentData?.upi_id || 'smartprint@upi', 'upiId')}
                className="p-1 rounded text-slate-400 hover:text-brand-600 hover:bg-white transition-colors cursor-pointer"
                title="Copy UPI ID"
              >
                {copiedField === 'upiId' ? (
                  <Check className="w-3.5 h-3.5 text-emerald-600" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
          </div>

          <div className="p-3 sm:p-3.5 flex items-center justify-between">
            <span className="text-slate-500 font-medium">Payee Name:</span>
            <span className="font-semibold text-slate-800">
              {paymentData?.upi_name || 'SmartPrint Kiosk'}
            </span>
          </div>

          <div className="p-3 sm:p-3.5 flex items-center justify-between">
            <span className="text-slate-500 font-medium">Exact Amount:</span>
            <div className="flex items-center gap-2">
              <span className="font-bold text-slate-900 font-mono">
                ₹{totalAmountFormatted}
              </span>
              <button
                type="button"
                onClick={() => handleCopy(totalAmountFormatted, 'amount')}
                className="p-1 rounded text-slate-400 hover:text-brand-600 hover:bg-white transition-colors cursor-pointer"
                title="Copy Amount"
              >
                {copiedField === 'amount' ? (
                  <Check className="w-3.5 h-3.5 text-emerald-600" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Verification & Manual UTR Section */}
        <div className="my-5 p-4 rounded-2xl bg-brand-50/50 border border-brand-100">
          <label
            htmlFor="upi-reference-input"
            className="block text-xs font-bold text-slate-800 mb-1"
          >
            UPI Reference / UTR Number (Optional):
          </label>
          <input
            id="upi-reference-input"
            type="text"
            value={referenceId}
            onChange={(e) => setReferenceId(e.target.value)}
            placeholder="e.g. 430129847192 (or leave blank to auto-verify)"
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 bg-white text-xs font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <p className="text-[11px] text-slate-500 mt-1.5 font-medium">
            Once you have completed the payment in your UPI app, click below to verify and send your document to the printer queue.
          </p>
        </div>

        {/* Error message */}
        {errorMessage && (
          <div className="mb-4 p-3.5 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs font-medium flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col gap-2.5">
          {/* Primary Verify Button */}
          <button
            id="verify-payment-btn"
            type="button"
            onClick={() => handleVerifyPayment(null)}
            disabled={verifying || loading || timeLeft === 0 || isPaid}
            className="w-full inline-flex items-center justify-center gap-2 py-4 px-6 rounded-2xl font-bold text-base text-white bg-brand-600 hover:bg-brand-700 active:scale-[0.99] transition-all shadow-md shadow-brand-600/25 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {isPaid ? (
              <>
                <CheckCircle2 className="w-5 h-5 text-emerald-400 animate-pulse" />
                <span>Payment Verified! Starting Print Machine...</span>
              </>
            ) : verifying ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                <span>Verifying Payment...</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-5 h-5" />
                <span>I Have Paid • Verify Payment</span>
              </>
            )}
          </button>

          {/* Quick Simulation / Demo Button */}
          <button
            id="simulate-payment-btn"
            type="button"
            onClick={() => handleVerifyPayment(`DEMO-PAID-${Date.now()}`)}
            disabled={verifying || loading || timeLeft === 0}
            className="w-full py-2.5 px-4 rounded-xl font-semibold text-xs text-brand-700 bg-brand-50 hover:bg-brand-100/80 border border-brand-200 transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
          >
            <Sparkles className="w-3.5 h-3.5 text-brand-600" />
            <span>Quick Test: Simulate Instant Payment</span>
          </button>

          {/* Back Button */}
          <button
            type="button"
            onClick={onCancel || onBackToOptions}
            disabled={verifying}
            className="w-full py-2 px-4 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors cursor-pointer text-center mt-1"
          >
            {isTablet ? 'Cancel and Return to Welcome Screen' : 'Cancel and Return to Print Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}
