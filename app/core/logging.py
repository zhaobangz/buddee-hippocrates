import logging
import sys
import json
from datetime import datetime
from pythonjsonlogger import jsonlogger

def setup_logging():
    logger = logging.getLogger()
    
    # Standard handler for console
    logHandler = logging.StreamHandler(sys.stdout)
    
    # JSON formatter for machine-readable logs (CloudWatch/Datadog ready)
    class CustomJsonFormatter(jsonlogger.JsonFormatter):
        def add_fields(self, log_record, record, message_dict):
            super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
            if not log_record.get('timestamp'):
                log_record['timestamp'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            if log_record.get('level'):
                log_record['level'] = log_record['level'].upper()
            else:
                log_record['level'] = record.levelname

    formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')
    logHandler.setFormatter(formatter)
    
    logger.addHandler(logHandler)
    logger.setLevel(logging.INFO)
    
    # Silence chatty libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    return logger

logger = setup_logging()
