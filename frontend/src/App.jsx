import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import HeroSection from './components/HeroSection';
import FileUploader from './components/FileUploader';
import DocumentReadyCard from './components/DocumentReadyCard';
import HowItWorksSection from './components/HowItWorksSection';
import PrintingOptionsScreen from './components/PrintingOptionsScreen';
import OrderSummaryCard from './components/OrderSummaryCard';
import HowItWorksModal from './components/HowItWorksModal';
import { uploadDocuments, checkHealth } from './services/api';
import { WifiOff, Users } from 'lucide-react';

export default function App() {
  const [files, setFiles] = useState([]);
  const [uploadingFiles, setUploadingFiles] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState(null);
  const [currentView, setCurrentView] = useState('upload'); // 'upload', 'options', or 'order_summary'
  const [activeOrder, setActiveOrder] = useState(null);
  const [isHowItWorksOpen, setIsHowItWorksOpen] = useState(false);
  const [backendOnline, setBackendOnline] = useState(null);

  // Check backend health on initial load
  useEffect(() => {
    checkHealth()
      .then((res) => {
        setBackendOnline(res.database === 'connected');
      })
      .catch(() => setBackendOnline(false));
  }, []);

  // Handle PDF file selection from Uploader
  const handleFilesSelected = async (selectedFiles, validationError) => {
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    if (!selectedFiles || selectedFiles.length === 0) return;

    setErrorMessage(null);
    setUploadingFiles(selectedFiles);
    setIsUploading(true);
    setUploadProgress(0);

    try {
      // Dispatch upload to FastAPI backend
      const uploadedResults = await uploadDocuments(selectedFiles, (progress) => {
        setUploadProgress(progress);
      });

      // Update state with backend response (including actual page_count)
      setFiles((prev) => [...prev, ...uploadedResults]);
      setBackendOnline(true);
      setCurrentView('upload');
    } catch (err) {
      setErrorMessage(err.message || "We couldn't upload your PDF. Please check your connection and try again.");
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
      setUploadingFiles(null);
    }
  };

  // Remove individual file from list
  const handleRemoveFile = (fileId) => {
    setFiles((prev) => {
      const remaining = prev.filter((f) => f.file_id !== fileId);
      if (remaining.length === 0) {
        setCurrentView('upload');
        setActiveOrder(null);
      }
      return remaining;
    });
  };

  // Reset all uploaded files and order state to start fresh
  const handleReset = () => {
    setFiles([]);
    setActiveOrder(null);
    setErrorMessage(null);
    setUploadingFiles(null);
    setCurrentView('upload');
  };

  // Called when an order is created successfully by PrintingOptionsScreen
  const handleOrderCreated = (order) => {
    setActiveOrder(order);
    setCurrentView('order_summary');
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900 selection:bg-brand-500 selection:text-white">
      {/* Sticky Header */}
      <Header onOpenHowItWorks={() => setIsHowItWorksOpen(true)} />

      {/* Main Content Area */}
      <main className="flex-1 max-w-3xl w-full mx-auto px-4 sm:px-6 py-6 sm:py-8 flex flex-col items-center">
        {/* Backend Connectivity Banner */}
        {backendOnline === false && (
          <div className="w-full max-w-xl mb-6 p-3.5 rounded-2xl bg-amber-50 border border-amber-200 flex items-center gap-2.5 text-amber-800 text-xs sm:text-sm shadow-sm">
            <WifiOff className="w-4 h-4 text-amber-600 shrink-0" />
            <span>
              SmartPrint service is connecting to the server. Please verify the backend is running.
            </span>
          </div>
        )}

        {/* View Routing: Upload/Ready Flow, Printing Options, or Order Summary */}
        {currentView === 'order_summary' && activeOrder ? (
          <OrderSummaryCard
            order={activeOrder}
            onReset={handleReset}
            onBackToOptions={() => setCurrentView('options')}
          />
        ) : currentView === 'options' ? (
          <PrintingOptionsScreen
            files={files}
            onBack={() => setCurrentView('upload')}
            onReset={handleReset}
            onOrderCreated={handleOrderCreated}
          />
        ) : (
          <>
            {/* Hero Section */}
            <HeroSection />

            {/* Dynamic Upload / Document Ready Area */}
            <div className="mt-4 w-full flex flex-col items-center">
              {files.length === 0 ? (
                <FileUploader
                  onFilesSelected={handleFilesSelected}
                  isUploading={isUploading}
                  uploadProgress={uploadProgress}
                  uploadingFiles={uploadingFiles}
                  errorMessage={errorMessage}
                  onClearError={() => setErrorMessage(null)}
                />
              ) : (
                <div className="w-full max-w-xl space-y-4">
                  <DocumentReadyCard
                    files={files}
                    onContinue={() => setCurrentView('options')}
                    onReset={handleReset}
                    onRemoveFile={handleRemoveFile}
                  />

                  {/* Add More Files option */}
                  <FileUploader
                    compact={true}
                    onFilesSelected={handleFilesSelected}
                    isUploading={isUploading}
                    uploadProgress={uploadProgress}
                    uploadingFiles={uploadingFiles}
                    errorMessage={errorMessage}
                    onClearError={() => setErrorMessage(null)}
                  />
                </div>
              )}
            </div>

            {/* How It Works Section */}
            <HowItWorksSection />
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200/80 bg-white py-6 mt-12 text-xs text-slate-500">
        <div className="max-w-3xl mx-auto px-4 flex flex-col items-center gap-3">
          {/* Top row: Brand & Subtitle */}
          <div className="w-full flex flex-col sm:flex-row items-center justify-between gap-2 pb-3 border-b border-slate-100">
            <div>
              <p className="font-bold text-slate-900 text-sm">SmartPrint</p>
              <p className="text-[11px] text-slate-500">Smart self-service printing system</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 font-medium">
                <span className={`w-2 h-2 rounded-full ${backendOnline ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                {backendOnline ? 'Database Connected' : 'Connecting'}
              </span>
              <span>•</span>
              <span className="font-medium text-slate-600">Stage 2</span>
            </div>
          </div>

          {/* Project Team Members */}
          <div className="w-full flex flex-col sm:flex-row items-center justify-center gap-2 text-center pt-1">
            <span className="flex items-center gap-1.5 font-semibold text-slate-700">
              <Users className="w-3.5 h-3.5 text-brand-600" />
              <span>Project Team:</span>
            </span>
            <div className="flex flex-wrap items-center justify-center gap-1.5 sm:gap-2">
              <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-slate-100/90 text-slate-800 font-medium border border-slate-200/80 hover:border-brand-300 hover:bg-brand-50/50 transition-colors">
                Darshan Kholkar
              </span>
              <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-slate-100/90 text-slate-800 font-medium border border-slate-200/80 hover:border-brand-300 hover:bg-brand-50/50 transition-colors">
                Harshvardhan Chavan
              </span>
              <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-slate-100/90 text-slate-800 font-medium border border-slate-200/80 hover:border-brand-300 hover:bg-brand-50/50 transition-colors">
                Rajveer Sahare
              </span>
              <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-slate-100/90 text-slate-800 font-medium border border-slate-200/80 hover:border-brand-300 hover:bg-brand-50/50 transition-colors">
                Pradeep Biradar
              </span>
            </div>
          </div>
        </div>
      </footer>

      {/* How It Works Modal */}
      <HowItWorksModal
        isOpen={isHowItWorksOpen}
        onClose={() => setIsHowItWorksOpen(false)}
      />
    </div>
  );
}
