import logging


def setup(debug_mode=False):
    """Streams logs to stdout
    Args:
        debug_mode (bool): a boolean to enable verbose logs
    """
    logFormatter = logging.Formatter(
        "%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s"
    )

    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.INFO)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    if debug_mode:
        rootLogger = logging.getLogger()
        rootLogger.setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled")
        selenium = logging.getLogger("selenium.webdriver.remote.remote_connection")
        selenium.setLevel(logging.ERROR)
