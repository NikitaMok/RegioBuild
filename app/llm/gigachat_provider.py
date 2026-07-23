from __future__ import annotations

from loguru import logger
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.llm.base import DEFAULT_MAX_TOKENS, LLMProvider, LLMProviderError


def _is_retryable_gigachat_error(exc: BaseException) -> bool:
    """401/403 не ретраим — credentials/права не «починятся» за 3 попытки."""
    if not isinstance(exc, LLMProviderError):
        return True
    text = str(exc).lower()
    if "401" in text or "403" in text or "credentials" in text or "doesn't match" in text:
        return False
    return True


class GigaChatProvider(LLMProvider):
    name = "gigachat"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gigachat_credentials:
            raise LLMProviderError(
                "GIGACHAT_CREDENTIALS не задан в .env. Ключ авторизации выдаётся в личном "
                "кабинете https://developers.sber.ru/portal/products/gigachat-api"
            )
        self._credentials = settings.gigachat_credentials
        self._scope = settings.gigachat_scope
        self._model = settings.gigachat_model
        self._base_url = settings.gigachat_base_url
        self._verify_ssl_certs = settings.gigachat_verify_ssl_certs

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception(_is_retryable_gigachat_error),
    )
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        from gigachat import GigaChat
        from gigachat.models import Chat, Messages, MessagesRole

        try:
            client_kwargs: dict = {
                "credentials": self._credentials,
                "scope": self._scope,
                "model": self._model,
                "verify_ssl_certs": self._verify_ssl_certs,
            }
            if self._base_url:
                client_kwargs["base_url"] = self._base_url
            with GigaChat(**client_kwargs) as client:
                chat = Chat(
                    messages=[
                        Messages(role=MessagesRole.SYSTEM, content=system_prompt),
                        Messages(role=MessagesRole.USER, content=user_prompt),
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                response = client.chat(chat)
                self._observe_usage(response)
                return response.choices[0].message.content
        except LLMProviderError:
            raise
        except Exception as exc:
            logger.error(f"GigaChat API вернул ошибку: {exc}")
            from app.core.metrics import LLM_REQUESTS

            LLM_REQUESTS.labels(provider=self.name, outcome="error").inc()
            raise LLMProviderError(str(exc)) from exc

    def _observe_usage(self, response: object) -> None:
        """Токены из usage → Prometheus; экономика запроса видна в /metrics."""
        try:
            from app.core.metrics import LLM_REQUESTS, observe_llm_usage

            LLM_REQUESTS.labels(provider=self.name, outcome="ok").inc()
            usage = getattr(response, "usage", None)
            if usage is not None:
                observe_llm_usage(
                    self.name,
                    getattr(usage, "prompt_tokens", None),
                    getattr(usage, "completion_tokens", None),
                )
        except Exception as exc:  # noqa: BLE001 — метрики не должны ронять ответ
            logger.debug(f"usage metrics skip: {exc}")
