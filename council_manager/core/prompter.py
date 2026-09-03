"""
API Prompter and Response Parsing Module.

Formats structured prompts for specialist personas, manages request payloads, 
handles async HTTP connection routing to Gemini or local Ollama endpoints, 
and parses structured JSON outputs safely.
"""

from typing import (
    List,
    Optional,
    Union,
    Any,
    Type,
    Sequence,
    Iterable,
    Tuple,
    Dict,
    Mapping,
    get_origin,
    get_args,
)
import json
import re
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, model_validator
from council_manager.config import settings

def clean_and_parse_json(text: str) -> dict:
    """Clean common JSON formatting issues from LLM outputs and parse it."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as orig_err:
        # Fallback regex parsing for VoteResponse (allowing truncated rationale quote)
        vote_match = re.search(r'"vote"\s*:\s*"(.*?)"', text, re.DOTALL)
        rationale_match = re.search(r'"rationale"\s*:\s*"(.*)', text, re.DOTALL)
        if vote_match and rationale_match:
            vote_val = vote_match.group(1).strip()
            rationale_val = rationale_match.group(1).strip()
            # Clean trailing quotes/braces/newlines
            while rationale_val.endswith('}') or rationale_val.endswith('"') or rationale_val.endswith('\n') or rationale_val.endswith('\r'):
                if rationale_val.endswith('}'):
                    rationale_val = rationale_val[:-1].strip()
                elif rationale_val.endswith('"'):
                    rationale_val = rationale_val[:-1]
                else:
                    rationale_val = rationale_val.strip()
            return {"vote": vote_val, "rationale": rationale_val}
            
        # Fallback regex parsing for InceptionResponse
        topic_match = re.search(r'"topic"\s*:\s*"(.*?)"', text, re.DOTALL)
        options_match = re.search(r'"options"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if topic_match and options_match:
            topic_val = topic_match.group(1).strip()
            options_val = [opt.strip().strip('"\'') for opt in re.findall(r'"(.*?)"', options_match.group(1))]
            return {"topic": topic_val, "options": options_val}
            
        raise orig_err

class VoteResponse(BaseModel):
    vote: str = Field(description="The exact option selected from the proposal's options")
    rationale: str = Field(description="A concise rationale from your paradigm's perspective")

class InceptionResponse(BaseModel):
    topic: str = Field(description="A concise title/topic for this proposal (maximum 4 words)")
    options: List[str] = Field(description="A list of 2 to 4 structured engineering alternatives/options extracted or derived from the description")

class DeliberationResponse(BaseModel):
    stance: str = Field(description="Strictly either 'FOR' or 'AGAINST'")
    motivation: str = Field(description="A concise summary of why this stance is good or bad from your paradigm's perspective")
    suggestion: str = Field(description="A constructive technical suggestion (if stance is FOR, suggest how implementation could work; if stance is AGAINST, suggest a concrete alternative)")

class OnboardingInferenceResponse(BaseModel):
    global_member_count: int = Field(description="A suggested integer between 5 and 50 representing the global member count for all paradigm teams, based on the project size and complexity.")
    rationale: str = Field(description="A brief explanation of why this member count is appropriate for the described project.")


def format_rationale(rationale: any) -> str:
    from typing import Any
    if isinstance(rationale, dict):
        stance = rationale.get("stance", "UNKNOWN")
        motivation = rationale.get("motivation", "")
        suggestion = rationale.get("suggestion", "")
        
        # Format motivation and suggestion with proper indentation
        indented_motivation = "\n  ".join(motivation.split("\n"))
        indented_suggestion = "\n  ".join(suggestion.split("\n"))
        
        return (
            f"Stance: {stance}\n"
            f"Motivation:\n  {indented_motivation}\n"
            f"Suggestion:\n  {indented_suggestion}"
        )
    return str(rationale)


def get_simple_json_template(
    schema: Union[BaseModel, Type[BaseModel]], max_depth: int = 5
) -> str:
    """Generate a clean JSON template string showing the expected fields and descriptions recursively."""

    def _resolve_field(
        annotation: Any, description: Optional[str] = None, depth: int = 0
    ) -> Any:
        if depth >= max_depth:
            return f"<{description or str(annotation)}>"

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Union:
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return _resolve_field(non_none[0], description, depth)
            elif non_none:
                return _resolve_field(non_none[0], description, depth)

        if origin in (list, List, Sequence, Iterable, tuple, Tuple):
            if args:
                item_template = _resolve_field(args[0], None, depth + 1)
                return [item_template]
            return [f"<{description or 'item'}>"]

        if origin in (dict, Dict, Mapping):
            return {"<key>": f"<{description or 'value'}>"}

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            model_template = {}
            for fname, ffield in annotation.model_fields.items():
                fdesc = ffield.description
                model_template[fname] = _resolve_field(
                    ffield.annotation, fdesc, depth + 1
                )
            return model_template

        desc = description or str(annotation)
        return f"<{desc}>"

    model_cls = schema if isinstance(schema, type) else schema.__class__
    if isinstance(model_cls, type) and issubclass(model_cls, BaseModel):
        template = {}
        for name, field in model_cls.model_fields.items():
            desc = field.description
            template[name] = _resolve_field(field.annotation, desc, depth=1)
        return json.dumps(template, indent=2)
    return "{}"


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

    def probe_connectivity(self) -> None:
        """Probe the connectivity of the LLM endpoint (checks base URL) and raises descriptive errors."""
        import httpx
        from urllib.parse import urlparse
        provider = settings.llm_provider.lower()
        if provider == "google":
            if settings.debug:
                print("[DEBUG] Probing connectivity for Google GenAI provider...")
            try:
                _ = self.client
                if settings.debug:
                    print("[DEBUG] Google GenAI client instantiated successfully.")
            except Exception as e:
                raise RuntimeError(f"Google GenAI initialization failed: {e}")
        else:
            api_base = settings.llm_api_base
            if not api_base:
                if provider == "ollama":
                    api_base = "http://localhost:11434/v1"
                elif provider == "openai":
                    api_base = "https://api.openai.com/v1"
                else:
                    raise ValueError(f"No API base URL configured for provider '{provider}'")
            
            parsed = urlparse(api_base)
            root_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else api_base.rstrip("/")
            
            if settings.debug:
                print(f"[DEBUG] Probing endpoint root connectivity: {root_url}")
            
            try:
                response = httpx.get(root_url, timeout=3.0)
                if settings.debug:
                    print(f"[DEBUG] Probe response from {root_url}: Status {response.status_code}")
            except httpx.RequestError as e:
                raise RuntimeError(
                    f"LLM provider '{provider}' is unreachable. Could not connect to base service at '{root_url}'. "
                    f"Please verify that the service is running and accessible. Error: {e}"
                )
            
            if provider == "ollama":
                tags_url = f"{root_url}/api/tags"
                if settings.debug:
                    print(f"[DEBUG] Checking Ollama available models: {tags_url}")
                try:
                    tags_response = httpx.get(tags_url, timeout=3.0)
                    if tags_response.status_code == 200:
                        data = tags_response.json()
                        available_models = [m.get("name", "") for m in data.get("models", [])]
                        configured_model = settings.gemini_model
                        norm_configured = configured_model.lower()
                        
                        match_found = False
                        for model in available_models:
                            norm_model = model.lower()
                            if norm_model == norm_configured:
                                match_found = True
                                break
                            if ":" in norm_model and norm_model.split(":")[0] == norm_configured:
                                match_found = True
                                break
                            if ":" in norm_configured and norm_configured.split(":")[0] == norm_model.split(":")[0]:
                                match_found = True
                                break
                        
                        if not match_found:
                            raise RuntimeError(
                                f"Ollama is running at '{root_url}', but the configured model '{configured_model}' "
                                f"is not pulled or available. Available models: {available_models}. "
                                f"Please run 'ollama pull {configured_model}' to pull it, or change the model in your .env configuration."
                            )
                except httpx.RequestError as e:
                    if settings.debug:
                        print(f"[DEBUG] Could not query Ollama tags endpoint at '{tags_url}': {e}")

    async def probe_connectivity_async(self) -> None:
        """Probe the connectivity of the LLM endpoint asynchronously."""
        import httpx
        from urllib.parse import urlparse
        provider = settings.llm_provider.lower()
        if provider == "google":
            if settings.debug:
                print("[DEBUG] Probing connectivity for Google GenAI provider (async)...")
            try:
                _ = self.client
                if settings.debug:
                    print("[DEBUG] Google GenAI client instantiated successfully.")
            except Exception as e:
                raise RuntimeError(f"Google GenAI initialization failed: {e}")
        else:
            api_base = settings.llm_api_base
            if not api_base:
                if provider == "ollama":
                    api_base = "http://localhost:11434/v1"
                elif provider == "openai":
                    api_base = "https://api.openai.com/v1"
                else:
                    raise ValueError(f"No API base URL configured for provider '{provider}'")
            
            parsed = urlparse(api_base)
            root_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else api_base.rstrip("/")
            
            if settings.debug:
                print(f"[DEBUG] Probing endpoint root connectivity (async): {root_url}")
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(root_url, timeout=3.0)
                if settings.debug:
                    print(f"[DEBUG] Probe response from {root_url}: Status {response.status_code}")
            except httpx.RequestError as e:
                raise RuntimeError(
                    f"LLM provider '{provider}' is unreachable. Could not connect to base service at '{root_url}'. "
                    f"Please verify that the service is running and accessible. Error: {e}"
                )
            
            if provider == "ollama":
                tags_url = f"{root_url}/api/tags"
                if settings.debug:
                    print(f"[DEBUG] Checking Ollama available models (async): {tags_url}")
                try:
                    async with httpx.AsyncClient() as client:
                        tags_response = await client.get(tags_url, timeout=3.0)
                    if tags_response.status_code == 200:
                        data = tags_response.json()
                        available_models = [m.get("name", "") for m in data.get("models", [])]
                        configured_model = settings.gemini_model
                        norm_configured = configured_model.lower()
                        
                        match_found = False
                        for model in available_models:
                            norm_model = model.lower()
                            if norm_model == norm_configured:
                                match_found = True
                                break
                            if ":" in norm_model and norm_model.split(":")[0] == norm_configured:
                                match_found = True
                                break
                            if ":" in norm_configured and norm_configured.split(":")[0] == norm_model.split(":")[0]:
                                match_found = True
                                break
                        
                        if not match_found:
                            raise RuntimeError(
                                f"Ollama is running at '{root_url}', but the configured model '{configured_model}' "
                                f"is not pulled or available. Available models: {available_models}. "
                                f"Please run 'ollama pull {configured_model}' to pull it, or change the model in your .env configuration."
                            )
                except httpx.RequestError as e:
                    if settings.debug:
                        print(f"[DEBUG] Could not query Ollama tags endpoint at '{tags_url}': {e}")

    def _generate_content_custom(
        self,
        system_instruction: str,
        prompt: str,
        schema: Optional[Union[BaseModel, Type[BaseModel]]] = None,
        temperature: float = 0.7,
    ) -> str:
        import httpx
        provider = settings.llm_provider.lower()
        api_base = settings.llm_api_base
        if not api_base:
            if provider == "ollama":
                api_base = "http://localhost:11434/v1"
            elif provider == "openai":
                api_base = "https://api.openai.com/v1"
            else:
                raise ValueError(f"No API base URL configured for provider '{provider}'")

        url = f"{api_base.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = settings.llm_api_key or settings.gemini_api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": settings.gemini_model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }

        if schema:
            payload["response_format"] = {"type": "json_object"}
            template_json = get_simple_json_template(schema)
            payload["messages"].append({
                "role": "user",
                "content": (
                    f"You must return your response as a raw JSON object conforming strictly to this structure:\n"
                    f"{template_json}\n\n"
                    f"Fill in the field values with your actual responses. Do not include standard JSON schema definitions or keys like 'properties', 'required', 'title', or 'type' in your output."
                )
            })

        if settings.debug:
            print(f"[DEBUG] Custom Provider HTTP Request:")
            print(f"  URL: {url}")
            print(f"  Headers: {headers}")
            print(f"  Payload: {json.dumps(payload, indent=2)}")

        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=settings.llm_timeout)
            if settings.debug:
                print(f"[DEBUG] Custom Provider HTTP Response Status: {response.status_code}")
                print(f"[DEBUG] Custom Provider HTTP Response Content: {response.text}")
            response.raise_for_status()
            res_data = response.json()
            return res_data["choices"][0]["message"]["content"].strip()
        except httpx.RequestError as e:
            if settings.debug:
                print(f"[DEBUG] Custom Provider Request Failed: {e}")
            raise

    async def _generate_content_custom_async(
        self,
        system_instruction: str,
        prompt: str,
        schema: Optional[Union[BaseModel, Type[BaseModel]]] = None,
        temperature: float = 0.7,
    ) -> str:
        import httpx
        provider = settings.llm_provider.lower()
        api_base = settings.llm_api_base
        if not api_base:
            if provider == "ollama":
                api_base = "http://localhost:11434/v1"
            elif provider == "openai":
                api_base = "https://api.openai.com/v1"
            else:
                raise ValueError(f"No API base URL configured for provider '{provider}'")

        url = f"{api_base.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = settings.llm_api_key or settings.gemini_api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": settings.gemini_model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }

        if schema:
            payload["response_format"] = {"type": "json_object"}
            template_json = get_simple_json_template(schema)
            payload["messages"].append({
                "role": "user",
                "content": (
                    f"You must return your response as a raw JSON object conforming strictly to this structure:\n"
                    f"{template_json}\n\n"
                    f"Fill in the field values with your actual responses. Do not include standard JSON schema definitions or keys like 'properties', 'required', 'title', or 'type' in your output."
                )
            })

        if settings.debug:
            print(f"[DEBUG] Custom Provider HTTP Request (async):")
            print(f"  URL: {url}")
            print(f"  Headers: {headers}")
            print(f"  Payload: {json.dumps(payload, indent=2)}")

        try:
            timeout_cfg = httpx.Timeout(settings.llm_timeout, connect=10.0, read=settings.llm_timeout)
            async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                response = await client.post(url, json=payload, headers=headers)
            if settings.debug:
                print(f"[DEBUG] Custom Provider HTTP Response Status: {response.status_code}")
                print(f"[DEBUG] Custom Provider HTTP Response Content: {response.text}")
            response.raise_for_status()
            res_data = response.json()
            return res_data["choices"][0]["message"]["content"].strip()
        except httpx.RequestError as e:
            if settings.debug:
                print(f"[DEBUG] Custom Provider Async Request Failed: {e}")
            raise

    def generate_deliberation(
        self,
        team_name: str,
        paradigm_specialty: str,
        title: str,
        description: str,
        options: List[str]
    ) -> DeliberationResponse:
        """Query target LLM model for a paradigm-based deliberation rationale."""
        system_instruction = (
            f"You are an AI agent representing the '{team_name}' engineering team, "
            f"specializing in '{paradigm_specialty}'. Your goal is to deliberate on technical/architectural "
            f"proposals from your paradigm's viewpoint. Provide a structured deliberation response."
        )

        prompt = (
            f"Please deliberate on the following proposal:\n"
            f"Title: {title}\n"
            f"Description: {description}\n"
            f"Options: {'; '.join(options)}\n\n"
            f"Provide a concise, professional justification of your team's stance. "
            f"Conform strictly to the DeliberationResponse schema."
        )

        if settings.llm_provider.lower() != "google":
            text = self._generate_content_custom(system_instruction, prompt, schema=DeliberationResponse, temperature=0.7)
            return DeliberationResponse(**clean_and_parse_json(text))

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                response_mime_type="application/json",
                response_schema=DeliberationResponse,
            )
        )
        if hasattr(response, "parsed") and response.parsed:
            return response.parsed
        data = clean_and_parse_json(response.text)
        return DeliberationResponse(**data)

    def generate_vote(
        self,
        team_name: str,
        paradigm_specialty: str,
        title: str,
        description: str,
        options: List[str],
        rationales_context: str
    ) -> VoteResponse:
        """Query target LLM model to cast a blind vote, using structured Pydantic response schemas."""
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

        if settings.llm_provider.lower() != "google":
            text = self._generate_content_custom(system_instruction, prompt, schema=VoteResponse, temperature=0.2)
            return VoteResponse(**clean_and_parse_json(text))

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
        data = clean_and_parse_json(response.text)
        return VoteResponse(**data)

    async def generate_deliberation_async(
        self,
        team_name: str,
        paradigm_specialty: str,
        title: str,
        description: str,
        options: List[str]
    ) -> DeliberationResponse:
        """Query target LLM model asynchronously for a paradigm-based deliberation rationale."""
        system_instruction = (
            f"You are an AI agent representing the '{team_name}' engineering team, "
            f"specializing in '{paradigm_specialty}'. Your goal is to deliberate on technical/architectural "
            f"proposals from your paradigm's viewpoint. Provide a structured deliberation response."
        )

        prompt = (
            f"Please deliberate on the following proposal:\n"
            f"Title: {title}\n"
            f"Description: {description}\n"
            f"Options: {'; '.join(options)}\n\n"
            f"Provide a concise, professional justification of your team's stance. "
            f"Conform strictly to the DeliberationResponse schema."
        )

        if settings.llm_provider.lower() != "google":
            text = await self._generate_content_custom_async(system_instruction, prompt, schema=DeliberationResponse, temperature=0.7)
            return DeliberationResponse(**clean_and_parse_json(text))

        response = await self.client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                response_mime_type="application/json",
                response_schema=DeliberationResponse,
            )
        )
        if hasattr(response, "parsed") and response.parsed:
            return response.parsed
        data = clean_and_parse_json(response.text)
        return DeliberationResponse(**data)

    async def generate_vote_async(
        self,
        team_name: str,
        paradigm_specialty: str,
        title: str,
        description: str,
        options: List[str],
        rationales_context: str
    ) -> VoteResponse:
        """Query target LLM model asynchronously to cast a blind vote, using structured Pydantic response schemas."""
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

        if settings.llm_provider.lower() != "google":
            text = await self._generate_content_custom_async(system_instruction, prompt, schema=VoteResponse, temperature=0.2)
            return VoteResponse(**clean_and_parse_json(text))

        response = await self.client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=VoteResponse,
            )
        )
        
        if hasattr(response, "parsed") and response.parsed:
            return response.parsed
            
        data = clean_and_parse_json(response.text)
        return VoteResponse(**data)

    def generate_proposal_inception(self, description: str) -> InceptionResponse:
        """Query target LLM model to extract topic and options from description."""
        system_instruction = (
            "You are an AI assistant designed to bootstrap project decisions. "
            "Given a proposal description, you must generate a concise topic title (maximum 4 words) "
            "and extract/extrapolate a list of 2 to 4 structured, mutually exclusive engineering options/alternatives."
        )

        prompt = (
            f"Please bootstrap the following proposal description:\n"
            f"Description: {description}\n\n"
            f"Return a structured JSON containing the topic title and options."
        )

        if settings.llm_provider.lower() != "google":
            text = self._generate_content_custom(system_instruction, prompt, schema=InceptionResponse, temperature=0.2)
            return InceptionResponse(**clean_and_parse_json(text))

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=InceptionResponse,
            )
        )

        if hasattr(response, "parsed") and response.parsed:
            return response.parsed

        data = clean_and_parse_json(response.text)
        return InceptionResponse(**data)

    async def generate_proposal_inception_async(self, description: str) -> InceptionResponse:
        """Query target LLM model asynchronously to extract topic and options."""
        system_instruction = (
            "You are an AI assistant designed to bootstrap project decisions. "
            "Given a proposal description, you must generate a concise topic title (maximum 4 words) "
            "and extract/extrapolate a list of 2 to 4 structured, mutually exclusive engineering options/alternatives."
        )

        prompt = (
            f"Please bootstrap the following proposal description:\n"
            f"Description: {description}\n\n"
            f"Return a structured JSON containing the topic title and options."
        )

        if settings.llm_provider.lower() != "google":
            text = await self._generate_content_custom_async(system_instruction, prompt, schema=InceptionResponse, temperature=0.2)
            return InceptionResponse(**clean_and_parse_json(text))

        response = await self.client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=InceptionResponse,
            )
        )

        if hasattr(response, "parsed") and response.parsed:
            return response.parsed

        data = clean_and_parse_json(response.text)
        return InceptionResponse(**data)

    def infer_global_member_count(self, description: str) -> OnboardingInferenceResponse:
        """Query target LLM model to suggest a global member count for the project based on its description."""
        system_instruction = (
            "You are an AI assistant designed to bootstrap project councils. "
            "Given a project description, you must suggest a single global member count/weight (an integer between 5 and 50, usually 10 for standard projects, 20-30 for large or complex projects) "
            "that will be applied to all 7 active paradigm teams (A-G)."
        )

        prompt = (
            f"Please suggest a global member count for the following project description:\n"
            f"Description: {description}\n\n"
            f"Return a structured JSON containing the suggested global_member_count and a brief rationale."
        )

        if settings.llm_provider.lower() != "google":
            text = self._generate_content_custom(system_instruction, prompt, schema=OnboardingInferenceResponse, temperature=0.2)
            return OnboardingInferenceResponse(**clean_and_parse_json(text))

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=OnboardingInferenceResponse,
            )
        )

        if hasattr(response, "parsed") and response.parsed:
            return response.parsed

        data = clean_and_parse_json(response.text)
        return OnboardingInferenceResponse(**data)

    def infer_project_council(self, description: str) -> "CouncilInferenceResponse":
        """Query target LLM model to suggest a customized council of 7 teams based on the project description."""
        system_instruction = (
            "You are an AI assistant designed to bootstrap project councils. "
            "Given a project description, you must classify the project and define a council of exactly 7 teams (A to G) that are best suited to govern this project.\n\n"
            "Your response must be a JSON object containing:\n"
            "- selected_template: 'software', 'education', 'marketing', 'general', or 'custom'.\n"
            "- teams: A list of exactly 7 team objects.\n\n"
            "Each team object in the 'teams' list MUST contain:\n"
            "- 'id': The team ID, exactly one of: 'A', 'B', 'C', 'D', 'E', 'F', 'G'.\n"
            "- 'name': The name of the team (e.g. 'Functional Specialists').\n"
            "- 'paradigm_specialty': The paradigm specialty and focus area (e.g. 'Functional Programming, Immutability').\n\n"
            "Team Constraints:\n"
            "- Team F must always represent the Auditors/Project Managers (focused on strategic alignment, quality assurance, requirement tracking, and auditing).\n"
            "- Team G must always represent the Contrarians (focused on devil's advocacy, design friction, and critical analysis of assumptions).\n"
            "- Teams A, B, C, D, E should represent the key specialist paradigms for the domain.\n\n"
            "Example Team Configurations:\n"
            "- For 'software':\n"
            "  A: name='Functional Specialists', paradigm_specialty='Functional Programming, Immutability'\n"
            "  B: name='OOP Specialists', paradigm_specialty='Object-Oriented Programming, Design Patterns'\n"
            "  C: name='Imperative Specialists', paradigm_specialty='Explicit State, Procedural logic'\n"
            "  D: name='Declarative Specialists', paradigm_specialty='Logic engines, Config-driven, DSLs'\n"
            "  E: name='Dynamic Specialists', paradigm_specialty='Reflection, Metaprogramming'\n"
            "- For 'education' (curriculum, teaching, pedagogy):\n"
            "  A: name='Pedagogy Specialists', paradigm_specialty='Learning theories, student needs'\n"
            "  B: name='Curriculum Setters', paradigm_specialty='Subject matter experts, syllabus design'\n"
            "  C: name='Assessment Designers', paradigm_specialty='Testing, grading rubrics, evaluations'\n"
            "  D: name='Instructional Technology Specialists', paradigm_specialty='E-learning, digital tools'\n"
            "  E: name='Student Experience Designers', paradigm_specialty='Engagement, accessibility, student feedback'\n"
            "- For 'marketing' (campaigns, branding, growth):\n"
            "  A: name='Brand Strategists', paradigm_specialty='Brand identity, positioning'\n"
            "  B: name='Copywriters & Content Creators', paradigm_specialty='Messaging, creative writing'\n"
            "  C: name='Media Buyers & Analysts', paradigm_specialty='Ad spend, ROI, channel selection'\n"
            "  D: name='SEO & Growth Engineers', paradigm_specialty='Conversion rate, traffic, search optimization'\n"
            "  E: name='Public Relations Specialists', paradigm_specialty='Press, community engagement'\n"
            "- For 'general' (business operations, general projects):\n"
            "  A: name='Strategy & Finance', paradigm_specialty='Planning, budgeting, ROI'\n"
            "  B: name='Operations & Execution', paradigm_specialty='Process efficiency, delivery'\n"
            "  C: name='Customer Experience', paradigm_specialty='User feedback, support, retention'\n"
            "  D: name='Compliance & Legal', paradigm_specialty='Regulatory, risk management, contracts'\n"
            "  E: name='Human Resources & Talent', paradigm_specialty='Team culture, staffing, training'"
        )

        prompt = (
            f"Please suggest a project-specific council for the following project description:\n"
            f"Description: {description}\n\n"
            f"Return a structured JSON containing the 'selected_template' and the 'teams' list of 7 team objects, each with 'id', 'name', and 'paradigm_specialty'."
        )

        if settings.llm_provider.lower() != "google":
            text = self._generate_content_custom(system_instruction, prompt, schema=CouncilInferenceResponse, temperature=0.2)
            return CouncilInferenceResponse(**clean_and_parse_json(text))

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=CouncilInferenceResponse,
            )
        )

        if hasattr(response, "parsed") and response.parsed:
            return response.parsed

        data = clean_and_parse_json(response.text)
        return CouncilInferenceResponse(**data)


class TeamInference(BaseModel):
    id: str = Field(description="The team ID, which must be exactly one of: 'A', 'B', 'C', 'D', 'E', 'F', 'G'")
    name: str = Field(description="The name of the team (e.g. 'Pedagogy Specialists', 'Curriculum Setters')")
    paradigm_specialty: str = Field(default="", description="The team's paradigm specialty and focus area (e.g. 'Learning theories, student needs')")

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Check for alternative field keys
            if not data.get("paradigm_specialty"):
                if data.get("specialty"):
                    data["paradigm_specialty"] = data["specialty"]
                elif data.get("paradigm"):
                    data["paradigm_specialty"] = data["paradigm"]
                elif data.get("focus"):
                    data["paradigm_specialty"] = data["focus"]
                elif data.get("name") and isinstance(data["name"], str):
                    # Check if name is formatted as "Name (Specialty)"
                    match = re.match(r"^([^(]+)\(([^)]+)\)$", data["name"].strip())
                    if match:
                        data["name"] = match.group(1).strip()
                        data["paradigm_specialty"] = match.group(2).strip()
                    else:
                        data["paradigm_specialty"] = data["name"]
        return data


class CouncilInferenceResponse(BaseModel):
    selected_template: str = Field(description="The matching template name: 'software', 'education', 'marketing', 'general', or 'custom'")
    teams: List[TeamInference] = Field(description="A list of exactly 7 teams (A to G). F must be the Auditors/Project Managers, G must be the Contrarians.")



