import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from .config import settings

log_file = f"{settings.log_file_name}_{datetime.now().year}{datetime.now().month}{datetime.now().day}.log"
logger = logging.getLogger(__name__)
# Configure the logger
logger.setLevel(logging.INFO)
file_handler = RotatingFileHandler(log_file, maxBytes=100*1024*1024, backupCount=3)  # 1 MB max size, 3 backups
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Add handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(logging.StreamHandler())
