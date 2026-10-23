import { useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { getOrders } from "../services/api";
import "./TabletDashboard.css";

const REFRESH_INTERVAL = 3000;
const CUSTOMER_WEBSITE_URL = "https://smart-print-web-orpin.vercel.app/";

function getOrderKey(order) {
  return String(
    order?.id ??
      order?.order_number ??
      order?.created_at ??
      `${order?.total_amount ?? ""}-${order?.status ?? ""}`
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

        <div className="tablet-order-badge">
          ORDER RECEIVED
        </div>
      </header>

      <section className="tablet-order-content">
        <div className="tablet-order-heading">
          <div className="tablet-success-icon">✓</div>

          <div>
            <span className="tablet-eyebrow">NEW PRINT ORDER</span>
            <h2>{getOrderNumber(order)}</h2>
            <p>Review the details of your print order below.</p>
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
              <span>Pages</span>
              <strong>{getPageCount(order)}</strong>
            </div>

            <div className="tablet-detail-row">
              <span>Copies</span>
              <strong>{getCopies(order)}</strong>
            </div>
          </section>

          <section className="tablet-info-card">
            <h3>⚙️ Print settings</h3>

            <div className="tablet-setting-item">
              <span className="tablet-setting-label">Colour mode</span>
              <strong>{getColorMode(order)}</strong>
            </div>

            <div className="tablet-setting-item">
              <span className="tablet-setting-label">Print sides</span>
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
              <span className="tablet-setting-label">Order time</span>
              <strong>{formatDate(order.created_at)}</strong>
            </div>

            <div className="tablet-setting-item">
              <span className="tablet-setting-label">Order status</span>
              <strong
                className={`tablet-status status-${getStatusClass(order)}`}
              >
                {getStatus(order)}
              </strong>
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

export default function TabletDashboard() {
  const [activeOrder, setActiveOrder] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [connectionError, setConnectionError] = useState(false);

  const seenOrderKeys = useRef(new Set());
  const initialized = useRef(false);
  const activeOrderKey = useRef(null);
  const dismissedOrderKeys = useRef(new Set());
  const pollingInProgress = useRef(false);

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

      // On first load, remember old orders but show the newest order if it
      // was created recently. This also handles opening/reloading the tablet
      // shortly after the customer confirms an order.
      if (!initialized.current) {
        sortedOrders.forEach((order) => {
          seenOrderKeys.current.add(getOrderKey(order));
        });

        initialized.current = true;

        const newestOrder = sortedOrders[0];
        const createdAt = Date.parse(newestOrder?.created_at ?? "");
        const isRecent =
          Number.isFinite(createdAt) &&
          createdAt > 0 &&
          Date.now() - createdAt <= 10 * 60 * 1000 &&
          createdAt <= Date.now() + 60 * 1000;

        if (
          newestOrder &&
          isRecent &&
          !dismissedOrderKeys.current.has(getOrderKey(newestOrder))
        ) {
          const key = getOrderKey(newestOrder);
          activeOrderKey.current = key;
          setActiveOrder(newestOrder);
        }

        return;
      }

      // Find orders that appeared after the previous poll.
      const newOrders = sortedOrders.filter((order) => {
        const key = getOrderKey(order);

        return (
          !seenOrderKeys.current.has(key) &&
          !dismissedOrderKeys.current.has(key)
        );
      });

      // Mark returned orders as seen to avoid repeatedly triggering them.
      sortedOrders.forEach((order) => {
        seenOrderKeys.current.add(getOrderKey(order));
      });

      // Display the newest newly-created order if the tablet is on Home.
      if (newOrders.length > 0 && !activeOrderKey.current) {
        const newestOrder = newOrders[0];
        activeOrderKey.current = getOrderKey(newestOrder);
        setActiveOrder(newestOrder);
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

  const handleHome = useCallback(() => {
    if (activeOrderKey.current) {
      dismissedOrderKeys.current.add(activeOrderKey.current);
    }

    activeOrderKey.current = null;
    setActiveOrder(null);
  }, []);

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