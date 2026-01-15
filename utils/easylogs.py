import os
import json
import requests
from datetime import datetime
from typing import Dict, Any, Optional
import threading
from queue import Queue
import time
import urllib3

# Disable SSL warnings for EasyLogs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import logging


class EasyLogsHandler:
    """
    Centralized logging handler for EasyLogs integration.
    Handles batching and asynchronous sending of logs to EasyLogs API.
    """

    def __init__(self):
        self.api_key = os.environ.get('EASYLOGS_API_KEY')
        self.api_url = "https://ingest.easylogs.co/logs"
        self.batch_queue = Queue()
        self.batch_size = 10
        self.flush_interval = 5  # seconds
        self.is_running = True
        self._pid = os.getpid()  # Track process ID for fork detection
        self._lock = threading.Lock()

        # Start the background worker thread
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def _ensure_worker_running(self):
        """Ensure the worker thread is running in the current process."""
        current_pid = os.getpid()
        if current_pid != self._pid:
            # Process was forked, reinitialize
            with self._lock:
                if current_pid != self._pid:  # Double-check after acquiring lock
                    self._pid = current_pid
                    self.batch_queue = Queue()
                    self.is_running = True
                    self.worker_thread = threading.Thread(target=self._worker, daemon=True)
                    self.worker_thread.start()
    
    def _worker(self):
        """Background worker that processes log batches."""
        batch = []
        last_flush = time.time()
        
        while self.is_running:
            try:
                # Try to get a log entry with timeout
                timeout = max(0.1, self.flush_interval - (time.time() - last_flush))
                try:
                    log_entry = self.batch_queue.get(timeout=timeout)
                    batch.append(log_entry)
                except:
                    pass
                
                # Flush if batch is full or interval has passed
                current_time = time.time()
                if (len(batch) >= self.batch_size or 
                    (len(batch) > 0 and current_time - last_flush >= self.flush_interval)):
                    self._flush_batch(batch)
                    batch = []
                    last_flush = current_time
                    
            except Exception as e:
                # Silently handle errors to avoid disrupting the application
                pass
    
    def _flush_batch(self, batch: list):
        """Send a batch of logs to EasyLogs."""
        if not self.api_key or not batch:
            return
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Send each log entry individually for now
            # Could be optimized to send in batches if EasyLogs supports it
            for log_entry in batch:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=log_entry,
                    timeout=5,
                    verify=False  # Using -k flag equivalent
                )
        except Exception as e:
            # Silently handle errors
            pass
    
    def log(self, level: str, message: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Send a log entry to EasyLogs.

        Args:
            level: Log level (info, warning, error, debug)
            message: Log message
            metadata: Additional metadata to include
        """
        if not self.api_key:
            # Fallback to console if API key not configured
            print(f"[{level.upper()}] {message}")
            return

        # Ensure worker thread is running (handles forked processes)
        self._ensure_worker_running()

        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            "service": "lfg",
            "env": os.environ.get("ENVIRONMENT", "development"),
            "app_type": os.environ.get("APP_TYPE", "web"),
            "metadata": {
                **(metadata or {})
            }
        }

        # Add to queue for async processing
        try:
            self.batch_queue.put_nowait(log_entry)
        except:
            # Queue is full, send synchronously as fallback
            self._flush_batch([log_entry])
    
    def info(self, message: str, **metadata):
        """Log an info message."""
        self.log("info", message, metadata)
    
    def warning(self, message: str, **metadata):
        """Log a warning message."""
        self.log("warning", message, metadata)
    
    def error(self, message: str, **metadata):
        """Log an error message."""
        self.log("error", message, metadata)
    
    def debug(self, message: str, **metadata):
        """Log a debug message."""
        self.log("debug", message, metadata)
    
    def shutdown(self):
        """Gracefully shutdown the logger."""
        self.is_running = False
        # Flush any remaining logs
        remaining = []
        while not self.batch_queue.empty():
            try:
                remaining.append(self.batch_queue.get_nowait())
            except:
                break
        if remaining:
            self._flush_batch(remaining)


class DjangoEasyLogsHandler(logging.Handler):
    """
    Django logging handler that sends logs to EasyLogs.
    This integrates with Django's standard logging system.
    """
    
    def __init__(self):
        super().__init__()
        self.easylogs_handler = EasyLogsHandler()
    
    def emit(self, record):
        """
        Emit a log record to EasyLogs.
        
        Args:
            record: LogRecord instance
        """
        try:
            # Map logging levels
            level_map = {
                logging.DEBUG: 'debug',
                logging.INFO: 'info',
                logging.WARNING: 'warning',
                logging.ERROR: 'error',
                logging.CRITICAL: 'error'
            }
            
            level = level_map.get(record.levelno, 'info')
            
            # Extract metadata from the log record
            metadata = {}
            
            # Add standard logging attributes
            metadata['logger_name'] = record.name
            metadata['module'] = record.module
            metadata['funcName'] = record.funcName
            metadata['lineno'] = record.lineno
            metadata['pathname'] = record.pathname
            
            # Add any extra attributes passed via the 'extra' parameter
            if hasattr(record, 'easylogs_metadata'):
                metadata.update(record.easylogs_metadata)
            
            # Add exception info if present
            if record.exc_info:
                import traceback
                metadata['exception'] = traceback.format_exception(*record.exc_info)
            
            # Send to EasyLogs
            self.easylogs_handler.log(level, self.format(record), metadata)
            
        except Exception:
            # Silently fail to avoid disrupting the application
            pass
    
    def close(self):
        """Close the handler and shutdown the EasyLogs handler."""
        self.easylogs_handler.shutdown()
        super().close()


# Global logger instance for backward compatibility
logger = EasyLogsHandler()


# Convenience functions for direct import (deprecated)
def log_info(message: str, **metadata):
    """Log an info message. DEPRECATED: Use standard logging instead."""
    logger.info(message, **metadata)


def log_warning(message: str, **metadata):
    """Log a warning message. DEPRECATED: Use standard logging instead."""
    logger.warning(message, **metadata)


def log_error(message: str, **metadata):
    """Log an error message. DEPRECATED: Use standard logging instead."""
    logger.error(message, **metadata)


def log_debug(message: str, **metadata):
    """Log a debug message. DEPRECATED: Use standard logging instead."""
    logger.debug(message, **metadata)