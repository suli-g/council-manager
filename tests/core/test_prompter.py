from unittest.mock import MagicMock, AsyncMock, patch
import json
import pytest
from council_manager.core.prompter import AgentPrompter, VoteResponse, DeliberationResponse
 
def test_generate_deliberation_mocked():
    # Setup mock Client and Response
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_parsed = DeliberationResponse(stance="FOR", motivation="Clean Functional style", suggestion="Use pure functions")
    mock_response.parsed = mock_parsed
    mock_client.models.generate_content.return_value = mock_response
 
    prompter = AgentPrompter(client=mock_client)
    res = prompter.generate_deliberation(
        team_name="Team A",
        paradigm_specialty="Functional",
        title="Title X",
        description="Desc Y",
        options=["Alt 1", "Alt 2"]
    )
 
    assert res.stance == "FOR"
    assert res.motivation == "Clean Functional style"
    assert res.suggestion == "Use pure functions"
    
    # Assert generate_content called with expected arguments
    mock_client.models.generate_content.assert_called_once()
    args, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["model"] == "gemini-3.5-flash"
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
    mock_parsed = DeliberationResponse(stance="AGAINST", motivation="Too complex", suggestion="Simplify design")
    mock_response.parsed = mock_parsed
    
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
    
    assert res.stance == "AGAINST"
    assert res.motivation == "Too complex"
    assert res.suggestion == "Simplify design"
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

from unittest.mock import patch
from council_manager.config import settings

def test_custom_provider_deliberation(monkeypatch):
    # Backup original settings
    orig_provider = settings.llm_provider
    orig_base = settings.llm_api_base
    orig_model = settings.gemini_model
    
    try:
        monkeypatch.setattr(settings, "llm_provider", "openai")
        monkeypatch.setattr(settings, "llm_api_base", "https://api.custom.com/v1")
        monkeypatch.setattr(settings, "gemini_model", "custom-model")
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"stance": "FOR", "motivation": "Custom deliberation result", "suggestion": "Try custom method"}'
                }
            }]
        }
        
        with patch("httpx.post", return_value=mock_response) as mock_post:
            prompter = AgentPrompter()
            res = prompter.generate_deliberation(
                team_name="Team A",
                paradigm_specialty="Functional",
                title="Title X",
                description="Desc Y",
                options=["Alt 1", "Alt 2"]
            )
            
            assert res.stance == "FOR"
            assert res.motivation == "Custom deliberation result"
            assert res.suggestion == "Try custom method"
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert args[0] == "https://api.custom.com/v1/chat/completions"
            assert kwargs["json"]["model"] == "custom-model"
    finally:
        settings.llm_provider = orig_provider
        settings.llm_api_base = orig_base
        settings.gemini_model = orig_model

@pytest.mark.anyio
async def test_custom_provider_deliberation_async(monkeypatch):
    orig_provider = settings.llm_provider
    orig_base = settings.llm_api_base
    orig_model = settings.gemini_model
    
    try:
        monkeypatch.setattr(settings, "llm_provider", "ollama")
        monkeypatch.setattr(settings, "llm_api_base", None)
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"stance": "AGAINST", "motivation": "Custom async deliberation", "suggestion": "Try async custom method"}'
                }
            }]
        }
        
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        # Mock __aenter__ and __aexit__ for context manager
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        with patch("httpx.AsyncClient", return_value=mock_client):
            prompter = AgentPrompter()
            res = await prompter.generate_deliberation_async(
                team_name="Team B",
                paradigm_specialty="OOP",
                title="Title Z",
                description="Desc W",
                options=["Opt A", "Opt B"]
            )
            
            assert res.stance == "AGAINST"
            assert res.motivation == "Custom async deliberation"
            assert res.suggestion == "Try async custom method"
            mock_client.post.assert_called_once()
            args, kwargs = mock_client.post.call_args
            assert args[0] == "http://localhost:11434/v1/chat/completions"
    finally:
        settings.llm_provider = orig_provider
        settings.llm_api_base = orig_base
        settings.gemini_model = orig_model

def test_clean_and_parse_json_fallback():
    from council_manager.core.prompter import clean_and_parse_json
    
    # 1. Test standard JSON
    standard_json = '{"vote": "Alt 1", "rationale": "Simple option is best"}'
    assert clean_and_parse_json(standard_json) == {"vote": "Alt 1", "rationale": "Simple option is best"}
    
    # 2. Test JSON wrapped in markdown blocks
    markdown_json = '```json\n{"vote": "Alt A", "rationale": "Pipeline composition"}\n```'
    assert clean_and_parse_json(markdown_json) == {"vote": "Alt A", "rationale": "Pipeline composition"}
    
    # 3. Test malformed JSON with unescaped double quotes inside value
    malformed_json = '{\n  "vote": "Alt 1",\n  "rationale": "This contains an unescaped "double quote" inside the string value."\n}'
    result = clean_and_parse_json(malformed_json)
    assert result["vote"] == "Alt 1"
    assert "unescaped" in result["rationale"]
    assert "double quote" in result["rationale"]
    
    # 4. Test InceptionResponse regex parsing fallback
    inception_json = '{\n  "topic": "Clean Code Project",\n  "options": ["Option 1", "Option 2", "Option 3"]\n}'
    inception_result = clean_and_parse_json(inception_json)
    assert inception_result["topic"] == "Clean Code Project"
    assert inception_result["options"] == ["Option 1", "Option 2", "Option 3"]

    # 5. Test truncated JSON without closing quotes/braces
    truncated_json = '{\n  "vote": "Option A",\n  "rationale": "We should adopt this because it is clean'
    truncated_result = clean_and_parse_json(truncated_json)
    assert truncated_result["vote"] == "Option A"
    assert truncated_result["rationale"] == "We should adopt this because it is clean"

