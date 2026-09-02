from __future__ import annotations

import asyncio
from threading import Event
from unittest.mock import patch

from app.api.routes.sales import get_sales_workspace
from app.api.routes.visits import get_visits_workspace
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.main import _run_startup_auto_analysis


def test_sales_and_visits_remain_responsive_during_background_analysis():
    async def execute():
        store = InMemoryCoreDataLayer()
        started = Event()
        release = Event()
        finished = False

        async def slow_analysis():
            nonlocal finished
            started.set()
            await asyncio.to_thread(release.wait)
            finished = True

        with patch(
            "app.main.AutoBusinessAnalyticsService.run_startup_if_needed",
            side_effect=slow_analysis,
        ):
            analysis_task = asyncio.create_task(_run_startup_auto_analysis(store))
            await asyncio.to_thread(started.wait)
            sales, visits = await asyncio.gather(
                asyncio.to_thread(get_sales_workspace, store),
                asyncio.to_thread(get_visits_workspace, store),
            )
            assert finished is False
            assert sales.rows == []
            assert visits.rows.visits == []
            release.set()
            await analysis_task

        assert finished is True

    asyncio.run(execute())
