import logging

from app.main import configure_application_logging


def test_application_logging_uses_info_propagation_without_duplicate_handlers(caplog):
    access_logger = logging.getLogger("uvicorn.access")
    access_handlers = list(access_logger.handlers)

    configure_application_logging()
    handler_count = len(logging.getLogger().handlers)
    configure_application_logging()

    assert logging.getLogger("app").level == logging.INFO
    assert logging.getLogger("app").propagate is True
    assert len(logging.getLogger().handlers) == handler_count
    assert list(access_logger.handlers) == access_handlers

    marker = "application logging propagation check"
    with caplog.at_level(logging.INFO, logger="app.test"):
        logging.getLogger("app.test").info(marker)
    assert [record.getMessage() for record in caplog.records].count(marker) == 1
