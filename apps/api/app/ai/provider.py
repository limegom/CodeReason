from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from .prompts import GRADING_SYSTEM_PROMPT, RUBRIC_SYSTEM_PROMPT
from .schemas import AIAnalysisOutput, RubricParseOutput


class ProviderUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderResult:
    parsed: BaseModel
    provider: str
    requested_model: str
    resolved_model: str
    response_id: str | None
    usage: dict[str, Any]


T = TypeVar("T", bound=BaseModel)


class AnalysisProvider(Protocol):
    async def analyze(self, payload: str) -> ProviderResult: ...

    async def parse_rubric(self, policy_text: str) -> ProviderResult: ...


class OpenAIAnalysisProvider:
    """OpenAI Responses API provider using Pydantic Structured Outputs."""

    def __init__(self, *, api_key: str | None, model: str = "gpt-5.6") -> None:
        if not api_key:
            raise ProviderUnavailableError("OPENAI_API_KEY is not configured")
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self.model = model

    @staticmethod
    def _usage_dict(response: Any) -> dict[str, Any]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        return dict(usage) if isinstance(usage, dict) else {}

    async def _parse(
        self,
        *,
        system_prompt: str,
        user_content: str,
        schema: type[T],
    ) -> ProviderResult:
        try:
            response = await self._client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                text_format=schema,
            )
        except Exception as exc:  # SDK errors are normalized at this boundary.
            raise ProviderUnavailableError(f"OpenAI analysis failed: {type(exc).__name__}") from exc

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ProviderUnavailableError("OpenAI returned no parseable structured output")
        return ProviderResult(
            parsed=parsed,
            provider="openai",
            requested_model=self.model,
            resolved_model=getattr(response, "model", self.model),
            response_id=getattr(response, "id", None),
            usage=self._usage_dict(response),
        )

    async def analyze(self, payload: str) -> ProviderResult:
        return await self._parse(
            system_prompt=GRADING_SYSTEM_PROMPT,
            user_content=payload,
            schema=AIAnalysisOutput,
        )

    async def parse_rubric(self, policy_text: str) -> ProviderResult:
        return await self._parse(
            system_prompt=RUBRIC_SYSTEM_PROMPT,
            user_content=policy_text,
            schema=RubricParseOutput,
        )

