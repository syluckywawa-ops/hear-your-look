import os

bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
# Single instance / worker is required by the in-process concurrency gate.
workers = 1
worker_class = 'gthread'
threads = 4
timeout = 90
graceful_timeout = 90
umask = 0o077
accesslog = None
errorlog = '-'
capture_output = False
control_socket_disable = True
limit_request_line = 4096
limit_request_fields = 50
limit_request_field_size = 4096
