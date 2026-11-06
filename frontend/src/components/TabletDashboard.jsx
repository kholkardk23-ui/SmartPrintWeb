import { useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { getOrders } from "../services/api";
import "./TabletDashboard.css";

const REFRESH_INTERVAL = 3000;
const DEFAULT_CUSTOMER_WEBSITE_URL = "https://smart-print-web-gules.vercel.app/";

function sanitizeCustomerWebsiteUrl(rawUrl) {
  let url = (rawUrl || "").trim();
  if (!url) return DEFAULT_CUSTOMER_WEBSITE_URL;

  if (!/^https?:\/\//i.test(url)) {
    url = `https://${url}`;
  }

  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();

    // Prevent pointing to localhost, backend API, or outdated deployments
    if (
      host === "localhost" ||
      host === "127.0.0.1" ||
      host.includes("onrender.com") ||
      host.includes("smart-print-web-orpin")
    ) {
      return DEFAULT_CUSTOMER_WEBSITE_URL;
    }

    // Strip /tablet if accidentally included
    if (parsed.pathname === "/tablet" || parsed.pathname === "/tablet/") {
      parsed.pathname = "/";
    } else if (parsed.pathname.endsWith("/tablet")) {
      parsed.pathname = parsed.pathname.replace(/\/tablet$/, "/");
    }

    return parsed.toString();
  } catch {
    return DEFAULT_CUSTOMER_WEBSITE_URL;
  }
}

function resolveCustomerWebsiteUrl() {
  const envUrl = import.meta.env.VITE_CUSTOMER_WEBSITE_URL;
  if (envUrl && typeof envUrl === "string" && envUrl.trim() !== "") {
    return sanitizeCustomerWebsiteUrl(envUrl);
  }

  if (typeof window !== "undefined" && window.location?.origin) {
    const origin = window.location.origin;
    if (!origin.includes("localhost") && !origin.includes("127.0.0.1")) {
      return sanitizeCustomerWebsiteUrl(origin);
    }
  }

  return DEFAULT_CUSTOMER_WEBSITE_URL;
}

const CUSTOMER_WEBSITE_URL = resolveCustomerWebsiteUrl();

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

function parseOrderDate(dateValue) {
  if (!dateValue) return 0;
  let s = String(dateValue).trim();
  if (s && !s.endsWith("Z") && !/[+-]\d{2}:\d{2}$/.test(s)) {
    s += "Z";
  }
  const t = Date.parse(s);
  return Number.isNaN(t) ? (Date.parse(dateValue) || 0) : t;
}

