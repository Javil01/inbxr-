import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get('WEB_CONCURRENCY', '4'))
worker_class = 'sync'
timeout = 120
accesslog = '-'
errorlog = '-'
loglevel = 'info'
