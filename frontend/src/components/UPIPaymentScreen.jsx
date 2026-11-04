import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  Check,
  ShieldCheck,
  Clock,
  Loader2,
  AlertCircle,
  RefreshCw,
  QrCode,
  Smartphone,
  Tablet,
  Printer,
  Sparkles,
} from 'lucide-react';
import {
  startPayment,
  createCheckout,
  getPaymentStatus,
} from '../services/api';

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

    try {
      const urlParams = new URLSearchParams(window.location.search);
      const urlError = urlParams.get('error');
      if (urlError) {
        setErrorMessage(decodeURIComponent(urlError));
      }
    } catch (e) {}
  }, []);

  const [paymentData, setPaymentData] = useState(null);
  const [checkoutData, setCheckoutData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [configNotice, setConfigNotice] = useState(null);
  const [copiedField, setCopiedField] = useState(null);
  const [timeLeft, setTimeLeft] = useState(PAYMENT_TIMEOUT_SECONDS);
  const [isPaid, setIsPaid] = useState(false);

  const orderIdentifier = order?.order_id || order?.id || order?.order_number;
  const pollingTimerRef = useRef(null);

  // Initialize Payment with PayU Gateway
  const initializePayment = async () => {
    if (!orderIdentifier) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      const [startRes, checkoutRes] = await Promise.allSettled([
        startPayment(orderIdentifier),
        createCheckout(orderIdentifier, 'payu'),
      ]);

      if (startRes.status === 'fulfilled') {
        const data = startRes.value;
        setPaymentData(data);
        if (
          data.payment_status === 'PAID' ||
          data.is_paid ||
          data.status === 'CONFIRMED' ||
          data.status === 'PAID' ||
          data.status === 'PRINTING' ||
          data.status === 'COMPLETED'
        ) {
          setIsPaid(true);
          if (onPaymentSuccess) {
            onPaymentSuccess({ ...order, ...data, status: 'CONFIRMED', payment_status: 'PAID' });
          }
          return;
        }
      }

      if (checkoutRes.status === 'fulfilled') {
        const cData = checkoutRes.value;
        setCheckoutData(cData);
      } else if (checkoutRes.status === 'rejected') {
        const detail = checkoutRes.reason?.response?.data?.detail || '';
        if (detail.includes('PAYU_MERCHANT_KEY') || detail.includes('PayU payment gateway is not configured')) {
          setConfigNotice('PayU merchant credentials are not yet configured on the server. Please complete payment using the tablet screen.');
        }
      }
    } catch (err) {
      console.error('Failed to initialize PayU payment:', err);
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

  // Real-time polling to detect verified payment from PayU / Tablet scan
  useEffect(() => {
    if (isPaid || !orderIdentifier) return;

    pollingTimerRef.current = setInterval(async () => {
      try {
        const statusRes = await getPaymentStatus(orderIdentifier);
        if (
          statusRes &&
          (statusRes.is_paid ||
            statusRes.status === 'CONFIRMED' ||
            statusRes.status === 'PAID' ||
            statusRes.status === 'PRINTING' ||
            statusRes.status === 'COMPLETED' ||
            statusRes.payment_status === 'PAID' ||
            statusRes.payment_status === 'SUCCESS')
        ) {
          clearInterval(pollingTimerRef.current);
          setIsPaid(true);
          setTimeout(() => {
            if (onPaymentSuccess) {
              onPaymentSuccess({
                ...order,
                ...statusRes,
                status: 'CONFIRMED',
                payment_status: 'PAID',
              });
            }
          }, 400);
        }
      } catch (e) {
        // Silent polling error
      }
    }, 2000);

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

  // Secure redirect to official PayU Hosted Checkout interface
  const redirectToPayU = (params) => {
    if (!params) return;
    const actionUrl =
      params.action ||
      checkoutData?.checkout_url ||
      (checkoutData?.mode === 'live'
        ? 'https://secure.payu.in/_payment'
        : 'https://test.payu.in/_payment');

    const form = document.createElement('form');
    form.method = 'POST';
    form.action = actionUrl;
    form.style.display = 'none';

    Object.entries(params).forEach(([key, val]) => {
      if (key !== 'action' && val !== undefined && val !== null) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = key;
        input.value = String(val);
        form.appendChild(input);
      }
    });

    document.body.appendChild(form);
    form.submit();
  };

  // Manual status check handler
  const handleCheckStatus = async () => {
    if (!orderIdentifier || verifying) return;
    setVerifying(true);
    setErrorMessage(null);
    try {
      const statusRes = await getPaymentStatus(orderIdentifier);
      if (
        statusRes &&
        (statusRes.is_paid ||
          statusRes.status === 'CONFIRMED' ||
          statusRes.status === 'PAID' ||
          statusRes.status === 'PRINTING' ||
          statusRes.status === 'COMPLETED' ||
          statusRes.payment_status === 'PAID' ||
          statusRes.payment_status === 'SUCCESS')
      ) {
        setIsPaid(true);
        if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
        if (onPaymentSuccess) {
          onPaymentSuccess({
            ...order,
            ...statusRes,
            status: 'CONFIRMED',
            payment_status: 'PAID',
          });
        }
      } else {
        setErrorMessage('Payment not yet detected. Please scan the QR code on the tablet and complete UPI payment.');
      }
    } catch (err) {
      setErrorMessage('Could not check status right now. Retrying automatically...');
    } finally {
      setVerifying(false);
    }
  };

  const currencySymbol = order?.currency === 'INR' ? '₹' : order?.currency || '₹';
  const totalAmountFormatted = Number(order?.total_amount || 0).toFixed(2);
  const orderNumberDisplay = order?.order_number || order?.order_id || orderIdentifier || 'SP-000000';

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
          <span>Adjust Options</span>
        </button>

        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-bold border border-emerald-200 shadow-sm">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
          <span>Step 3 of 4 • PayU UPI Payment</span>
        </span>
      </div>

      {/* Main Payment Card */}
      <div className="bg-white rounded-3xl border border-slate-200/90 p-5 sm:p-7 shadow-card">
        {/* Card Header with Countdown */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-100 gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200 mb-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              <span>PayU India • Secure Gateway</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight">
              PAYU UPI PAYMENT
            </h2>
            <p className="text-xs text-slate-500 font-medium">
              Complete your UPI payment using the SmartPrint payment tablet.
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
        <div className="my-5 p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900 to-emerald-950 text-white shadow-md shadow-slate-900/10 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Order {orderNumberDisplay}
              </span>
              <button
                type="button"
                onClick={() => handleCopy(orderNumberDisplay, 'orderId')}
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
            <span className="block text-[10px] font-bold text-emerald-400 uppercase tracking-wider">
              Exact Amount
            </span>
          </div>
        </div>

        {/* Live Pending Status Banner */}
        <div className="mb-4 p-3.5 rounded-2xl bg-amber-50/90 border border-amber-200 text-amber-900 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
            </span>
            <span className="font-semibold">
              {isPaid ? 'Payment Confirmed!' : 'Waiting for payment...'}
            </span>
          </div>
          <span className="text-[10px] font-mono text-amber-700 bg-amber-100/70 px-2 py-0.5 rounded-full font-bold">
            Live Polling Active
          </span>
        </div>

        {/* REQUIRED INSTRUCTION BOX */}
        <div className="flex flex-col items-center justify-center p-6 sm:p-8 bg-gradient-to-b from-slate-50 to-emerald-50/30 rounded-3xl border-2 border-emerald-500/20 my-4 text-center">
          {loading ? (
            <div className="py-8 flex flex-col items-center justify-center gap-3">
              <Loader2 className="w-8 h-8 text-emerald-600 animate-spin" />
              <p className="text-xs font-semibold text-slate-600">
                Connecting to SmartPrint Payment Kiosk...
              </p>
            </div>
          ) : timeLeft === 0 ? (
            <div className="py-6 flex flex-col items-center justify-center gap-3 text-center">
              <AlertCircle className="w-10 h-10 text-rose-500" />
              <p className="text-sm font-bold text-slate-800">
                Payment Session Expired
              </p>
              <p className="text-xs text-slate-500 max-w-xs">
                Your payment session has timed out. Click below to regenerate your session.
              </p>
              <button
                type="button"
                onClick={() => {
                  setTimeLeft(PAYMENT_TIMEOUT_SECONDS);
                  initializePayment();
                }}
                className="mt-2 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 text-white font-bold text-xs hover:bg-emerald-700 transition-colors cursor-pointer"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Refresh Payment Session</span>
              </button>
            </div>
          ) : (
            <>
              {/* Tablet Icon graphic */}
              <div className="relative mb-4 flex items-center justify-center">
                <div className="w-20 h-20 rounded-2xl bg-emerald-100/80 border border-emerald-300 flex items-center justify-center text-emerald-700 shadow-inner">
                  <Tablet className="w-10 h-10" />
                </div>
                <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-full bg-brand-600 text-white flex items-center justify-center shadow-md">
                  <QrCode className="w-4 h-4" />
                </div>
              </div>

              {/* Exact instruction prompt */}
              <h3 className="text-base sm:text-lg font-black text-slate-900 max-w-md leading-snug">
                Please scan the QR code displayed on the SmartPrint payment tablet to complete your payment.
              </h3>

              <p className="text-xs text-slate-500 font-medium mt-2 max-w-sm">
                The PayU dynamic QR code for <strong className="text-slate-800">{orderNumberDisplay}</strong> is active on the tablet screen next to the printer.
              </p>

              {/* How it works steps on kiosk */}
              <div className="mt-5 w-full max-w-md grid grid-cols-1 sm:grid-cols-3 gap-2 text-left">
                <div className="p-2.5 rounded-xl bg-white border border-slate-200/80 shadow-2xs">
                  <div className="text-[10px] font-bold text-emerald-700">STEP 1</div>
                  <div className="text-xs font-semibold text-slate-800 mt-0.5">Look at Tablet</div>
                  <div className="text-[10px] text-slate-500">Find the QR code for {orderNumberDisplay}</div>
                </div>
                <div className="p-2.5 rounded-xl bg-white border border-slate-200/80 shadow-2xs">
                  <div className="text-[10px] font-bold text-emerald-700">STEP 2</div>
                  <div className="text-xs font-semibold text-slate-800 mt-0.5">Scan with UPI</div>
                  <div className="text-[10px] text-slate-500">Pay ₹{totalAmountFormatted} with your UPI app</div>
                </div>
                <div className="p-2.5 rounded-xl bg-white border border-slate-200/80 shadow-2xs">
                  <div className="text-[10px] font-bold text-emerald-700">STEP 3</div>
                  <div className="text-xs font-semibold text-slate-800 mt-0.5">Auto Confirm</div>
                  <div className="text-[10px] text-slate-500">Printing starts automatically once paid</div>
                </div>
              </div>

              {/* Supported UPI Apps */}
              <div className="mt-4 flex flex-wrap items-center justify-center gap-1.5">
                {['Google Pay', 'PhonePe', 'Paytm', 'BHIM UPI'].map((appName) => (
                  <span
                    key={appName}
                    className="inline-flex items-center px-2 py-0.5 rounded-md bg-white border border-emerald-200 text-[10px] font-bold text-emerald-800 shadow-2xs"
                  >
                    {appName}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Configuration Notice */}
        {configNotice && !isPaid && (
          <div className="mb-4 p-3.5 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 text-xs font-medium flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-amber-950">PayU Gateway Setup Pending</p>
              <p className="mt-0.5">{configNotice}</p>
            </div>
          </div>
        )}

        {/* Error message */}
        {errorMessage && (
          <div className="mb-4 p-3.5 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs font-medium flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col gap-2.5 mt-4">
          {/* Primary Pay Online via PayU Gateway Button */}
          {checkoutData?.payu_params && !isPaid && (
            <button
              id="payu-checkout-btn"
              type="button"
              onClick={() => redirectToPayU(checkoutData.payu_params)}
              disabled={verifying || timeLeft === 0 || isPaid}
              className="w-full inline-flex items-center justify-center gap-2 py-3.5 px-6 rounded-2xl font-bold text-sm sm:text-base text-white bg-emerald-600 hover:bg-emerald-700 active:scale-[0.99] transition-all shadow-md shadow-emerald-600/25 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              <span>Pay Online via PayU ({currencySymbol}{totalAmountFormatted})</span>
            </button>
          )}

          {/* Check Status Button */}
          <button
            id="check-payment-status-btn"
            type="button"
            onClick={handleCheckStatus}
            disabled={verifying || loading || timeLeft === 0 || isPaid}
            className={`w-full inline-flex items-center justify-center gap-2 py-3 px-6 rounded-2xl font-bold text-sm transition-all cursor-pointer ${
              checkoutData?.payu_params && !isPaid
                ? 'text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200'
                : 'text-white bg-emerald-600 hover:bg-emerald-700 shadow-md shadow-emerald-600/25'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {isPaid ? (
              <>
                <CheckCircle2 className="w-5 h-5 text-emerald-600 animate-pulse" />
                <span>Payment Confirmed! Printing Order...</span>
              </>
            ) : verifying ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                <span>Checking Payment Status...</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-5 h-5" />
                <span>I Have Scanned on Tablet • Check Status</span>
              </>
            )}
          </button>

          {/* Cancel Button */}
          <button
            type="button"
            onClick={onCancel || onBackToOptions}
            disabled={verifying}
            className="w-full py-2 px-4 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors cursor-pointer text-center"
          >
            Cancel and Return to Print Settings
          </button>
        </div>
      </div>
    </div>
  );
}
