import logging

# Define custom colors for log levels
class Color:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

# Add a custom log level for SUCCESS
SUCCESS_LEVEL_NUM = 25
logging.addLevelName(SUCCESS_LEVEL_NUM, "SUCCESS")

def success(self, message, *args, **kws):
    if self.isEnabledFor(SUCCESS_LEVEL_NUM):
        self._log(SUCCESS_LEVEL_NUM, message, args, **kws)

logging.Logger.success = success

class ColoredFormatter(logging.Formatter):
    """
    A custom log formatter that adds color to log messages based on their level.
    """
    def __init__(self, fmt, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.log_level_colors = {
            logging.DEBUG: Color.BLUE,
            logging.INFO: Color.RESET,
            SUCCESS_LEVEL_NUM: Color.GREEN,
            logging.WARNING: Color.YELLOW,
            logging.ERROR: Color.RED,
            logging.CRITICAL: Color.RED,
        }

    def format(self, record):
        color = self.log_level_colors.get(record.levelno)
        record.msg = color + str(record.msg) + Color.RESET
        return super().format(record)

def setup_logger():
    """
    Sets up the root logger to output colored messages to the console.
    """
    handler = logging.StreamHandler()
    formatter = ColoredFormatter(
        '%(asctime)s [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Avoid adding handlers multiple times
    if not logger.handlers:
        logger.addHandler(handler)

# Example usage:
if __name__ == '__main__':
    setup_logger()
    logging.info("This is an info message.")
    logging.success("This is a success message.")
    logging.warning("This is a warning message.")
    logging.error("This is an error message.")
    logging.critical("This is a critical error message.")
