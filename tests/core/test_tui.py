import pytest
from unittest.mock import patch
from council_manager.server.tui import CouncilDashboardApp
from tests.core.test_server import test_db_session, workspace_dir

@pytest.mark.anyio
async def test_tui_app_mount(test_db_session):
    """Verify that the TUI dashboard app runs and mounts widgets correctly."""
    app = CouncilDashboardApp(workspace=test_db_session)
    async with app.run_test() as pilot:
        # Assert database widgets are mounted
        assert app.query_one("#proposals-table") is not None
        assert app.query_one("#decisions-table") is not None
        assert app.query_one("#roadmap-table") is not None
        assert app.query_one("#audits-table") is not None
        
        # Verify initial data loads
        p_table = app.query_one("#proposals-table")
        assert p_table.row_count == 1  # test_db_session seeds 1 proposal
        
        d_table = app.query_one("#decisions-table")
        assert d_table.row_count == 1  # test_db_session seeds 1 decision
