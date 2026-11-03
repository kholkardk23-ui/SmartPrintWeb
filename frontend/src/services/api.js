import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  timeout: 60000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Upload one PDF
export const uploadFile = async (file, sessionId = null) => {
  const formData = new FormData();
  formData.append("file", file);

  const url = sessionId
    ? `/api/files/upload/${sessionId}`
    : "/api/files/upload";

  const response = await api.post(url, formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  return response.data;
};

// Upload multiple PDFs
export const uploadMultipleFiles = async (files, sessionId = null) => {
  const formData = new FormData();

  files.forEach((file) => {
    formData.append("files", file);
  });

  const url = sessionId
    ? `/api/files/upload-multiple/${sessionId}`
    : "/api/files/upload-multiple";

  const response = await api.post(url, formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  return response.data;
};

// Compatibility function for the previous SmartPrint design
export const uploadDocuments = async (files, onProgress = null) => {
  try {
    const result = await uploadMultipleFiles(files);

    let uploadedFiles = [];

    if (Array.isArray(result)) {
      uploadedFiles = result;
    } else if (Array.isArray(result?.files)) {
      uploadedFiles = result.files;
    } else if (Array.isArray(result?.data)) {
      uploadedFiles = result.data;
    } else if (result) {
      uploadedFiles = [result];
    }

    if (onProgress) {
      onProgress(100);
    }

    return uploadedFiles;
  } catch (error) {
    throw error;
  }
};

// Create order
export const createOrder = async (orderData) => {
  console.log("Sending order data:", orderData);

  const response = await api.post("/api/orders", orderData);

  return response.data;
};

// Get all orders — newest order number first
export const getOrders = async () => {
  const response = await api.get("/api/orders");

  const orders = response.data;

  if (!Array.isArray(orders)) {
    return orders;
  }

  return [...orders].sort((a, b) => {
    const orderA = a.order_number || "";
    const orderB = b.order_number || "";

    return orderB.localeCompare(orderA, undefined, {
      numeric: true,
      sensitivity: "base",
    });
  });
};

// Get single order
export const getOrder = async (orderId) => {
  const response = await api.get(`/api/orders/${orderId}`);

  return response.data;
};

// Update order status (e.g. PRINTING, COMPLETED)
export const updateOrderStatus = async (orderId, status) => {
  const response = await api.patch(`/api/orders/${orderId}/status`, { status });
  return response.data;
};

// Backend health check
export const healthCheck = async () => {
  const response = await api.get("/api/health");

  return response.data;
};

// Compatibility alias used by the old polished App.jsx
export const checkHealth = healthCheck;

// Start Dynamic UPI payment for order
export const startPayment = async (orderId) => {
  const response = await api.post(`/api/payments/${orderId}/start`);
  return response.data;
};

// Generate/Get PayU Dynamic QR for order (used by tablet payment display)
export const getPayUQR = async (orderId) => {
  const response = await api.post(`/api/payments/${orderId}/qr`);
  return response.data;
};

// Create automatic checkout session (PayU / YouPI / Razorpay / Cashfree / Demo)
export const createCheckout = async (orderId, provider = null) => {
  const url = provider
    ? `/api/payments/${orderId}/checkout?provider=${provider}`
    : `/api/payments/${orderId}/checkout`;
  const response = await api.post(url);
  return response.data;
};

// Verify payment for order (supports UTR string or Razorpay signature object)
export const verifyPayment = async (orderId, paymentReference = null) => {
  let payload = {};
  if (paymentReference && typeof paymentReference === "object") {
    payload = paymentReference;
  } else if (paymentReference) {
    payload = { payment_reference: paymentReference };
  }
  const response = await api.post(`/api/payments/${orderId}/verify`, payload);
  return response.data;
};

// Verify PayU payment response directly
export const verifyPayUPayment = async (orderId, payuData) => {
  const response = await api.post(`/api/payments/${orderId}/verify-payu`, payuData);
  return response.data;
};

// Verify Razorpay payment signature directly
export const verifyRazorpayPayment = async (orderId, razorpayData) => {
  const response = await api.post(`/api/payments/${orderId}/verify-razorpay`, razorpayData);
  return response.data;
};

// Get payment status for polling
export const getPaymentStatus = async (orderId) => {
  const response = await api.get(`/api/payments/${orderId}/status`);
  return response.data;
};

// Default API object
const apiService = {
  uploadFile,
  uploadMultipleFiles,
  uploadDocuments,
  createOrder,
  getOrders,
  getOrder,
  updateOrderStatus,
  healthCheck,
  checkHealth,
  startPayment,
  getPayUQR,
  createCheckout,
  verifyPayment,
  verifyPayUPayment,
  verifyRazorpayPayment,
  getPaymentStatus,
};

export default apiService;
