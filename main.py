"""
ReelForge Entry Point
Configures logging and launches the application.
"""
import logging
import sys
from app import ReelForgeApp

def setup_logging():
    """Configures the root logger to write to a file."""
    # Create a logger
    log_file = 'media_weaver.log'
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Configure file handler
    logging.basicConfig(
        level=logging.DEBUG,  # Capture all levels of logs
        format=log_format,
        filename=log_file,
        filemode='w' # 'w' for overwrite each session, 'a' for append
    )
    
    # Also log to console (optional, but good for debugging)
    # console_handler = logging.StreamHandler(sys.stdout)
    # console_handler.setLevel(logging.INFO)
    # console_handler.setFormatter(logging.Formatter(log_format))
    # logging.getLogger().addHandler(console_handler)

    logging.info("Logging configured. Starting application.")

def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    """
    A top-level exception handler to log any uncaught exceptions.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        # Don't log Ctrl+C
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

# 1. Set up the global exception hook
sys.excepthook = handle_uncaught_exception

if __name__ == "__main__":
    # 2. Set up logging *before* the app runs
    setup_logging()
    
    try:
        app = ReelForgeApp()
        app.mainloop()
    except Exception as e:
        # Catch any final-moment startup errors
        logging.critical("Fatal error during app initialization", exc_info=True)
        sys.exit(1)