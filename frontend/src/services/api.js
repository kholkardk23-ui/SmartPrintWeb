import axios from 'axios';

// Resolve base API URL from environment variable or default to local FastAPI server
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000, // 60 seconds
});

/**
 * Upload a single customer PDF file to SmartPrint backend
 * @param {File} file - PDF file to upload
 * @param {Function} [onProgress] - Optional callback with percentage (0 to 100)
 * @returns {Promise<{file_id: string, original_filename: string, file_size: number, page_count: number, status: string}>}
 */
export async function uploadPdf(file, onProgress) {
  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await apiClient.post('/api/files/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onProgress) {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          onProgress(percentCompleted);
        }
      },
    });

    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

export const uploadFile = uploadPdf;

/**
 * Upload multiple customer PDF files to SmartPrint backend in one batch
 * @param {File[]} files - Array of PDF files
 * @param {Function} [onProgress] - Optional callback with percentage (0 to 100)
 * @returns {Promise<Array<{file_id: string, original_filename: string, file_size: number, page_count: number, status: string}>>}
 */
export async function uploadMultipleFiles(files, onProgress) {
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }

  try {
    const response = await apiClient.post('/api/files/upload-multiple', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onProgress) {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          onProgress(percentCompleted);
        }
      },
    });

    return response.data;
  } catch (error) {
    handleApiError(error);
  }
}

/**
 * Unified helper that handles either single or multiple PDF uploads cleanly
 * @param {File|File[]} filesInput - Single File or Array of Files
 * @param {Function} [onProgress] - Optional progress callback
 * @returns {Promise<Array>} Array of uploaded file response objects
 */
export async function uploadDocuments(filesInput, onProgress) {
  const fileList = Array.isArray(filesInput) ? filesInput : [filesInput];
  if (fileList.length === 1) {
    const singleResult = await uploadPdf(fileList[0], onProgress);
    return [singleResult];
  }
  return await uploadMultipleFiles(fileList, onProgress);
}

/**
 * Check backend health status
 * @returns {Promise<{status: string, service: string}>}
 */
export async function checkHealth() {
  try {
    const response = await apiClient.get('/api/health');
    return response.data;
  } catch (error) {
    throw new Error('Backend service is currently unavailable. Please try again.');
  }
}

/**
 * Normalize and handle API errors with friendly user-facing messages
 */
function handleApiError(error) {
  if (error.response) {
    const status = error.response.status;
    const detail = error.response.data?.detail;

    if (typeof detail === 'string') {
      throw new Error(detail);
    }
    if (status === 413) {
      throw new Error('One or more files exceed the 10 MB limit.');
    }
    if (status === 400) {
      throw new Error('Please upload valid PDF files.');
    }
    throw new Error("We couldn't upload your file(s). Please try again.");
  } else if (error.request) {
    throw new Error('SmartPrint backend is unreachable. Please ensure the server is running and check your connection.');
  } else {
    throw new Error(error.message || "We couldn't upload your file(s). Please try again.");
  }
}
/**
 * Create a print order.
 * Pricing and page calculations are performed by the backend.
 *
 * @param {Object} orderData
 * @param {string} orderData.file_id - Uploaded file ID
 * @param {number} orderData.copies - Number of copies
 * @param {string} orderData.color_mode - 'bw' or 'color'
 * @param {boolean} orderData.duplex - true for double-sided
 * @param {string} orderData.page_range - 'all' or selected pages
 * @returns {Promise<Object>} Authoritative order response
 */
export async function createOrder(orderData) {
  try {
    const response = await apiClient.post('/api/orders', orderData);
    return response.data;
  } catch (error) {
    if (error.response) {
      const detail = error.response.data?.detail;

      if (typeof detail === 'string') {
        throw new Error(detail);
      }

      throw new Error('Unable to create the print order. Please check your options.');
    }

    if (error.request) {
      throw new Error(
        'SmartPrint backend is unreachable. Please ensure the server is running.'
      );
    }

    throw new Error(error.message || 'Unable to create the print order.');
  }
}
export default {
  uploadPdf,
  uploadFile,
  uploadMultipleFiles,
  uploadDocuments,
  checkHealth,
  createOrder,
};
