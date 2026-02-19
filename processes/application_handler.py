"""Module for handling application startup, and close"""

import logging

APP = None
logger = logging.getLogger(__name__)


def get_app():
    """Function to get the application instance"""
    # ruff: noqa: PLW0602
    global APP
    return APP


def startup():
    """Function for starting applications"""
    logger.info("Starting applications...")

    # This part adds the app to the global var after startup,
    # and allows other files to use get_app() to get the app instance from the startup
    # # ruff: noqa: PLW0603
    # global APP
    # APP = solteq_app


def soft_close():
    """Function for closing applications softly"""
    logger.info("Closing applications softly...")


def hard_close():
    """Function for closing applications hard"""
    logger.info("Closing applications hard...")


def close():
    """Function for closing applications softly or hardly if necessary"""
    try:
        soft_close()
    except Exception:
        hard_close()


def reset():
    """Function for resetting application"""
    close()
    startup()
