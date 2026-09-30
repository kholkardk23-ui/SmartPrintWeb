import pymupdf


class PDFProcessingError(Exception):
    """Exception raised when a PDF cannot be read or is invalid."""
    pass


class PDFService:
    """Service for validating and extracting information from PDF documents."""

    @staticmethod
    def validate_pdf_header(file_header: bytes) -> bool:
        """Check whether the initial bytes match standard PDF file signature (%PDF-)."""
        return file_header.startswith(b"%PDF-")

    @staticmethod
    def get_pdf_page_count_from_bytes(pdf_bytes: bytes) -> int:
        """
        Open a PDF from byte buffer using PyMuPDF and return its exact page count.
        Using stream in memory avoids OS file lock issues on Windows.
        
        Raises:
            PDFProcessingError: If the file is corrupted, encrypted, empty, or not a valid PDF.
        """
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise PDFProcessingError("The uploaded file is not a valid or readable PDF document.") from exc

        try:
            if doc.is_encrypted:
                raise PDFProcessingError("Password-protected PDF files are not supported. Please remove the password.")

            page_count = doc.page_count

            if page_count <= 0:
                raise PDFProcessingError("The uploaded PDF has no readable pages.")

            return page_count
        finally:
            doc.close()


pdf_service = PDFService()
