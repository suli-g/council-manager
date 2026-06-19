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

@pytest.mark.anyio
async def test_tui_new_proposal_modal(test_db_session):
    """Verify that the proposal creation modal can be opened and successfully submitted."""
    app = CouncilDashboardApp(workspace=test_db_session)
    async with app.run_test() as pilot:
        # Press 'n' to trigger the new proposal modal
        await pilot.press("n")
        
        # The current active screen should be the ProposalCreateModal
        from council_manager.server.tui import ProposalCreateModal
        assert isinstance(app.screen, ProposalCreateModal)
        
        # Enter description
        app.screen.query_one("#input-desc").value = "New TUI Proposal Description"
        
        # Enter topic
        app.screen.query_one("#input-topic").value = "TUI Integration"
        
        # Enter options
        app.screen.query_one("#input-options").value = "Option A; Option B"
        
        # Click the Create submit button and verify proposal creation call
        import anyio
        with patch("council_manager.core.orchestrator.council_orchestrator.create_proposal") as mock_create:
            await pilot.click("#btn-create-submit")
            
            # Wait for executor thread to run and invoke create_proposal
            for _ in range(50):
                if mock_create.called:
                    break
                await anyio.sleep(0.1)
                
            assert mock_create.called
            called_kwargs = mock_create.call_args[1]
            assert called_kwargs["description"] == "New TUI Proposal Description"
            assert called_kwargs["topic"] == "TUI Integration"
            assert called_kwargs["options"] == ["Option A", "Option B"]

