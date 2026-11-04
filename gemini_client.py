"""The one place that talks to Google's Gemini API. Both the AI tools and the Resume Builder's assistant call
`generate()`, so request building, the model's thinking budget, error handling and the "answer was cut short"
signal are written once and cannot drift apart.

Network or HTTP failures propagate as `requests.RequestException`; an answer that arrives but is empty raises
`EmptyAnswer`. Callers decide how to word each for the user.
"""
from typing import NamedTuple

import requests

from config import Config

ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'


class EmptyAnswer(Exception):
    """Gemini replied, but with no usable text (blocked, or nothing generated)."""


class Reply(NamedTuple):
    text: str
    truncated: bool   # True when the model hit its output limit mid-answer


def generation_config(max_tokens, temperature, thinking_budget=0):
    """Gemini 2.5 "flash" models spend part of maxOutputTokens on hidden thinking, which cut writing answers off
    mid-sentence. So thinking is switched off unless the caller asks for some, and then the thinking tokens are
    added on top of the answer's own budget."""
    config = {'maxOutputTokens': max_tokens, 'temperature': temperature}
    if 'flash' in (Config.GEMINI_MODEL or ''):
        config['thinkingConfig'] = {'thinkingBudget': thinking_budget}
        config['maxOutputTokens'] = max_tokens + thinking_budget
    return config


def generate(system_prompt, messages, max_tokens=1500, temperature=0.6, thinking_budget=0, timeout=45):
    """One Gemini request.

    messages is a list of (role, text) pairs in order, role being 'user' or 'model'. Returns a Reply.
    """
    resp = requests.post(
        ENDPOINT.format(model=Config.GEMINI_MODEL),
        headers={'x-goog-api-key': Config.GEMINI_API_KEY},
        json={
            'system_instruction': {'parts': [{'text': system_prompt}]},
            'contents': [{'role': role, 'parts': [{'text': text}]} for role, text in messages],
            'generationConfig': generation_config(max_tokens, temperature, thinking_budget),
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    candidates = resp.json().get('candidates') or []
    if not candidates:
        raise EmptyAnswer('no candidates')
    parts = (candidates[0].get('content') or {}).get('parts') or []
    text = ''.join(p.get('text', '') for p in parts).strip()
    if not text:
        raise EmptyAnswer('empty text')
    return Reply(text=text, truncated=candidates[0].get('finishReason') == 'MAX_TOKENS')
