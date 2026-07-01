web: uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips "*"
worker: python -m app.jobs.sync_live_scores --watch
