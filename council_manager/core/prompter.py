from typing import List, Dict, Any, Optional
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from council_manager.config import settings

class VoteResponse(BaseModel):
    vote: str = Field(description="The exact option selected from the proposal's options")
    rationale: str = Field(description="A concise rationale from your paradigm's perspective")

class AgentPrompter:
    def __init__(self, client: Optional[genai.Client] = None):
        self._client = client

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            # genai.Client automatically reads GEMINI_API_KEY from environment
            # if settings.gemini_api_key is not configured
            api_key = settings.gemini_api_key
            if api_key:
                self._client = genai.Client(api_key=api_key)
            else:
                self._client = genai.Client()
        return self._client

    def generate_deliberation(
        self,
        team_name: str,
        paradigm_specialty: str,
        title: str,
        description: str,
        options: List[str]
    ) -> str:
        """Query Gemini model for a paradigm-based deliberation rationale."""
        system_instruction = (
            f"You are an AI agent representing the '{team_name}' engineering team, "
            f"specializing in '{paradigm_specialty}'. Your goal is to deliberate on technical/architectural "
            f"proposals from your paradigm's viewpoint. Provide clear, rigorous justifications."
        )

        prompt = (
            f"Please deliberate on the following proposal:\n"
            f"Title: {title}\n"
            f"Description: {description}\n"
            f"Options: {'; '.join(options)}\n\n"
            f"Provide a concise, professional justification of your team's stance. "
            f"Focus strictly on how the proposal affects your team's paradigm and domain of expertise."
        )

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
            )
        )
        return response.text.strip()

    def generate_vote(
        self,
        team_name: str,
        paradigm_specialty: str,
        title: str,
        description: str,
        options: List[str],
        rationales_context: str
    ) -> VoteResponse:
        """Query Gemini model to cast a blind vote, using structured Pydantic response schemas."""
        system_instruction = (
            f"You are an AI agent representing the '{team_name}' engineering team, "
            f"specializing in '{paradigm_specialty}'. Your goal is to vote on technical/architectural "
            f"proposals from your paradigm's viewpoint. Cast a blind vote without seeing how other teams voted."
        )

        prompt = (
            f"Please cast your blind vote on the following proposal:\n"
            f"Title: {title}\n"
            f"Description: {description}\n"
            f"Options: {'; '.join(options)}\n\n"
            f"Here are the deliberation rationales written by all teams (including yours):\n"
            f"{rationales_context}\n\n"
            f"Cast your final blind vote. You must select exactly one of the options. "
            f"Return your selection and voting rationale."
        )

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=VoteResponse,
            )
        )
        
        # If response.parsed is available in google-genai, it returns the parsed model instance
        if hasattr(response, "parsed") and response.parsed:
            return response.parsed
            
        # Fallback to parsing raw text if parsed is empty
        data = json.loads(response.text)
        return VoteResponse(**data)
