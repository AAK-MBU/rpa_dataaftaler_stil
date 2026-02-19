"""Module for handling errors"""

import base64
import json
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from io import BytesIO

from automation_server_client import WorkItem
from mbu_dev_shared_components.database.connection import RPAConnection
from mbu_rpa_core.exceptions import BusinessError, ProcessError
from PIL import ImageGrab


@dataclass
class ErrorContext:
    """Context for error handling"""

    item: WorkItem | None = None
    action: Callable | None = None
    send_mail: bool = False
    add_screenshot: bool = True
    process_name: str | None = None


def handle_error(
    error: ProcessError | BusinessError,
    log,
    context: ErrorContext | None = None,
) -> None:
    """
    Function to log error.
    Args:
        error (ProcessError | BusinessError): The error to handle.
        log (function): Logging function to log messages.
        context (ErrorContext): Context object containing additional parameters.
    Returns:
        None
    Raises:
        BusinessError: If a business logic error occurs.
        ProcessError: If a processing error occurs.
    """
    if context is None:
        context = ErrorContext()
    error_json = json.dumps(error.__dictinfo__())
    log_msg = f"Error: {error}"
    if context.item:
        log_msg = f"{repr(error)} raised for item: {context.item}. " + log_msg
        if context.action:
            context.action(error_json)
    log(log_msg)
    if context.send_mail:
        send_error_email(
            error=error,
            add_screenshot=context.add_screenshot,
            process_name=context.process_name,
        )


def send_error_email(
    error: ProcessError | BusinessError,
    add_screenshot: bool = False,
    process_name: str | None = None,
) -> None:
    """
    Send email to defined recipient with error information
    Args:
        error (ProcessError | BusinessError): The error to include in the email.
        add_screenshot (bool): Whether to include a screenshot in the email.
        process_name (str | None): Name of the process where the error occurred.
    Returns:
        None
    Raises:
        Exception: If sending the email fails.
    """
    rpa_conn = RPAConnection(db_env="PROD", commit=False)
    with rpa_conn:
        error_email = rpa_conn.get_constant("Error Email")["value"]
        error_sender = rpa_conn.get_constant("Email Friend")[
            "value"
        ]  # Find in database...
        smtp_server = rpa_conn.get_constant("smtp_server")["value"]
        smtp_port = rpa_conn.get_constant("smtp_port")["value"]

    # Create message
    msg = EmailMessage()
    msg["to"] = error_email
    msg["from"] = error_sender
    msg["subject"] = "Error screenshot" + f": {process_name}" if process_name else ""

    # Create an HTML message with the exception and screenshot
    error_dict = error.__dictinfo__()

    if add_screenshot:
        screenshot = grab_screenshot()
        html_message = f"""
                <html>
                    <body>
                        <p>Error type: {error_dict["type"]}</p>
                        <p>Error message: {error_dict["message"]}</p>
                        <p>{error_dict["traceback"]}</p>
                        <img src="data:image/png;base64,{screenshot}" alt="Screenshot">
                    </body>
                </html>
            """
    else:
        html_message = f"""
                <html>
                    <body>
                        <p>Error type: {error_dict["type"]}</p>
                        <p>Error message: {error_dict["message"]}</p>
                        <p>{error_dict["traceback"]}</p>
                    </body>
                </html>
            """

    msg.set_content("Please enable HTML to view this message.")
    msg.add_alternative(html_message, subtype="html")

    # Send message
    with smtplib.SMTP(smtp_server, smtp_port) as smtp:
        smtp.starttls()
        smtp.send_message(msg)


def grab_screenshot() -> str:
    """
    Grabs screenshot.

    Returns:
        str: Screenshot in base64 format.
    Raises:
        Exception: If screenshot capture fails.
    """
    # Take screenshot and convert to base64
    screenshot = ImageGrab.grab()
    buffer = BytesIO()
    screenshot.save(buffer, format="PNG")
    screenshot_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return screenshot_base64