function formatDate(dateValue) {
  if (!dateValue) return "Not available";

  const ms = parseOrderDate(dateValue);
  const date = new Date(ms || dateValue);

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
            className={`tablet-connection-dot ${connectionError ? "offline" : "online"
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
  const isPaid = isOrderPaid(order);
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

        <div
          className="tablet-order-badge"
          style={
            isPaid
              ? { background: "#dcfce7", color: "#15803d", borderColor: "#86efac" }
              : { background: "#fef3c7", color: "#b45309", borderColor: "#fcd34d" }
          }
        >
          {isPaid ? "ORDER CONFIRMED" : "PAYMENT PENDING"}
        </div>
      </header>

      <section className="tablet-order-content">
        <div className="tablet-order-heading">
          <div
            className="tablet-success-icon"
            style={
              isPaid
                ? { background: "#10b981", color: "#ffffff" }
                : { background: "#f59e0b", color: "#ffffff" }
            }
          >
            {isPaid ? "✓" : "⏳"}
          </div>

          <div>
            <span
              className="tablet-eyebrow"
              style={!isPaid ? { color: "#b45309" } : undefined}
            >
              {isPaid ? "CONFIRMED PRINT ORDER" : "PRINT ORDER AWAITING PAYMENT"}
            </span>
            <h2>{getOrderNumber(order)}</h2>
            <p>
              {isPaid
                ? "Payment verified. Review the details of your confirmed print order below."
                : "Please complete payment on the customer website. This screen will update automatically once payment is verified."}
            </p>
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
              <strong
                className={`tablet-status ${isPaid ? "status-paid" : "status-pending"}`}
                style={
                  !isPaid
                    ? { background: "#fef3c7", color: "#b45309", border: "1px solid #fcd34d" }
                    : undefined
                }
              >
                {isPaid ? "PAID" : "PAYMENT PENDING"}
              </strong>
            </div>

            <div className="tablet-setting-item">
              <span className="tablet-setting-label">Order Status</span>
              <strong
                className={`tablet-status ${isPaid ? "status-confirmed" : "status-created"}`}
                style={
                  !isPaid
                    ? { background: "#eff6ff", color: "#1d4ed8", border: "1px solid #bfdbfe" }
                    : undefined
                }
              >
                {isPaid ? "CONFIRMED" : "AWAITING PAYMENT"}
              </strong>
            </div>

            {isPaid && order?.payment_reference && (
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

        <div
          className="tablet-order-message"
          style={!isPaid ? { borderColor: "#fcd34d", background: "#fffbeb" } : undefined}
        >
          <span className="tablet-message-icon">{isPaid ? "ℹ️" : "⏳"}</span>

          <p>
            {isPaid
              ? "Payment verified. Please collect your documents when printing is complete."
              : "Please complete payment on the customer website. This tablet screen will update automatically once payment is verified."}
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
        const dateA = parseOrderDate(a?.created_at);
        const dateB = parseOrderDate(b?.created_at);

        if (dateA && dateB && dateA !== dateB) return dateB - dateA;

        return String(b?.order_number ?? b?.id ?? "").localeCompare(
          String(a?.order_number ?? a?.id ?? ""),
          undefined,
          { numeric: true, sensitivity: "base" }
        );
      });

      setConnectionError(false);
      setLastUpdated(new Date().toISOString());

      // Helper to identify active pending orders awaiting payment
      const isPendingOrder = (o) => {
        if (!o || isOrderPaid(o)) return false;
        const status = String(o?.status ?? "").toUpperCase();
        const paymentStatus = String(o?.payment_status ?? "").toUpperCase();
        if (["FAILED", "CANCELLED"].includes(status) || ["FAILED", "CANCELLED"].includes(paymentStatus)) {
          return false;
        }
        return ["PAYMENT_PENDING", "CREATED", "OPTIONS_SELECTED"].includes(status);
      };

      const confirmedOrders = sortedOrders.filter(isOrderPaid);
      const pendingOrders = sortedOrders.filter(isPendingOrder);

      // On first load, display latest active pending or confirmed paid order
      if (!initialized.current) {
        initialized.current = true;

        const latestOrder = sortedOrders.find((o) => {
          const id = getOrderId(o);
          return (
            id &&
            !dismissedOrderIds.current.has(id) &&
            (isPendingOrder(o) || isOrderPaid(o))
          );
        });

        if (latestOrder) {
          activeOrderKey.current = getOrderKey(latestOrder);
          setActiveOrder(latestOrder);
        }
        return;
      }

      // If already viewing an order, update live
      if (activeOrderRef.current) {
        const activeId = getOrderId(activeOrderRef.current);
        const currentIsPaid = isOrderPaid(activeOrderRef.current);

        // Find current order in freshly polled orders
        const matchingCurrent = sortedOrders.find((o) => getOrderId(o) === activeId);

        if (matchingCurrent) {
          // If viewing a pending order and it just became paid, transition to OrderDetails!
          if (!currentIsPaid && isOrderPaid(matchingCurrent)) {
            activeOrderKey.current = getOrderKey(matchingCurrent);
            setActiveOrder(matchingCurrent);
            return;
          }

          // If pending order was failed or cancelled, dismiss it
          const status = String(matchingCurrent?.status ?? "").toUpperCase();
          const paymentStatus = String(matchingCurrent?.payment_status ?? "").toUpperCase();
          if (["FAILED", "CANCELLED"].includes(status) || ["FAILED", "CANCELLED"].includes(paymentStatus)) {
            activeOrderKey.current = null;
            setActiveOrder(null);
            return;
          }

          // Update active order live
          setActiveOrder(matchingCurrent);
        }

        // Check if a newer confirmed paid order arrived
        const newestConfirmed = confirmedOrders[0];
        if (
          newestConfirmed &&
          getOrderId(newestConfirmed) !== activeId &&
          !dismissedOrderIds.current.has(getOrderId(newestConfirmed))
        ) {
          const createdAtNew = parseOrderDate(newestConfirmed?.created_at);
          const createdAtActive = parseOrderDate(activeOrderRef.current?.created_at);
          if (createdAtNew >= createdAtActive) {
            activeOrderKey.current = getOrderKey(newestConfirmed);
            setActiveOrder(newestConfirmed);
            return;
          }
        }

        // If viewing a confirmed order, check if a new customer created a new pending order
        if (currentIsPaid) {
          const newestPending = pendingOrders[0];
          if (
            newestPending &&
            getOrderId(newestPending) !== activeId &&
            !dismissedOrderIds.current.has(getOrderId(newestPending))
          ) {
            const createdAtPending = parseOrderDate(newestPending?.created_at);
            const createdAtActive = parseOrderDate(activeOrderRef.current?.created_at);
            if (createdAtPending > createdAtActive) {
              activeOrderKey.current = getOrderKey(newestPending);
              setActiveOrder(newestPending);
              return;
            }
          }
        }
      } else {
        // On Welcome Screen:
        // Priority 1: Check if a customer created a pending order requiring payment
        const newestPending = pendingOrders.find((o) => {
          const id = getOrderId(o);
          return id && !dismissedOrderIds.current.has(id);
        });

        // Priority 2: Check for newest confirmed paid order
        const newestConfirmed = confirmedOrders.find((o) => {
          const id = getOrderId(o);
          return id && !dismissedOrderIds.current.has(id);
        });

        if (newestPending && newestConfirmed) {
          const datePending = parseOrderDate(newestPending?.created_at);
          const dateConfirmed = parseOrderDate(newestConfirmed?.created_at);
          if (datePending >= dateConfirmed) {
            activeOrderKey.current = getOrderKey(newestPending);
            setActiveOrder(newestPending);
          } else {
            activeOrderKey.current = getOrderKey(newestConfirmed);
            setActiveOrder(newestConfirmed);
          }
        } else if (newestPending) {
          activeOrderKey.current = getOrderKey(newestPending);
          setActiveOrder(newestPending);
        } else if (newestConfirmed) {
          activeOrderKey.current = getOrderKey(newestConfirmed);
          setActiveOrder(newestConfirmed);
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
    return <OrderDetails order={activeOrder} onHome={handleHome} />;
  }

  return (
    <WelcomeScreen
      lastUpdated={lastUpdated}
      connectionError={connectionError}
    />
  );
}