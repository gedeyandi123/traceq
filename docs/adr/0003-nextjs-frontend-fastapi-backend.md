# Next.js for the UI, FastAPI (Python) for the domain and AI

The frontend is Next.js; all domain logic, the document pipeline, AI and evaluation live in FastAPI, with a TypeScript client generated from OpenAPI. The best document parsers (Docling, PaddleOCR) exist only in Python, and long OCR and ingest jobs need a worker outside the web request anyway, so Python is unavoidable; keeping the domain in one language stops its logic splitting across two runtimes.

## Considered Options

- Full-stack TypeScript Next.js plus a Python worker for parsing only: rejected, the domain splits across two languages.
- Express: rejected, it adds nothing over Next.js route handlers and adds a third runtime.
