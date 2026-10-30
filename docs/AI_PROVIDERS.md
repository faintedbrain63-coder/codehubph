# AI integration maintenance

Official formats and frontier defaults checked on 2026-10-24. Model is a free-text field validated for identifier syntax and length, with no catalogue membership restriction. New connections prefill the provider's frontier default. Saved/custom IDs are preserved; Use frontier default resets the input without saving automatically. Discovery returns model IDs for reference and never changes typed or saved model text. Keep the registry in dashboard/ai/providers.py current as provider APIs change; defaults are verified release choices, not a live auto-upgrade service or a promise of account access.

| Provider | Frontier default | Official model source |
| --- | --- | --- |
| OpenAI | `gpt-6-astra` | [Official OpenAI models](https://developers.openai.com/api/docs/models) |
| Claude | `claude-fable-5-1` | [Claude Fable 5.1](https://platform.claude.com/docs/en/models/fable-5-1/overview) |
| Kimi | `kimi-k3.1-pro` | [Kimi model catalogue](https://platform.kimi.ai/docs/models) |
| DeepSeek | `deepseek-flash` | [Latest V4.1-Flash-1017 release and API alias](https://api-docs.deepseek.com/updates/) |
| OpenRouter | `openai/gpt-6-astra` | [Routed GPT-6 Astra model](https://openrouter.ai/openai/gpt-6-astra) |
| GLM | `glm-5.3` | [Latest GLM flagship](https://docs.z.ai/guides/llm/glm-5.3) |
| MiniMax | `MiniMax-M3.1-Flash` | [MiniMax language models](https://platform.minimax.io/docs/guides/models-intro) |

OpenRouter is a gateway, so its default is a concrete routed frontier model. DeepSeek's newest public generation is V4.1 Flash, served by the stable `deepseek-flash` alias; the older V4 Pro remains available as a manually entered alternative.

| Provider | Base endpoint | Interface | Official reference |
| --- | --- | --- | --- |
| OpenAI | https://api.openai.com/v1 | Responses; GET /models | [Text generation](https://developers.openai.com/api/docs/guides/text), [Models API](https://developers.openai.com/api/reference/resources/models/methods/list) |
| Claude | https://api.anthropic.com/v1 | Messages; GET /models | [API overview](https://platform.claude.com/docs/en/api/overview), [Model IDs](https://platform.claude.com/docs/en/models/overview) |
| Kimi | https://api.moonshot.ai/v1 | Chat Completions; GET /models | [Official quickstart](https://platform.kimi.ai/docs/get-your-api-key), [Model catalogue and retirements](https://platform.kimi.ai/docs/models) |
| DeepSeek | https://api.deepseek.com | Chat Completions; GET /models | [First API call](https://api-docs.deepseek.com/), [Models](https://api-docs.deepseek.com/api/list-models/) |
| OpenRouter | https://openrouter.ai/api/v1 | Chat Completions; GET /models | [Chat](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion), [Models](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties) |
| GLM | https://api.z.ai/api/coding/paas/v4 for GLM-5.3; https://api.z.ai/api/paas/v4 for older model IDs | Chat Completions | [GLM-5.3 endpoint and reasoning requirements](https://docs.z.ai/guides/llm/glm-5.3) |
| MiniMax | https://api.minimax.io/v1 | Chat Completions | [OpenAI-compatible API](https://platform.minimax.io/docs/api-reference/text-openai-api) |

The normal request has no tools and never executes model output. OpenAI uses store=false. Non-streaming requests have connect/read timeouts and a bounded response body. Model list filtering excludes obvious non-text models, but discovery cannot prove every model is usable by every account; test the saved connection. OpenAI GPT-6, routed GPT-6 Astra, Kimi K3.1 and MiniMax-M3.1-Flash use low reasoning effort for bounded administrative replies. GLM-5.3 requires thinking enabled and uses low effort; the old disabled-thinking setting would be rejected. GLM-5.3 routes to its documented coding endpoint, while saved older model IDs retain the original endpoint. Only answer text is rendered; internal reasoning is not displayed. No raw provider errors or response bodies are logged or shown to users.

Keys use authenticated Fernet encryption. By default a purpose-specific key is derived from Django SECRET_KEY. To separate rotation, set AI_CREDENTIAL_ENCRYPTION_KEY to a Fernet key before saving connections. Keep that key stable with database backups. Changing either effective encryption key requires re-entering saved provider credentials; it does not silently decrypt old keys using alternate secrets. The UI never prepopulates or returns the key. Endpoints are server-owned and redirects are rejected.

Chat history is stored in the authenticated server-side session, scoped by user ID, with at most six exchanges. User messages are limited to 3,000 characters; replies are bounded. Failed requests do not append history. App-level busy/rate guards use Django's configured cache (12 requests/minute per staff user). For consistent limits across multiple workers, configure a shared cache; the default local-memory cache only coordinates its own worker. Provider account usage limits remain the spending control.

The assistant receives a freshly read copy of docs/ADMIN_MANUAL.md and freshly queried revenue aggregates on every question. It does not ingest .env, arbitrary repository files, customer notes, names, payment proofs or transaction details. Financial results are also displayed in independent server-backed cards because prompting alone cannot guarantee a model's numerical accuracy. No paid API request is made automatically during deployment or when opening the chat/settings pages.
