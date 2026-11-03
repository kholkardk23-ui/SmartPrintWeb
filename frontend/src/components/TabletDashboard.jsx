import { useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import {
  getOrders,
  startPayment,
  getPayUQR,
  verifyPayment,
  getPaymentStatus,
} from "../services/api";
import "./TabletDashboard.css";

const REFRESH_INTERVAL = 3000;
const CUSTOMER_WEBSITE_URL =
  import.meta.env.VITE_CUSTOMER_WEBSITE_URL ||
  "https://smart-print-web-orpin.vercel.app/";

function getOrderKey(order) {
  const id = order?.id || order?.order_number || order?.order_id || "order";
  const status = order?.status || "UNKNOWN";
  return `${id}__${status}`;
}

function getOrderId(order) {
  return String(order?.order_number ?? order?.order_id ?? order?.id ?? "");
}

function isOrderPaid(order) {
  if (!order) return false;
  const status = String(order?.status ?? "").toUpperCase();
  const paymentStatus = String(order?.payment_status ?? "").toUpperCase();
  return (
    ["CONFIRMED", "PAID", "QUEUED", "PRINTING", "COMPLETED"].includes(status) ||
    paymentStatus === "PAID" ||
    paymentStatus === "SUCCESS" ||
    Boolean(order?.is_paid)
  );
}

function formatAmount(amount) {
  const value = Number(amount ?? 0);

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(Number.isFinite(value) ? value : 0);
}

function formatDate(dateValue) {
  if (!dateValue) return "Not available";

  const date = new Date(dateValue);

  if (Number.isNaN(date.getTime())) {
    return String(dateValue);
  }

  return date.toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function getOrderNumber(order) {
  return (
    order?.order_number ??
    order?.order_id ??
    (order?.id ? `SP-${String(order.id).slice(0, 8)}` : "Order")
  );
}

function getFileNames(order) {
  const possibleArrays = [
    order?.files,
    order?.documents,
    order?.items,
  ];

  for (const list of possibleArrays) {
    if (Array.isArray(list) && list.length > 0) {
      return list.map((file, index) => {
        if (typeof file === "string") return file;

        return (
          file?.filename ??
          file?.file_name ??
          file?.original_filename ??
          file?.name ??
          `Document ${index + 1}`
        );
      });
    }
  }

  const singleFile =
    order?.filename ??
    order?.file_name ??
    order?.original_filename ??
    order?.file?.filename ??
    order?.file?.file_name;

  if (singleFile) return [singleFile];

  if (order?.file_id) {
    return [`Uploaded PDF (${order.file_id})`];
  }

  return ["Document details unavailable"];
}

function getCopies(order) {
  return order?.copies ?? 1;
}

function getColorMode(order) {
  const mode = String(
    order?.color_mode ?? order?.colour_mode ?? "bw"
  ).toLowerCase();

  if (
    mode.includes("color") ||
    mode.includes("colour") ||
    mode === "colour"
  ) {
    return "Colour";
  }

  return "Black & White";
}

function getPrintSides(order) {
  if (typeof order?.duplex === "boolean") {
    return order.duplex ? "Back-to-back (Duplex)" : "Single-sided";
  }

  const value = String(order?.duplex ?? "").toLowerCase();

  if (["true", "1", "yes", "duplex", "double-sided"].includes(value)) {
    return "Back-to-back (Duplex)";
  }

  if (["false", "0", "no", "simplex", "single-sided"].includes(value)) {
    return "Single-sided";
  }

  return order?.print_sides ?? order?.sides ?? "Not specified";
}

function getPageCount(order) {
  return (
    order?.selected_page_count ??
    order?.page_count ??
    order?.total_pages ??
    "Not specified"
  );
}

function getStatus(order) {
  return String(order?.status ?? "CREATED").replaceAll("_", " ");
}

function getStatusClass(order) {
  return String(order?.status ?? "created")
    .toLowerCase()
    .replaceAll("_", "-");
}

function WelcomeScreen({ lastUpdated, connectionError }) {
  return (
    <main className="tablet-dashboard tablet-welcome">
      {/* Header */}
      <header className="tablet-header">
        <div className="tablet-brand">
          <div className="tablet-brand-icon">🖨️</div>

          <div>
            <h1>SmartPrint</h1>
            <p>Print Smart. Print Simple.</p>
          </div>
        </div>

        <div className="tablet-connection">
          <span
            className={`tablet-connection-dot ${
              connectionError ? "offline" : "online"
            }`}
          />
          {connectionError ? "Connection issue" : "System ready"}
        </div>
      </header>

      {/* Main Welcome Content */}
      <section className="tablet-welcome-content">
        {/* Instructions */}
        <div className="tablet-welcome-text">
          <span className="tablet-eyebrow">SELF-SERVICE PRINTING</span>

          <h2>
            Your documents.
            <br />
            <span>Printed simply.</span>
          </h2>

          <p>
            Scan the QR code with your phone to upload your PDF,
            choose your print settings, and place your order.
          </p>

          {/* Steps */}
          <div className="tablet-steps">
            <div className="tablet-step">
              <span>1</span>
              <div>
                <strong>Scan QR code</strong>
                <small>Open SmartPrint on your phone</small>
              </div>
            </div>

            <div className="tablet-step">
              <span>2</span>
              <div>
                <strong>Upload your PDF</strong>
                <small>Select documents and print options</small>
              </div>
            </div>

            <div className="tablet-step">
              <span>3</span>
              <div>
                <strong>Pay and print</strong>
                <small>Follow the order status on this tablet</small>
              </div>
            </div>
          </div>
        </div>

        {/* QR Code Card */}
        <div className="tablet-qr-card">
          <div className="tablet-qr-heading">SCAN TO GET STARTED</div>

          <div className="tablet-qr-code">
            <QRCodeSVG
              value={CUSTOMER_WEBSITE_URL}
              size={260}
              level="H"
              includeMargin
              title="Scan to open SmartPrint"
            />
          </div>

          <h3>Scan with your phone</h3>
          <p>Open your camera and point it at the QR code.</p>
        </div>
      </section>

      {/* Footer and Project Team */}
      <footer className="tablet-footer tablet-welcome-footer">
        <div className="tablet-footer-status">
          <span>SmartPrint Self-Service Machine</span>

          <span>
            {lastUpdated
              ? `Last checked: ${formatDate(lastUpdated)}`
              : "Connecting to server..."}
          </span>
        </div>

        <div className="tablet-group-members">
          <span className="tablet-members-title">PROJECT TEAM</span>
          <span>Darshan Kholkar</span>
          <span>Harshavardhan Chavan</span>
          <span>Pradip Biradar</span>
          <span>Rajveer Sahare</span>
        </div>
      </footer>

      {/* Connection Warning */}
      {connectionError && (
        <div className="tablet-connection-warning" role="status">
          Unable to refresh orders. Retrying automatically...
        </div>
      )}
    </main>
  );
}


function OrderDetails({ order, onHome }) {
  const fileNames = getFileNames(order);

  return (
    <main className="tablet-dashboard tablet-order-screen">
      <header className="tablet-header">
        <div className="tablet-brand">
          <div className="tablet-brand-icon">🖨️</div>

          <div>
            <h1>SmartPrint</h1>
            <p>Print Smart. Print Simple.</p>
          </div>
        </div>

        <div className="tablet-order-badge" style={{ background: "#dcfce7", color: "#15803d", borderColor: "#86efac" }}>
          ORDER CONFIRMED
        </div>
      </header>

      <section className="tablet-order-content">
        <div className="tablet-order-heading">
          <div className="tablet-success-icon">✓</div>

          <div>
            <span className="tablet-eyebrow">CONFIRMED PRINT ORDER</span>
            <h2>{getOrderNumber(order)}</h2>
            <p>Review the details of your confirmed print order below.</p>
          </div>
        </div>

        <div className="tablet-order-grid">
          <section className="tablet-info-card tablet-documents-card">
            <h3>📄 Documents</h3>

            <div className="tablet-document-list">
              {fileNames.map((name, index) => (
                <div
                  className="tablet-document-row"
                  key={`${name}-${index}`}
                >
                  <span className="tablet-document-icon">PDF</span>

                  <div className="tablet-document-name">
                    <strong>{name}</strong>
                    <small>Document {index + 1}</small>
                  </div>
                </div>
              ))}
            </div>

            <div className="tablet-detail-divider" />

            <div className="tablet-detail-row">
              <span>Total Pages</span>
              <strong>{getPageCount(order)}</strong>
            </div>

            <div className="tablet-detail-row">
              <span>Number of Copies</span>
              <strong>{getCopies(order)}</strong>
            </div>
          </section>

          <section className="tablet-info-card">
            <h3>⚙️ Print Settings & Verification</h3>

            <div className="tablet-setting-item">
              <span className="tablet-setting-label">Order Number</span>
              <strong style={{ fontFamily: "monospace", letterSpacing: "0.5px" }}>{getOrderNumber(order)}</strong>
            </div>

            <div className="tablet-setting-item">
              <span className="tablet-setting-label">Print Type</span>
              <strong>{getColorMode(order)}</strong>
            </div>

            <div className="tablet-setting-item">
              <span className="tablet-setting-label">Double-sided or Single-sided</span>
              <strong>{getPrintSides(order)}</strong>
            </div>

            {order?.page_range && (
              <div className="tablet-setting-item">
                <span className="tablet-setting-label">Page range</span>
                <strong>{order.page_range}</strong>
              </div>
            )}

            <div className="tablet-detail-divider" />

            <div className="tablet-setting-item">
              <span className="tablet-setting-label">Payment Status</span>
              <strong className="tablet-status status-paid">
                PAID
              </strong>
            </div>

            <div className="tablet-setting-item">
              <span className="tablet-setting-label">Order Status</span>
              <strong className="tablet-status status-confirmed">
                CONFIRMED
              </strong>
            </div>

            {order?.payment_reference && (
              <div className="tablet-setting-item">
                <span className="tablet-setting-label">Transaction Ref</span>
                <strong style={{ fontFamily: "monospace", fontSize: "12px" }}>{order.payment_reference}</strong>
              </div>
            )}

            <div className="tablet-setting-item">
              <span className="tablet-setting-label">Order Time</span>
              <strong>{formatDate(order.created_at)}</strong>
            </div>
          </section>
        </div>

        <section className="tablet-total-card">
          <div>
            <span className="tablet-total-label">TOTAL PRINT AMOUNT</span>
            <p>Amount for this order</p>
          </div>

          <strong className="tablet-total-amount">
            {formatAmount(order.total_amount)}
          </strong>
        </section>

        <div className="tablet-order-message">
          <span className="tablet-message-icon">ℹ️</span>

          <p>
            Please follow the payment and printing instructions shown
            by the SmartPrint system. Collect your documents when
            printing is complete.
          </p>
        </div>

        <button
          type="button"
          className="tablet-home-button"
          onClick={onHome}
        >
          ← HOME / READY FOR NEXT CUSTOMER
        </button>
      </section>

      <footer className="tablet-footer">
        <span>SmartPrint Self-Service Machine</span>
        <span>{getOrderNumber(order)}</span>
      </footer>
    </main>
  );
}

function TabletPaymentView({ order, onPaymentSuccess, onHome }) {
  const [paymentData, setPaymentData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  const orderIdentifier = order?.order_id || order?.id || order?.order_number;
  const pollingRef = useRef(null);

  // Initialize payment details
  useEffect(() => {
    let active = true;

    async function init() {
      if (!orderIdentifier) return;
      setLoading(true);
      try {
        // Fetch official PayU dynamic payment QR for this order
        const data = await getPayUQR(orderIdentifier);
        if (!active) return;
        setPaymentData(data);
        if (
          data.payment_status === "PAID" ||
          data.payment_status === "SUCCESS" ||
          data.is_paid ||
          data.status === "CONFIRMED" ||
          data.status === "PAID" ||
          data.status === "PRINTING" ||
          data.status === "COMPLETED"
        ) {
          onPaymentSuccess({ ...order, ...data, status: "CONFIRMED", payment_status: "PAID" });
        }
      } catch (err) {
        console.warn("PayU getPayUQR notice, trying startPayment:", err);
        try {
          const fallbackData = await startPayment(orderIdentifier);
          if (active) setPaymentData(fallbackData);
        } catch (e) {
          console.error("Payment QR init error:", e);
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    init();

    return () => {
      active = false;
    };
  }, [orderIdentifier, order, onPaymentSuccess]);

  // Real-time polling to detect payment verification from phone
  useEffect(() => {
    if (!orderIdentifier) return;

    pollingRef.current = setInterval(async () => {
      try {
        const statusRes = await getPaymentStatus(orderIdentifier);
        if (
          statusRes &&
          (statusRes.is_paid ||
            statusRes.status === "CONFIRMED" ||
            statusRes.status === "PAID" ||
            statusRes.status === "PRINTING" ||
            statusRes.status === "COMPLETED" ||
            statusRes.payment_status === "PAID" ||
            statusRes.payment_status === "SUCCESS")
        ) {
          clearInterval(pollingRef.current);
          onPaymentSuccess({ ...order, ...statusRes, status: "CONFIRMED", payment_status: "PAID" });
        }
      } catch (e) {
        // silent polling error
      }
    }, 2000);

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [orderIdentifier, order, onPaymentSuccess]);

  // Simulate payment for quick testing on kiosk
  const handleSimulatePayment = async () => {
    if (verifying || !orderIdentifier) return;
    setVerifying(true);
    setErrorMessage(null);
    try {
      const result = await verifyPayment(
        orderIdentifier,
        `DEMO-PAID-${Date.now()}`
      );
      if (pollingRef.current) clearInterval(pollingRef.current);
      onPaymentSuccess({ ...order, ...result, status: "PRINTING" });
    } catch (err) {
      console.error("Simulation failed:", err);
      setErrorMessage("Verification failed. Please try again.");
    } finally {
      setVerifying(false);
    }
  };

  const dynamicUpiUri =
    paymentData?.upi_uri ||
    paymentData?.qr_data ||
    `upi://pay?pa=9823555453@kotakbank&pn=SmartPrint%20Kiosk&am=${Number(
      order?.total_amount || 0
    ).toFixed(2)}&cu=INR&tn=${encodeURIComponent(
      `SmartPrint ${getOrderNumber(order)}`
    )}&tr=${getOrderNumber(order)}`;

  return (
    <main className="tablet-dashboard tablet-upi-screen">
      <header className="tablet-header">
        <div className="tablet-brand">
          <div className="tablet-brand-icon">🖨️</div>
          <div>
            <h1>SmartPrint</h1>
            <p>Print Smart. Print Simple.</p>
          </div>
        </div>

        <div className="tablet-order-badge tablet-payment-badge">
          SMARTPRINT PAYMENT
        </div>
      </header>

      <div className="tablet-upi-container">
        {/* Amount Display */}
        <div className="tablet-upi-amount-card">
          <span className="tablet-upi-order-tag">Order: {getOrderNumber(order)}</span>
          <h2 className="tablet-upi-amount-value">
            Amount: {formatAmount(order?.total_amount)}
          </h2>
          <span className="tablet-upi-amount-label">
            PayU India • Secure UPI Payment
          </span>
        </div>

        {/* Scanner Card */}
        <div className="tablet-upi-qr-card">
          <div className="tablet-upi-qr-frame">
            {loading ? (
              <div style={{ padding: "40px", color: "var(--sp-muted)", fontSize: "14px" }}>
                Generating Scanner...
              </div>
            ) : (
              <QRCodeSVG
                value={dynamicUpiUri}
                size={210}
                level="H"
                includeMargin
                imageSettings={{
                  src: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="%232563eb" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/></svg>',
                  height: 28,
                  width: 28,
                  excavate: true,
                }}
              />
            )}
          </div>

          <span className="tablet-upi-qr-prompt">
            Scan using your UPI App
          </span>

          <div className="tablet-upi-apps">
            {["GPay", "PhonePe", "Paytm", "BHIM"].map((app) => (
              <span key={app} className="tablet-upi-app-pill">
                {app}
              </span>
            ))}
          </div>
        </div>

        {/* Live Status Hint */}
        <div className="tablet-upi-status-hint">
          <span className="tablet-upi-pulse-dot" />
          <span>Waiting for payment...</span>
        </div>

        {errorMessage && (
          <div style={{ color: "#b91c1c", fontSize: "12px", fontWeight: "600" }}>
            {errorMessage}
          </div>
        )}

        {/* Quick Actions (Simulate & Cancel) */}
        <div className="tablet-upi-actions">
          <button
            type="button"
            className="tablet-upi-simulate-btn"
            onClick={handleSimulatePayment}
            disabled={verifying}
          >
            {verifying ? "Verifying..." : "⚡ Quick Test: Simulate Payment"}
          </button>

          <button
            type="button"
            className="tablet-upi-cancel-btn"
            onClick={onHome}
            disabled={verifying}
          >
            ← Cancel
          </button>
        </div>
      </div>

      <footer className="tablet-footer">
        <span>SmartPrint Self-Service Machine</span>
        <span>{getOrderNumber(order)}</span>
      </footer>
    </main>
  );
}

export default function TabletDashboard() {
  const [activeOrder, setActiveOrder] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [connectionError, setConnectionError] = useState(false);

  const seenOrderKeys = useRef(new Set());
  const initialized = useRef(false);
  const activeOrderKey = useRef(null);
  const dismissedOrderKeys = useRef(new Set());
  const dismissedOrderIds = useRef(new Set());
  const activeOrderRef = useRef(null);
  const pollingInProgress = useRef(false);

  useEffect(() => {
    activeOrderRef.current = activeOrder;
  }, [activeOrder]);

  const handlePaymentSuccess = useCallback((paidOrder) => {
    if (paidOrder) {
      activeOrderKey.current = getOrderKey(paidOrder);
      setActiveOrder(paidOrder);
    }
  }, []);

  const handleHome = useCallback(() => {
    if (activeOrderRef.current) {
      const orderId = getOrderId(activeOrderRef.current);
      if (orderId) {
        dismissedOrderIds.current.add(orderId);
      }
    }
    if (activeOrderKey.current) {
      dismissedOrderKeys.current.add(activeOrderKey.current);
    }

    activeOrderKey.current = null;
    setActiveOrder(null);
  }, []);

  const fetchOrders = useCallback(async () => {
    if (pollingInProgress.current) return;

    pollingInProgress.current = true;

    try {
      const response = await getOrders();

      // Support an array, { orders: [...] }, or Axios-style { data: [...] }.
      const orders = Array.isArray(response)
        ? response
        : Array.isArray(response?.orders)
          ? response.orders
          : Array.isArray(response?.data)
            ? response.data
            : [];

      // getOrders() normally sorts order_number descending, but sort by
      // creation time when available so the newest order is considered first.
      const sortedOrders = [...orders].sort((a, b) => {
        const dateA = Date.parse(a?.created_at ?? "") || 0;
        const dateB = Date.parse(b?.created_at ?? "") || 0;

        if (dateA && dateB && dateA !== dateB) return dateB - dateA;

        return String(b?.order_number ?? b?.id ?? "").localeCompare(
          String(a?.order_number ?? a?.id ?? ""),
          undefined,
          { numeric: true, sensitivity: "base" }
        );
      });

      setConnectionError(false);
      setLastUpdated(new Date().toISOString());

      // Filter confirmed/paid orders and pending payment orders for tablet kiosk
      const confirmedOrders = sortedOrders.filter(isOrderPaid);
      const pendingOrders = sortedOrders.filter(
        (o) =>
          !isOrderPaid(o) &&
          ["PAYMENT_PENDING", "OPTIONS_SELECTED", "CREATED"].includes(
            String(o?.status || "").toUpperCase()
          )
      );

      // On first load, display latest pending order or confirmed order if not dismissed
      if (!initialized.current) {
        sortedOrders.forEach((order) => {
          seenOrderKeys.current.add(getOrderKey(order));
        });

        initialized.current = true;

        const targetOrder = pendingOrders[0] || confirmedOrders[0];
        if (targetOrder) {
          const targetId = getOrderId(targetOrder);
          const targetKey = getOrderKey(targetOrder);
          if (
            !dismissedOrderIds.current.has(targetId) &&
            !dismissedOrderKeys.current.has(targetKey)
          ) {
            activeOrderKey.current = targetKey;
            setActiveOrder(targetOrder);
          }
        }
        return;
      }

      // If already viewing an order, update its details live
      if (activeOrderRef.current) {
        const activeId = getOrderId(activeOrderRef.current);
        const updated = sortedOrders.find((o) => getOrderId(o) === activeId);
        if (updated) {
          setActiveOrder(updated);
        }

        // If the current order is paid, check if a newer pending order arrived for payment
        if (isOrderPaid(activeOrderRef.current)) {
          const newestPending = pendingOrders[0];
          if (
            newestPending &&
            getOrderId(newestPending) !== activeId &&
            !dismissedOrderIds.current.has(getOrderId(newestPending))
          ) {
            activeOrderKey.current = getOrderKey(newestPending);
            setActiveOrder(newestPending);
          }
        }
      } else {
        // On Welcome Screen: Prioritize any pending order waiting for payment
        const newestPending = pendingOrders[0];
        if (
          newestPending &&
          !dismissedOrderIds.current.has(getOrderId(newestPending))
        ) {
          activeOrderKey.current = getOrderKey(newestPending);
          setActiveOrder(newestPending);
        } else {
          // Otherwise display latest confirmed order if not dismissed
          const newestConfirmed = confirmedOrders[0];
          if (
            newestConfirmed &&
            !dismissedOrderIds.current.has(getOrderId(newestConfirmed))
          ) {
            activeOrderKey.current = getOrderKey(newestConfirmed);
            setActiveOrder(newestConfirmed);
          }
        }
      }
    } catch (error) {
      console.error("Tablet dashboard polling error:", error);
      setConnectionError(true);
    } finally {
      pollingInProgress.current = false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timerId;

    const poll = async () => {
      if (cancelled) return;

      await fetchOrders();

      if (!cancelled) {
        timerId = window.setTimeout(poll, REFRESH_INTERVAL);
      }
    };

    poll();

    return () => {
      cancelled = true;

      if (timerId) {
        window.clearTimeout(timerId);
      }
    };
  }, [fetchOrders]);

  if (activeOrder) {
    if (!isOrderPaid(activeOrder)) {
      return (
        <TabletPaymentView
          order={activeOrder}
          onPaymentSuccess={handlePaymentSuccess}
          onHome={handleHome}
        />
      );
    }

    return <OrderDetails order={activeOrder} onHome={handleHome} />;
  }

  return (
    <WelcomeScreen
      lastUpdated={lastUpdated}
      connectionError={connectionError}
    />
  );
}