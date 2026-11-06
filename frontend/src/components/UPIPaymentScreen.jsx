import React, { useState, useEffect, useRef, useMemo } from 'react';
import { QRCodeSVG } from 'qrcode.react';
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
  RotateCcw,
  Smartphone,
  ExternalLink,
  QrCode,
  Info,
} from 'lucide-react';
import {
  startPayment,
  createCheckout,
  getPaymentStatus,
  getPayUAppIntent,
} from '../services/api';

const PAYMENT_TIMEOUT_SECONDS = 600; // 10 minutes

// Device detection helper
function getDeviceType() {
  if (typeof navigator === 'undefined') return 'desktop';
  const ua = navigator.userAgent || '';
  if (/Android/i.test(ua)) return 'android';
  if (/iPhone|iPad|iPod/i.test(ua)) return 'ios';
  return 'desktop';
}

// App Logo Components
function PhonePeLogo() {
  return (
    <div className="w-10 h-10 rounded-2xl bg-[#5f259f] flex items-center justify-center text-white font-extrabold text-lg shadow-sm shrink-0">
      <span style={{ fontFamily: 'sans-serif' }}>पे</span>
    </div>
  );
}

function GooglePayLogo() {
  return (
    <div className="w-10 h-10 rounded-2xl bg-white border border-slate-200 flex items-center justify-center shadow-sm shrink-0 p-1">
      <svg viewBox="0 0 48 48" className="w-7 h-7">
        <path fill="#4285F4" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
        <path fill="#34A853" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
        <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
        <path fill="#EA4335" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
      </svg>
    </div>
  );
}

function PaytmLogo() {
  return (
    <div className="w-10 h-10 rounded-2xl bg-[#002e6e] flex items-center justify-center text-white font-extrabold text-[11px] tracking-tight shadow-sm shrink-0">
      <span className="text-[#00b9f5]">pay</span><span>tm</span>
    </div>
  );
}

