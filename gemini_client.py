"""The one place that talks to Google's Gemini API. Both the AI tools and the Resume Builder's assistant call
`generate()`, so request building, the model's thinking budget, error handling, the fallback model and the
"answer was cut short" signal are written once and cannot drift apart.

Network or HTTP failures propagate as `requests.RequestException`; an answer that arrives but is empty raises
`EmptyAnswer`. Callers decide how to word each for the user.
"""
import time
from typing import NamedTuple

import requests

from config import Config

ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'

# Gemini's free tier answers 429 (over the minute or daily limit for that model) or 503 (model overloaded) now and
# then. Those come back quickly, so they are handled by trying again: on the fallback model when one is set (it has
# its own quota), otherwise on the same model after a short pause. Every attempt shares one total time budget.
RETRY_STATUSES = (429, 500, 502, 503, 504)
RETRY_PAUSE_SECONDS = 2.0


class EmptyAnswer(Exception):
    """Gemini replied, but with no usable text (blocked, or nothing generated)."""


class Reply(NamedTuple):
    text: str
    truncated: bool   # True when the model hit its output limit mid-answer
    model: str = ''   # which model actually answered


def generation_config(max_tokens, temperature, thinking_budget=0, model=None):
    """Gemini 2.5 "flash" models spend part of maxOutputTokens on hidden thinking, which cut writing answers off
    mid-sentence. So thinking is switched off unless the caller asks for some, and then the thinking tokens are
    added on top of the answer's own budget."""
    model = model or Config.GEMINI_MODEL
    config = {'maxOutputTokens': max_tokens, 'temperature': temperature}
    if 'flash' in (model or ''):
        config['thinkingConfig'] = {'thinkingBudget': thinking_budget}
        config['maxOutputTokens'] = max_tokens + thinking_budget
    return config


def _models_to_try():
    models = [Config.GEMINI_MODEL]
    fallback = getattr(Config, 'GEMINI_FALLBACK_MODEL', '') or ''
    if fallback and fallback != Config.GEMINI_MODEL:
        models.append(fallback)
    return models


MIN_ATTEMPT_SECONDS = 4.0


def generate(system_prompt, messages, max_tokens=1500, temperature=0.6, thinking_budget=0, timeout=45):
    """One Gemini request, with a hard overall time limit.

    messages is a list of (role, text) pairs in order, role being 'user' or 'model'. `timeout` is the total
    budget in seconds across every attempt, so a slow or failing model can never hold a request longer than that.
    When a fallback model is set it gets the second attempt (and the first attempt may use only 60% of the budget,
    leaving time for it); with no fallback, a quick failure is retried once on the same model after a short pause.
    Returns a Reply; raises requests.RequestException (including Timeout) or EmptyAnswer.
    """
    def send(model, seconds):
        return requests.post(
            url=ENDPOINT.format(model=model),
            headers={'x-goog-api-key': Config.GEMINI_API_KEY},
            json={
                'system_instruction': {'parts': [{'text': system_prompt}]},
                'contents': [{'role': role, 'parts': [{'text': text}]} for role, text in messages],
                'generationConfig': generation_config(max_tokens, temperature, thinking_budget, model),
            },
            timeout=seconds,
        )

    started = time.monotonic()
    models = _models_to_try()
    attempts = models if len(models) > 1 else [models[0], models[0]]
    resp, last_error, used = None, None, models[0]
    for i, model in enumerate(attempts):
        if i > 0 and len(models) == 1:
            time.sleep(RETRY_PAUSE_SECONDS)
        remaining = timeout - (time.monotonic() - started)
        if remaining < MIN_ATTEMPT_SECONDS:
            break
        last_attempt = i == len(attempts) - 1
        used = model
        try:
            resp = send(model, remaining if last_attempt else remaining * 0.6)
        except (requests.Timeout, requests.ConnectionError) as e:
            resp, last_error = None, e
            continue
        last_error = None
        if getattr(resp, 'status_code', 200) not in RETRY_STATUSES:
            break
    if resp is None:
        raise last_error or requests.Timeout('the AI did not answer within the time limit')
    resp.raise_for_status()
    candidates = resp.json().get('candidates') or []
    if not candidates:
        raise EmptyAnswer('no candidates')
    parts = (candidates[0].get('content') or {}).get('parts') or []
    text = ''.join(p.get('text', '') for p in parts).strip()
    if not text:
        raise EmptyAnswer('empty text')
    return Reply(text=text, truncated=candidates[0].get('finishReason') == 'MAX_TOKENS', model=used)
