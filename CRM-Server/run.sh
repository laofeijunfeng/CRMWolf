#!/bin/bash
source venv/bin/activate
export CRM_DEBUG=true
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
