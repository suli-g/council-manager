from unittest.mock import MagicMock
from council_manager.core.prompter import AgentPrompter, VoteResponse

def test_generate_deliberation_mocked():
    # Setup mock Client and Response
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "This is a deliberation rationale."
    mock_client.models.generate_content.return_value = mock_response

    prompter = AgentPrompter(client=mock_client)
    res = prompter.generate_deliberation(
        team_name="Team A",
        paradigm_specialty="Functional",
        title="Title X",
        description="Desc Y",
        options=["Alt 1", "Alt 2"]
    )

    assert res == "This is a deliberation rationale."
    
    # Assert generate_content called with expected arguments
    mock_client.models.generate_content.assert_called_once()
    args, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["model"] == "gemini-2.5-flash"
    assert kwargs["contents"].startswith("Please deliberate on the following proposal:")
    assert kwargs["config"].system_instruction.startswith("You are an AI agent representing the 'Team A'")

def test_generate_vote_mocked():
    mock_client = MagicMock()
    mock_response = MagicMock()
    
    # Setup parsed response object
    mock_parsed_vote = VoteResponse(vote="Alt 1", rationale="Clean Functional style")
    mock_response.parsed = mock_parsed_vote
    mock_client.models.generate_content.return_value = mock_response

    prompter = AgentPrompter(client=mock_client)
    res = prompter.generate_vote(
        team_name="Team A",
        paradigm_specialty="Functional",
        title="Title X",
        description="Desc Y",
        options=["Alt 1", "Alt 2"],
        rationales_context="Rationales..."
    )

    assert res.vote == "Alt 1"
    assert res.rationale == "Clean Functional style"
    
    mock_client.models.generate_content.assert_called_once()
    args, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["config"].response_mime_type == "application/json"
    assert kwargs["config"].response_schema == VoteResponse
