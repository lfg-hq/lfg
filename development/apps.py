from django.apps import AppConfig
import logging

# Configure logging
logger = logging.getLogger(__name__)

class DevelopmentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'development'
    
    def ready(self):
        """
        Called when the Django application is ready.
        Initialize any application-specific tasks here.
        """
        # Import here to avoid circular imports
        try:
            from .k8s_manager import ensure_persistent_storage_directory
            
            # Ensure the persistent storage directory exists on the Kubernetes host
            if ensure_persistent_storage_directory():
                logger.info("Kubernetes persistent storage directory is ready")
            else:
                logger.warning("Failed to ensure Kubernetes persistent storage directory exists")
        except Exception as e:
            logger.error(f"Error during application initialization: {str(e)}")
