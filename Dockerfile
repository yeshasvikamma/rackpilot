# RackPilot — Dockerfile (STUB)
#
# This is intentionally a scaffold. It gets filled in during Block 4, AFTER the
# merge: once api/main.py imports `from solver.model import solve` (the real
# solver) and the full /handle flow passes end to end.
#
# Block 4 checklist (do NOT build this until the swap is done):
#   1. Base image with Python 3.11+ (ortools needs a manylinux wheel).
#   2. Install requirements.txt (ortools is the heavy one — cache this layer).
#   3. Copy the source. Set GMI_API_KEY / GMI_BASE_URL via runtime env, NOT baked in.
#   4. CMD: uvicorn api.main:app --host 0.0.0.0 --port 8000
#
# Sketch (uncomment + finalize in Block 4):
#
# FROM python:3.11-slim
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
# COPY . .
# EXPOSE 8000
# CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
