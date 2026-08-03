import logging

from .config import Settings

logger = logging.getLogger("pcip.observability")


def configure_observability(settings: Settings) -> bool:
    connection_string = (
        settings.applicationinsights_connection_string or ""
    ).strip()
    if not connection_string:
        return False

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
            connection_string=connection_string,
            logger_name="pcip",
        )
    except Exception as exc:
        logger.error(
            "azure_monitor_configuration_failed error=%s",
            exc.__class__.__name__,
        )
        return False
    return True