def test_infer_global_member_count_mocked():
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_response = MagicMock()
    from council_manager.core.prompter import OnboardingInferenceResponse
    mock_parsed = OnboardingInferenceResponse(global_member_count=15, rationale="Moderate project complexity")
    mock_response.parsed = mock_parsed
    mock_client.models.generate_content.return_value = mock_response

    prompter = AgentPrompter(client=mock_client)
    res = prompter.infer_global_member_count("Description of the project")

    assert res.global_member_count == 15
    assert res.rationale == "Moderate project complexity"
    mock_client.models.generate_content.assert_called_once()


def test_infer_project_council_mocked():
    mock_client = MagicMock()
    mock_response = MagicMock()
    from council_manager.core.prompter import CouncilInferenceResponse, TeamInference
    mock_parsed = CouncilInferenceResponse(
        selected_template="education",
        teams=[
            TeamInference(id="A", name="Pedagogy Specialists", paradigm_specialty="Learning theories"),
            TeamInference(id="B", name="Curriculum Setters", paradigm_specialty="Syllabus design"),
            TeamInference(id="C", name="Assessment Designers", paradigm_specialty="Testing and rubrics"),
            TeamInference(id="D", name="Instructional Tech", paradigm_specialty="E-learning"),
            TeamInference(id="E", name="Student Experience", paradigm_specialty="Accessibility"),
            TeamInference(id="F", name="Program Administrators", paradigm_specialty="Resource allocation"),
            TeamInference(id="G", name="Contrarians", paradigm_specialty="Devil's Advocacy")
        ]
    )
    mock_response.parsed = mock_parsed
    mock_client.models.generate_content.return_value = mock_response

    prompter = AgentPrompter(client=mock_client)
    res = prompter.infer_project_council("An educational curriculum project")

    assert res.selected_template == "education"
    assert len(res.teams) == 7
    assert res.teams[0].id == "A"
    assert res.teams[0].name == "Pedagogy Specialists"
    mock_client.models.generate_content.assert_called_once()


def test_get_simple_json_template_recursive():
    import json
    from council_manager.core.prompter import get_simple_json_template, CouncilInferenceResponse
    
    template_str = get_simple_json_template(CouncilInferenceResponse)
    template = json.loads(template_str)
    
    assert "selected_template" in template
    assert "teams" in template
    assert isinstance(template["teams"], list)
    assert len(template["teams"]) == 1
    team_obj = template["teams"][0]
    assert "id" in team_obj
    assert "name" in team_obj
    assert "paradigm_specialty" in team_obj


def test_team_inference_normalizer_fallback():
    from council_manager.core.prompter import TeamInference, CouncilInferenceResponse

    # 1. Name with parenthesis format (the exact issue reported in Issue #3)
    team1 = TeamInference.model_validate({
        "id": "A",
        "name": "Contrarians (Devil's Advocacy, Question identification)"
    })
    assert team1.id == "A"
    assert team1.name == "Contrarians"
    assert team1.paradigm_specialty == "Devil's Advocacy, Question identification"

    # 2. Key named 'specialty'
    team2 = TeamInference.model_validate({
        "id": "B",
        "name": "OOP Specialists",
        "specialty": "Design Patterns & Polymorphism"
    })
    assert team2.id == "B"
    assert team2.name == "OOP Specialists"
    assert team2.paradigm_specialty == "Design Patterns & Polymorphism"

    # 3. Full CouncilInferenceResponse with 7 teams missing paradigm_specialty key
    raw_payload = {
        "selected_template": "software",
        "teams": [
            {"id": "A", "name": "Functional Specialists (Pure Functions, Pipelines)"},
            {"id": "B", "name": "OOP Specialists (Design Patterns)"},
            {"id": "C", "name": "Imperative Specialists (Explicit State)"},
            {"id": "D", "name": "Declarative Specialists (Logic Engines)"},
            {"id": "E", "name": "Dynamic Specialists (Metaprogramming)"},
            {"id": "F", "name": "Auditors (Strategic Alignment)"},
            {"id": "G", "name": "Contrarians (Devil's Advocacy)"}
        ]
    }
    parsed = CouncilInferenceResponse.model_validate(raw_payload)
    assert parsed.selected_template == "software"
    assert len(parsed.teams) == 7
    assert parsed.teams[0].name == "Functional Specialists"
    assert parsed.teams[0].paradigm_specialty == "Pure Functions, Pipelines"





