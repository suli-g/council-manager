from unittest.mock import MagicMock, AsyncMock
import json
import pytest
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

@pytest.mark.anyio
async def test_generate_deliberation_async_mocked():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Async deliberation response"
    
    # Setup async mock on client.aio.models.generate_content
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
    
    prompter = AgentPrompter(client=mock_client)
    res = await prompter.generate_deliberation_async(
        team_name="Team B",
        paradigm_specialty="OOP",
        title="Title Z",
        description="Desc W",
        options=["Opt A", "Opt B"]
    )
    
    assert res == "Async deliberation response"
    mock_client.aio.models.generate_content.assert_called_once()

@pytest.mark.anyio
async def test_generate_vote_async_mocked():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_parsed_vote = VoteResponse(vote="Opt B", rationale="Better coupling")
    mock_response.parsed = mock_parsed_vote
    
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
    
    prompter = AgentPrompter(client=mock_client)
    res = await prompter.generate_vote_async(
        team_name="Team B",
        paradigm_specialty="OOP",
        title="Title Z",
        description="Desc W",
        options=["Opt A", "Opt B"],
        rationales_context="context"
    )
    
    assert res.vote == "Opt B"
    assert res.rationale == "Better coupling"
    mock_client.aio.models.generate_content.assert_called_once()

def test_generate_vote_fallback_json():
    mock_client = MagicMock()
    mock_response = MagicMock()
    
    # No parsed attribute to force JSON fallback parsing
    del mock_response.parsed
    mock_response.text = json.dumps({"vote": "Alt 2", "rationale": "Fallback parsing works"})
    mock_client.models.generate_content.return_value = mock_response

    prompter = AgentPrompter(client=mock_client)
    res = prompter.generate_vote(
        team_name="Team C",
        paradigm_specialty="Imperative",
        title="T",
        description="D",
        options=["Alt 1", "Alt 2"],
        rationales_context="..."
    )

    assert res.vote == "Alt 2"
    assert res.rationale == "Fallback parsing works"


def test_generate_proposal_inception_mocked():
    from council_manager.core.prompter import InceptionResponse
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_parsed_inception = InceptionResponse(topic="Cool Topic", options=["Opt 1", "Opt 2"])
    mock_response.parsed = mock_parsed_inception
    mock_client.models.generate_content.return_value = mock_response

    prompter = AgentPrompter(client=mock_client)
    res = prompter.generate_proposal_inception("Some description")

    assert res.topic == "Cool Topic"
    assert res.options == ["Opt 1", "Opt 2"]
    mock_client.models.generate_content.assert_called_once()
    args, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["config"].response_schema == InceptionResponse

@pytest.mark.anyio
async def test_generate_proposal_inception_async_mocked():
    from council_manager.core.prompter import InceptionResponse
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_parsed_inception = InceptionResponse(topic="Async Topic", options=["A", "B"])
    mock_response.parsed = mock_parsed_inception
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    prompter = AgentPrompter(client=mock_client)
    res = await prompter.generate_proposal_inception_async("Some description")

    assert res.topic == "Async Topic"
    assert res.options == ["A", "B"]
    mock_client.aio.models.generate_content.assert_called_once()

