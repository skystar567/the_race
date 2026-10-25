"""One DeepSeek Responses entry point, shared by workers and learning features."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any

import httpx


class ModelError(Exception):
    """A safe, classified failure; never persist upstream bodies or credentials."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def load_env(path: Path) -> None:
    """Read optional backend configuration without overriding process settings."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() in {"DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"}:
            os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def output_text(response: dict[str, Any]) -> str:
    """Accept final assistant text only; discard reasoning and tool items."""
    if response.get("status") == "incomplete":
        raise ModelError("truncated", "模型输出被截断，请缩小整理范围后重试。")
    if response.get("status") != "completed":
        raise ModelError("failed", "模型未正常完成请求。")
    text = "".join(
        part.get("text", "")
        for item in response.get("output", [])
        if item.get("type") == "message" and item.get("role", "assistant") == "assistant"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )
    if not text.strip():
        raise ModelError("empty_output", "模型没有返回可用正文。")
    return text


@dataclass
class DeepSeek:
    """Stateless Responses client. Keys stay in the backend process."""

    api_key: str = field(default="", repr=False)
    base_url: str = "https://api.deepseek.com"
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)
    timeout: float = 180.0

    @classmethod
    def from_environment(cls) -> "DeepSeek":
        """Load local configuration for a server or worker process."""
        load_env(Path(__file__).resolve().parent.parent / ".env")
        return cls(os.getenv("DEEPSEEK_API_KEY", ""), os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))

    def payload(self, instructions: str, content: Any, *, thinking: bool, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build requests without enabling tools, remote storage, or fallback models."""
        if not self.api_key:
            raise ModelError("configuration", "后端尚未配置 DEEPSEEK_API_KEY；请配置后重试。")
        payload: dict[str, Any] = {
            "model": "deepseek-flash", "instructions": instructions,
            "input": json.dumps(content, ensure_ascii=False),
            "reasoning": {"effort": "high" if thinking else "none"},
            "max_output_tokens": 16384 if thinking else 8192,
        }
        if schema is not None:
            payload["text"] = {"format": {"type": "json_schema", "name": "course_output", "schema": schema}}
        return payload

    @staticmethod
    def check_status(response: httpx.Response) -> None:
        """Classify HTTP failures without reflecting sensitive upstream content."""
        if response.status_code < 400:
            return
        status = response.status_code
        if status in {401, 403}:
            raise ModelError("authentication", "模型凭据无效或没有调用权限。")
        if status in {408, 429} or status >= 500:
            raise ModelError("temporary", f"模型服务暂时不可用（{status}）。", True)
        raise ModelError("request", f"模型请求被拒绝（{status}），请检查配置与请求范围。")

    async def complete(self, instructions: str, content: Any, schema: dict[str, Any], *, thinking: bool = True) -> dict[str, Any]:
        """Return JSON output; business validation is an additional required step."""
        payload = self.payload(instructions, content, thinking=thinking, schema=schema)
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
                response = await client.post(self.base_url.rstrip("/") + "/responses", headers={"Authorization": f"Bearer {self.api_key}"}, json=payload)
                self.check_status(response)
                result = json.loads(output_text(response.json()))
        except httpx.TransportError as exc:
            raise ModelError("network", "模型连接中断或超时，可稍后重试。", True) from exc
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise ModelError("invalid_output", "模型返回的结构无法解析。") from exc
        if not isinstance(result, dict):
            raise ModelError("invalid_output", "模型输出必须是 JSON 对象。")
        return result

    async def stream(self, instructions: str, content: Any) -> AsyncIterator[str]:
        """Yield visible text only, requiring a valid terminal Responses SSE event."""
        payload = self.payload(instructions, content, thinking=False)
        payload["stream"] = True
        terminal = False
        collected = ""
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
                async with client.stream("POST", self.base_url.rstrip("/") + "/responses", headers={"Authorization": f"Bearer {self.api_key}"}, json=payload) as response:
                    self.check_status(response)
                    event_lines: list[str] = []
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            event_lines.append(line[5:].lstrip())
                        elif not line and event_lines:
                            event = json.loads("\n".join(event_lines))
                            event_lines = []
                            kind = event.get("type")
                            if kind == "response.output_text.delta":
                                delta = event.get("delta", "")
                                if not isinstance(delta, str):
                                    raise ModelError("invalid_output", "流式正文格式无效。")
                                collected += delta
                                yield delta
                            elif kind in {"response.completed", "response.incomplete", "response.failed"}:
                                final = output_text(event.get("response", {}))
                                if collected and collected != final:
                                    raise ModelError("invalid_output", "流式正文与最终结果不一致。")
                                if not collected:
                                    yield final
                                terminal = True
                                break
        except httpx.TransportError as exc:
            raise ModelError("network", "回答连接中断，已显示的内容尚未完成。", True) from exc
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise ModelError("invalid_output", "流式模型事件无法解析。") from exc
        if not terminal:
            raise ModelError("interrupted", "模型连接结束，但没有收到完成事件。")
