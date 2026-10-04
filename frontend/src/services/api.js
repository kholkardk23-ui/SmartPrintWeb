import axios from 'axios';

const API_BASE_URL =
  import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
});

// ============================================================
// HEALTH
// ============================================================

export const checkHealth = async () => {
  const response = await api.get('/health');
  return response.data;
};

// ============================================================
// SINGLE FILE UPLOAD
// ============================================================

export const uploadFile = async (file, onProgress) => {
  const formData = new FormData();

  formData.append('file', file);

  const response = await api.post('/files/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },

    onUploadProgress: (progressEvent) => {
      if (!onProgress || !progressEvent.total) return;

      const percent = Math.round(
        (progressEvent.loaded * 100) / progressEvent.total
      );

      onProgress(percent);
    },
  });

  return response.data;
};

// ============================================================
// MULTIPLE FILE UPLOAD
// ============================================================

export const uploadMultipleFiles = async (files, onProgress) => {
  const formData = new FormData();

  files.forEach((file) => {
    formData.append('files', file);
  });

  const response = await api.post(
    '/files/upload-multiple',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },

      onUploadProgress: (progressEvent) => {
        if (!onProgress || !progressEvent.total) return;

        const percent = Math.round(
          (progressEvent.loaded * 100) / progressEvent.total
        );

        onProgress(percent);
      },
    }
  );

  return response.data;
};

// ============================================================
// DOCUMENT UPLOAD HELPER
// ============================================================

export const uploadDocuments = async (files, onProgress) => {
  if (!files || files.length === 0) {
    throw new Error('No PDF files selected.');
  }

  if (files.length === 1) {
    const result = await uploadFile(files[0], onProgress);

    return [result];
  }

  return await uploadMultipleFiles(files, onProgress);
};

// ============================================================
// CREATE ORDER
// ============================================================

export const createOrder = async ({
  fileIds,
  copies = 1,
  colorMode = 'bw',
  duplex = false,
  pageRange = 'all',
}) => {
  const response = await api.post('/orders', {
    file_ids: fileIds,
    copies,
    color_mode: colorMode,
    duplex,
    page_range: pageRange,
  });

  return response.data;
};

// ============================================================
// GET ORDER
// ============================================================

export const getOrder = async (orderId) => {
  const response = await api.get(`/orders/${orderId}`);

  return response.data;
};

// ============================================================
// GET LATEST ORDERS
// ============================================================

export const getLatestOrders = async () => {
  const response = await api.get('/orders/latest');

  return response.data;
};

// ============================================================
// GET ALL ORDERS
// ============================================================

export const getAllOrders = async () => {
  const response = await api.get('/orders');

  return response.data;
};

// ============================================================
// PAYMENT
// ============================================================

export const startPayment = async (orderId) => {
  const response = await api.post(
    `/payments/${orderId}/start`
  );

  return response.data;
};

export const verifyPayment = async (
  orderId,
  paymentReference
) => {
  const response = await api.post(
    `/payments/${orderId}/verify`,
    {
      payment_reference: paymentReference,
    }
  );

  return response.data;
};

export default api;