function BhimLogo() {
  return (
    <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-[#005a9c] to-[#00875a] flex items-center justify-center text-white font-black text-xs tracking-wider shadow-sm shrink-0">
      <span>BHIM</span>
    </div>
  );
}

function GenericUpiLogo() {
  return (
    <div className="w-10 h-10 rounded-2xl bg-emerald-600 flex items-center justify-center text-white font-extrabold text-xs shadow-sm shrink-0">
      <QrCode className="w-5 h-5" />
    </div>
  );
}

export default function UPIPaymentScreen({
  order,
  onPaymentSuccess,
  onBackToOptions,
  onCancel,
  isTablet = false,
}) {
  const [checkoutData, setCheckoutData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [openingApp, setOpeningApp] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [configNotice, setConfigNotice] = useState(null);
  const [copiedField, setCopiedField] = useState(null);
  const [timeLeft, setTimeLeft] = useState(PAYMENT_TIMEOUT_SECONDS);
  const [isPaid, setIsPaid] = useState(false);
  const [paidDetails, setPaidDetails] = useState(null);
  const [deviceType, setDeviceType] = useState('desktop');

  const orderIdentifier = order?.order_id || order?.id || order?.order_number;
  const pollingTimerRef = useRef(null);

  // Detect device type on mount
  useEffect(() => {
    setDeviceType(getDeviceType());
  }, []);

  // Check URL query parameters for PayU callback status or errors
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;

    try {
      const urlParams = new URLSearchParams(window.location.search);
      const urlError = urlParams.get('error');
      const urlStatus = urlParams.get('payment_status');
      if (urlError) {
        setErrorMessage(decodeURIComponent(urlError));
      } else if (urlStatus === 'failure' || urlStatus === 'failed') {
        setErrorMessage('Payment was declined or cancelled at your UPI app. Please retry below.');
      } else if (urlStatus === 'cancelled') {
        setErrorMessage('Payment was cancelled. You can select another UPI app below.');
      }
    } catch (e) {}
  }, []);

  // Initialize Payment with PayU Gateway
  const initializePayment = async (isRetry = false) => {
    if (!orderIdentifier) return;
    setLoading(true);
    if (isRetry) {
      setErrorMessage(null);
    }
    try {
      const [startRes, checkoutRes] = await Promise.allSettled([
        startPayment(orderIdentifier),
        createCheckout(orderIdentifier, 'payu'),
      ]);

      if (startRes.status === 'fulfilled') {
        const data = startRes.value;
        if (
          data.payment_status === 'PAID' ||
          data.is_paid ||
          data.status === 'CONFIRMED' ||
          data.status === 'PAID' ||
          data.status === 'PRINTING' ||
          data.status === 'COMPLETED'
        ) {
          setIsPaid(true);
          setPaidDetails(data);
          if (onPaymentSuccess) {
            onPaymentSuccess({ ...order, ...data, status: 'CONFIRMED', payment_status: 'PAID' });
          }
          return;
        }
      }

      if (checkoutRes.status === 'fulfilled') {
        const cData = checkoutRes.value;
        setCheckoutData(cData);
        if (cData.activation_required) {
          setConfigNotice(cData.activation_details || 'PayU UPI Smart Intent requires merchant account activation.');
        }
      } else if (checkoutRes.status === 'rejected') {
        const detail = checkoutRes.reason?.response?.data?.detail || '';
        if (detail.includes('PAYU_MERCHANT_KEY') || detail.includes('PayU payment gateway is not configured')) {
          setConfigNotice('PayU merchant credentials are not yet configured on the server. Please check backend environment variables.');
        } else {
          setErrorMessage(detail || 'Could not initiate PayU checkout session.');
        }
      }
    } catch (err) {
      console.error('Failed to initialize PayU Smart Intent payment:', err);
      setErrorMessage('Could not connect to payment server. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    initializePayment(false);
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

  // Real-time polling to detect verified payment from PayU server
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
          setPaidDetails(statusRes);
          setTimeout(() => {
            if (onPaymentSuccess) {
              onPaymentSuccess({
                ...order,
                ...statusRes,
                status: 'CONFIRMED',
                payment_status: 'PAID',
              });
            }
          }, 800);
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

  // Launch targeted UPI application via PayU Smart Intent deep link
  const handleAppSelect = async (appKey) => {
    if (isPaid || verifying) return;
    setOpeningApp(appKey);
    setErrorMessage(null);

    try {
      // 1. Check if we already have the intent data or request specific intent
      let targetIntent = checkoutData?.upi_apps?.[appKey];

      // If app intent is not yet ready, fetch it on the fly
      if (!targetIntent?.android_intent && !targetIntent?.universal_upi_uri) {
        try {
          const freshIntent = await getPayUAppIntent(orderIdentifier, appKey);
          if (freshIntent?.success && freshIntent?.apps?.[appKey]) {
            targetIntent = freshIntent.apps[appKey];
          }
        } catch (e) {
          console.warn('Could not fetch app-specific intent, using universal fallback:', e);
        }
      }

      const universalUri = targetIntent?.universal_upi_uri || checkoutData?.upi_uri || checkoutData?.qr_data;
      const androidIntent = targetIntent?.android_intent || targetIntent?.android_scheme || universalUri;
      const iosScheme = targetIntent?.ios_scheme || universalUri;

      if (!universalUri && !androidIntent) {
        setErrorMessage('Payment link could not be generated. Please click Retry Payment.');
        setOpeningApp(null);
        return;
      }

      // 2. Platform-specific execution
      if (deviceType === 'android') {
        // Android: Open via Android Intent URL
        const launchUrl = androidIntent || universalUri;
        window.location.href = launchUrl;

        // Fallback after 2.5s if the specific app isn't installed
        setTimeout(() => {
          if (!isPaid && universalUri) {
            // Attempt generic UPI chooser as fallback
            window.location.href = universalUri;
          }
        }, 2500);
      } else if (deviceType === 'ios') {
        // iOS: Open via URL scheme
        const launchUrl = iosScheme || universalUri;
        window.location.href = launchUrl;
      } else {
        // Desktop: Mobile app cannot be launched directly on desktop.
        // Alert user to scan the QR code displayed
        setErrorMessage(`To pay with ${targetIntent?.name || 'UPI'}, scan the QR code below using your mobile phone camera or UPI app.`);
      }
    } catch (err) {
      console.error('Failed to open UPI app:', err);
      setErrorMessage('Could not launch the selected UPI app. Please try another app or scan the QR code.');
    } finally {
      setTimeout(() => setOpeningApp(null), 2000);
    }
  };

  // Manual status check handler
  const handleCheckStatus = async () => {
    if (!orderIdentifier || verifying || isPaid) return;
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
        setPaidDetails(statusRes);
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
        setErrorMessage('Payment not yet detected. Once you approve the payment in your UPI app, please check again.');
      }
    } catch (err) {
      setErrorMessage('Could not check status right now. Retrying automatically...');
    } finally {
      setVerifying(false);
    }
  };

  // Handle Retry Payment
  const handleRetryPayment = () => {
    setErrorMessage(null);
    setTimeLeft(PAYMENT_TIMEOUT_SECONDS);
    initializePayment(true);
  };

  const currencySymbol = order?.currency === 'INR' ? '₹' : order?.currency || '₹';
  const totalAmountFormatted = Number(order?.total_amount || 0).toFixed(2);
  const orderNumberDisplay = order?.order_number || order?.order_id || orderIdentifier || 'SP-000000';
  const transactionRef = paidDetails?.payment_reference || checkoutData?.payment_session_id;

  const upiQrData = checkoutData?.upi_intent?.universal_upi_uri || checkoutData?.upi_uri || checkoutData?.qr_data;

  // The 5 Required UPI App options
  const appOptions = [
    {
      key: 'phonepe',
      name: 'PhonePe',
      subtitle: 'Instant UPI Payment',
      Logo: PhonePeLogo,
      badge: 'Popular',
    },
    {
      key: 'googlepay',
      name: 'Google Pay',
      subtitle: 'GPay UPI',
      Logo: GooglePayLogo,
      badge: 'Fast',
    },
    {
      key: 'paytm',
      name: 'Paytm',
      subtitle: 'Paytm UPI / Wallet',
      Logo: PaytmLogo,
    },
    {
      key: 'bhim',
      name: 'BHIM',
      subtitle: 'NPCI Official App',
      Logo: BhimLogo,
    },
    {
      key: 'genericintent',
      name: 'Other UPI Apps',
      subtitle: 'CRED, WhatsApp, Bank UPI',
      Logo: GenericUpiLogo,
    },
  ];

  return (
    <div className={`w-full ${isTablet ? 'max-w-2xl' : 'max-w-xl'} mx-auto animate-fade-in ${isTablet ? 'pb-4' : 'pb-10'}`}>
      {/* Top Breadcrumb & Step Indicator */}
      <div className="mb-4 flex items-center justify-between">
        <button
          type="button"
          onClick={onCancel || onBackToOptions}
          disabled={verifying || isPaid}
          className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-semibold text-slate-600 hover:text-brand-600 transition-colors disabled:opacity-50 p-1 cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Adjust Options</span>
        </button>

        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-bold border border-emerald-200 shadow-sm">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
          <span>Step 3 of 4 • PayU Smart Intent</span>
        </span>
      </div>

      {/* Main Payment Card */}
      <div className="bg-white rounded-3xl border border-slate-200/90 p-5 sm:p-7 shadow-card">
        {/* Card Header with Countdown */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-100 gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200 mb-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              <span>PayU India • UPI Smart Intent</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight">
              PAYMENT SUMMARY
            </h2>
            <p className="text-xs text-slate-500 font-medium">
              Choose your preferred UPI application to pay instantly.
            </p>
          </div>

          {/* Session Timer */}
          {!isPaid && (
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
          )}
        </div>

        {/* SUCCESSFUL PAYMENT VIEW */}
        {isPaid ? (
          <div className="my-5 p-5 sm:p-6 rounded-2xl bg-emerald-50 border-2 border-emerald-500/80 text-emerald-950 space-y-4 animate-fade-in">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-2xl bg-emerald-600 text-white flex items-center justify-center shrink-0 shadow-sm">
                <CheckCircle2 className="w-7 h-7" />
              </div>
              <div>
                <h3 className="text-lg font-extrabold text-emerald-900 leading-tight">
                  Payment Successful!
                </h3>
                <p className="text-xs text-emerald-700 font-medium mt-0.5">
                  Verified authoritatively by PayU India server.
                </p>
              </div>
            </div>

            <div className="bg-white/90 rounded-xl p-3.5 border border-emerald-200 text-xs space-y-2">
              <div className="flex justify-between items-center py-1 border-b border-emerald-100">
                <span className="text-slate-500 font-medium">Order Number:</span>
                <span className="font-mono font-extrabold text-slate-900">{orderNumberDisplay}</span>
              </div>
              <div className="flex justify-between items-center py-1 border-b border-emerald-100">
                <span className="text-slate-500 font-medium">Total Amount Paid:</span>
                <span className="font-extrabold text-emerald-700">{currencySymbol}{totalAmountFormatted}</span>
              </div>
              {transactionRef && (
                <div className="flex justify-between items-center py-1 border-b border-emerald-100">
                  <span className="text-slate-500 font-medium">Transaction Reference:</span>
                  <span className="font-mono font-bold text-slate-800 text-[11px] truncate max-w-[200px]">{transactionRef}</span>
                </div>
              )}
              <div className="flex justify-between items-center py-1">
                <span className="text-slate-500 font-medium">Order Confirmation:</span>
                <span className="font-bold text-emerald-700">Confirmed on Tablet Kiosk</span>
              </div>
            </div>

            <button
              type="button"
              onClick={() => onPaymentSuccess && onPaymentSuccess({ ...order, ...paidDetails, status: 'CONFIRMED', payment_status: 'PAID' })}
              className="w-full py-3.5 px-4 rounded-xl font-bold text-sm text-white bg-emerald-600 hover:bg-emerald-700 transition-colors shadow-sm cursor-pointer text-center"
            >
              View Order Confirmation & Printer Status
            </button>
          </div>
        ) : (
          <>
            {/* Order Number & Amount Highlight Box */}
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
                    onClick={() => handleCopy(orderNumberDisplay, 'orderId')}
                    className="text-slate-400 hover:text-white transition-colors"
                    title="Copy Order Number"
                  >
                    {copiedField === 'orderId' ? (
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
                <p className="text-xs text-slate-300 mt-1.5 flex flex-wrap items-center gap-2">
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

            {/* PAYMENT FAILED ALERT WITH RETRY OPTION */}
            {errorMessage && (
              <div className="mb-5 p-4 rounded-2xl bg-rose-50 border-2 border-rose-300 text-rose-900 text-xs sm:text-sm animate-fade-in shadow-xs">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="font-extrabold text-rose-900 text-sm">Payment Notice</p>
                    <p className="mt-1 text-rose-800 leading-relaxed">{errorMessage}</p>
                    <button
                      type="button"
                      onClick={handleRetryPayment}
                      className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs transition-colors shadow-xs cursor-pointer"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Retry Payment</span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Configuration / Activation Notice */}
            {configNotice && (
              <div className="mb-4 p-4 rounded-2xl bg-amber-50 border border-amber-300 text-amber-950 text-xs font-medium">
                <div className="flex items-start gap-2.5">
                  <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-bold">PayU UPI Smart Intent Activation Required</p>
                    <p className="mt-1 text-amber-900 leading-relaxed">{configNotice}</p>
                    {checkoutData?.checkout_url && (
                      <a
                        href={checkoutData.checkout_url}
                        className="mt-2 inline-flex items-center gap-1.5 text-xs font-bold text-amber-950 underline hover:text-black"
                      >
                        <span>Open PayU Checkout Fallback</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* UPI SMART INTENT APP SELECTION LIST */}
            <div className="my-4">
              <div className="flex items-center justify-between mb-2.5">
                <label className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                  <Smartphone className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Choose Your UPI App</span>
                </label>
                <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                  Direct Intent
                </span>
              </div>

              {loading ? (
                <div className="py-8 flex flex-col items-center justify-center gap-3 bg-slate-50 rounded-2xl border border-slate-200">
                  <Loader2 className="w-7 h-7 text-emerald-600 animate-spin" />
                  <p className="text-xs font-semibold text-slate-600">
                    Generating PayU Smart Intent details...
                  </p>
                </div>
              ) : (
                <div className="space-y-2.5">
                  {appOptions.map((app) => {
                    const AppIcon = app.Logo;
                    const isOpening = openingApp === app.key;
                    return (
                      <button
                        key={app.key}
                        id={`pay-via-${app.key}-btn`}
                        type="button"
                        onClick={() => handleAppSelect(app.key)}
                        disabled={loading || verifying || timeLeft === 0 || isPaid}
                        className="w-full p-3.5 sm:p-4 rounded-2xl border-2 border-slate-200/90 hover:border-emerald-500 bg-white hover:bg-emerald-50/30 transition-all flex items-center justify-between shadow-2xs group cursor-pointer active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <div className="flex items-center gap-3.5 text-left">
                          <AppIcon />
                          <div>
                            <div className="font-extrabold text-sm sm:text-base text-slate-900 group-hover:text-emerald-700 transition-colors flex items-center gap-2">
                              <span>{app.name}</span>
                              {app.badge && (
                                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-100/90 px-2 py-0.5 rounded-full">
                                  {app.badge}
                                </span>
                              )}
                            </div>
                            <div className="text-xs text-slate-500 font-medium">
                              {app.subtitle}
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          {isOpening ? (
                            <Loader2 className="w-5 h-5 text-emerald-600 animate-spin" />
                          ) : (
                            <span className="text-xs font-bold text-emerald-700 bg-emerald-50 group-hover:bg-emerald-600 group-hover:text-white px-3 py-1.5 rounded-xl border border-emerald-200 transition-all">
                              Pay {currencySymbol}{totalAmountFormatted}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* DESKTOP VIEW: PAYU INTENT QR SCANNER */}
            {deviceType === 'desktop' && upiQrData && (
              <div className="my-5 p-5 bg-gradient-to-b from-slate-50 to-emerald-50/20 rounded-3xl border border-slate-200 text-center flex flex-col items-center">
                <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-100/70 px-2.5 py-0.5 rounded-full mb-3">
                  Desktop Detected • Scan with Phone
                </span>
                <div className="p-3 bg-white rounded-2xl border border-slate-200 shadow-sm inline-block mb-3">
                  <QRCodeSVG
                    value={upiQrData}
                    size={180}
                    level="H"
                    includeMargin
                  />
                </div>
                <h4 className="font-extrabold text-sm text-slate-900">
                  Scan with PhonePe, GPay, Paytm or BHIM
                </h4>
                <p className="text-xs text-slate-500 max-w-xs mt-1">
                  Point your phone's camera or UPI app at this QR code to complete payment of <strong>{currencySymbol}{totalAmountFormatted}</strong>.
                </p>
              </div>
            )}

            {/* Live Polling Status Indicator */}
            <div className="my-4 p-3 rounded-2xl bg-amber-50/90 border border-amber-200 text-amber-900 text-xs flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
                </span>
                <span className="font-semibold">
                  Waiting for payment confirmation from UPI app...
                </span>
              </div>
              <span className="text-[10px] font-mono text-amber-700 bg-amber-100/70 px-2 py-0.5 rounded-full font-bold">
                Live Polling
              </span>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-col gap-2 mt-2">
              {/* Check Status Button */}
              <button
                id="check-payment-status-btn"
                type="button"
                onClick={handleCheckStatus}
                disabled={verifying || loading || timeLeft === 0 || isPaid}
                className="w-full inline-flex items-center justify-center gap-2 py-3 px-5 rounded-2xl font-bold text-xs sm:text-sm text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-200 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {verifying ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin text-emerald-600" />
                    <span>Verifying with PayU Server...</span>
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4 text-slate-500" />
                    <span>Check Payment Status</span>
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
          </>
        )}
      </div>
    </div>
  );
}
