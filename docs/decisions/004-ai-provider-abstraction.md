# ADR-004: AI Provider Abstraction

## Status
Accepted

## Context
The platform uses AI for competency extraction, assessment generation, and insight generation. The AI provider may change (OpenAI, Groq, local models, etc.).

## Decision
Create an `AIProvider` abstract interface with an `OpenAICompatibleProvider` implementation. All AI-dependent code depends on the interface, not the provider.

## Alternatives Considered
- **Direct OpenAI SDK usage** — simpler initially, but locks to one provider
- **LangChain** — feature-rich but heavy abstraction layer, introduces significant dependency
- **LiteLLM** — lightweight proxy, but adds another service

## Why Selected
1. Minimal abstraction — only wraps the chat completion endpoint
2. OpenAI-compatible API is a de facto standard supported by most providers
3. Configuration-driven: change provider by updating `AI_BASE_URL` and `AI_MODEL`
4. No heavy framework dependency

## Trade-offs
- Manual implementation of retry/rate-limiting logic
- Provider-specific features (function calling variations) may need adapter code

## Future Migration Path
- Add provider-specific subclasses as needed (e.g., `AnthropicProvider`)
