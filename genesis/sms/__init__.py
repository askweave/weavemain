"""Genesis over SMS: Twilio webhook -> durable queue -> the same Orchestrator the dashboard uses -> SMS replies."""

import logging

# The Twilio SDK logs every request (URLs, headers) at INFO; Genesis logs its own redacted sms.* events instead.
logging.getLogger("twilio.http_client").setLevel(logging.WARNING)
