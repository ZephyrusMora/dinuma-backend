release: playwright install chromium
web: gunicorn -w 1 -k uvicorn.workers.UvicornWorker app.main:app
