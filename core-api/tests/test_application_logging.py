import logging

from app.main import configure_application_logging


def test_application_logging_uses_info_handler_without_duplicate_handlers(caplog):
    access_logger = logging.getLogger("uvicorn.access")
    access_handlers = list(access_logger.handlers)

    configure_application_logging()
    application_logger = logging.getLogger("app")
    handler_count = len(application_logger.handlers)
    configure_application_logging()

    assert application_logger.level == logging.INFO
    assert application_logger.propagate is False
    assert len(application_logger.handlers) == handler_count
    assert list(access_logger.handlers) == access_handlers

    marker = "application logging propagation check"
    with caplog.at_level(logging.INFO, logger="app.test"):
        logging.getLogger("app.test").info(marker)
    assert application_logger.handlers
