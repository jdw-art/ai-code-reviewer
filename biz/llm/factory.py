import os

from biz.llm.client.base import BaseClient


class Factory:
    @staticmethod
    def getClient(provider: str = None) -> BaseClient:
        provider = provider or os.getenv("LLM_PROVIDER", "anthropic")
        chat_model_providers = {
            'anthropic': lambda: __import__("biz.llm.client.anthropic", fromlist=["AnthropicClient"]).AnthropicClient(),
            'zhipuai': lambda: __import__("biz.llm.client.zhipuai", fromlist=["ZhipuAIClient"]).ZhipuAIClient(),
            'openai': lambda: __import__("biz.llm.client.openai", fromlist=["OpenAIClient"]).OpenAIClient(),
            'deepseek': lambda: __import__("biz.llm.client.deepseek", fromlist=["DeepSeekClient"]).DeepSeekClient(),
            'qwen': lambda: __import__("biz.llm.client.qwen", fromlist=["QwenClient"]).QwenClient(),
            'ollama': lambda: __import__("biz.llm.client.ollama_client", fromlist=["OllamaClient"]).OllamaClient()
        }

        provider_func = chat_model_providers.get(provider)
        if provider_func:
            return provider_func()
        else:
            raise Exception(f'Unknown chat model provider: {provider}')
