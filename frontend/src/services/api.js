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
    ? `/files/upload/${sessionId}`
    : "/files/upload";

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
    ? `/files/upload-multiple/${sessionId}`
    : "/files/upload-multiple";

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

    // Support different backend response formats
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

  const response = await api.post("/orders", orderData);

  return response.data;
};

// Get all orders
export const getOrders = async () => {
  const response = await api.get("/orders");

  return response.data;
};

// Get single order
export const getOrder = async (orderId) => {
  const response = await api.get(`/orders/${orderId}`);

  return response.data;
};

// Backend health check
export const healthCheck = async () => {
  const response = await api.get("/health");

  return response.data;
};

// Compatibility alias used by the old polished App.jsx
export const checkHealth = healthCheck;

// Default API object
const apiService = {
  uploadFile,
  uploadMultipleFiles,
  uploadDocuments,
  createOrder,
  getOrders,
  getOrder,
  healthCheck,
  checkHealth,
};

export default apiService;