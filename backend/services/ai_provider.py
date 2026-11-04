"""One explicitly selected provider for every paid text/vision request. No retries or upgrades."""
from __future__ import annotations

import base64
import json
import math
import os
import uuid
import hashlib
import threading
import request_context
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

import httpx
from pydantic import ValidationError
from security.secrets import read_secret, write_secret
from .ai_budget import BudgetLedger, DEFAULT_LIMITS, token_cost

DEFAULT_MODEL = "gpt-6-luna"
PREPARATION_MODEL = "gpt-6.1-sol"
PREPARATION_REASONING = "high"
PREPARATION_READ_TIMEOUT = 600
GOOGLE_TEXT_MODEL = "gemini-3.5-flash-lite"
_generation_scope = ContextVar("generation_scope", default=None)
_request_identity = ContextVar("generation_request_identity", default=None)
_provider_override = ContextVar('generation_provider_override',default=None)
_preparing_lesson = ContextVar('preparing_lesson', default=False)
_reading_handwriting = ContextVar('reading_handwriting', default=False)


class StructuredResponseError(ValueError):
    """A paid, cached response cannot be used safely as the requested structure."""


class InvalidStructuredResponseError(StructuredResponseError):
    """A complete saved reply failed validation, rather than an unknown transport outcome."""


class UnusableResponseError(StructuredResponseError):
    def __init__(self,outcome):
        self.code=outcome.get('code','provider_incomplete')
        self.request_id=outcome['request_id']
        messages={
            'provider_empty':'The provider returned no lesson content.',
            'provider_length_limit':'The provider stopped at its output limit before finishing.',
            'provider_refusal':'The provider declined this request; the source needs review.',
            'provider_failed':'The provider reported a generation failure.',
            'provider_incomplete':'The provider did not finish its reply.',
        }
        super().__init__(messages.get(self.code,messages['provider_incomplete'])+' The outcome is saved; an ordinary retry will not purchase it again.')


class ContentRejectedError(ValueError):
    """Known provider content refusal; device speech can read the original text."""


class RateLimitError(ValueError):
    def __init__(self, retry_after=60, provider_code=None, provider_type=None):
        quota = provider_code in ('insufficient_quota','billing_hard_limit_reached','credit_balance_exhausted') or provider_type == 'insufficient_quota'
        self.code = 'provider_quota' if quota else 'provider_rate_limit' if provider_code=='rate_limit_exceeded' or provider_type=='rate_limit_exceeded' else 'provider_429'
        message = ('The script provider has no available API credits or quota. Restore its API billing credit or quota before retrying; waiting will not fix this. Saved work is kept.' if self.code=='provider_quota'
            else f'The script provider is temporarily limiting requests. Try again after {math.ceil(retry_after)} seconds; the saved script is kept.' if self.code=='provider_rate_limit'
            else "AI provider returned 429. Check the provider's quota and billing; try again later.")
        super().__init__(message)
        self.retry_after = retry_after


def validated(text, schema):
    if not schema:
        return text.strip()
    try:
        return schema.model_validate_json(text).model_dump(by_alias=True)
    except ValidationError as exc:
        # Only lesson plans opt into duplicate-output recovery. Assessments and
        # source checks retain their strict validation; never choose between replies.
        recover = getattr(schema, "recover_duplicate_response", None)
        if recover:
            recovered = recover(text)
            if recovered is not None:
                return recovered
        raise InvalidStructuredResponseError("The AI response did not match the requested structure. Saved work is safe; the response is cached and no automatic retry was sent.") from exc


def provider_schema(schema,provider=None):
    if provider=='google' and hasattr(schema,'google_json_schema'):
        return schema.google_json_schema()
    custom=getattr(schema,'provider_json_schema',None)
    return custom() if custom else schema.model_json_schema(by_alias=True)


def strict_schema(schema):
    """OpenAI requires all properties (nullable defaults included) and closed objects."""
    value = provider_schema(schema)
    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            node.pop("default", None)
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(value)
    return value


class AIService:
    def __init__(self, ctx, http=None):
        self.ctx = ctx
        self.http = http or httpx.Client(timeout=180)
        self.ledger = BudgetLedger(ctx.config.dir / "ai-usage.sqlite3")
        self._cache_lock = threading.RLock()
        self._input_locks = {}

    @contextmanager
    def identified(self, identity):
        """A durable logical job keeps its provider request identity across HTTP retries."""
        token = _request_identity.set(identity)
        try:
            yield
        finally:
            _request_identity.reset(token)

    @contextmanager
    def scoped(self, scope_id):
        token = _generation_scope.set(scope_id)
        try:
            yield
        finally:
            _generation_scope.reset(token)

    @property
    def settings(self):
        return self.ctx.config.get("ai", {})

    @property
    def limits(self):
        # Kept as an adapter for callers saved before spending became tracking-only.
        return {}

    def selection(self):
        provider = _provider_override.get() or self.settings.get("provider", "openai")
        if provider == "openai":
            return provider, PREPARATION_MODEL if _preparing_lesson.get() or _reading_handwriting.get() else DEFAULT_MODEL
        if provider == "google":
            return provider, GOOGLE_TEXT_MODEL
        raise ValueError("Choose a supported teaching provider in Settings")

    @contextmanager
    def preparing_lesson(self):
        """Spend reasoning on occasional preparation, without upgrading live feedback."""
        token = _preparing_lesson.set(True)
        try:
            yield
        finally:
            _preparing_lesson.reset(token)

    @contextmanager
    def reading_handwriting(self):
        """Copy a child's handwriting with the careful model, briefly reasoning.

        The quick model tends to 'fix' a misspelt word into the printed word
        beside it, which hides the very mistake the check is looking for.
        """
        token = _reading_handwriting.set(True)
        try:
            yield
        finally:
            _reading_handwriting.reset(token)

    @contextmanager
    def using_provider(self,provider=None):
        if provider not in (None,'configured','openai','google'):
            raise ValueError('Choose a supported teaching provider')
        token=_provider_override.set(None if provider=='configured' else provider)
        try:yield
        finally:_provider_override.reset(token)

    def key(self, provider):
        value = read_secret(self.ctx.config.secrets_dir / f"{provider}-api-key")
        names = {"openai":"OPENAI_API_KEY", "google":"GEMINI_API_KEY", "elevenlabs":"ELEVENLABS_API_KEY",
                 "inworld":"INWORLD_API_KEY"}
        if provider not in names:
            return None
        key = value.decode() if value else os.getenv(names[provider], "")
        return key if key and key != "your_key_here" else None

    def save_key(self, provider, key):
        if provider not in ("openai", "google", "elevenlabs", "inworld") or len(key.strip()) < 15 or any(c.isspace() for c in key.strip()):
            raise ValueError("Enter a valid API key")
        write_secret(self.ctx.config.secrets_dir / f"{provider}-api-key", key.strip().encode())

    def rates(self, provider, model):
        if provider == "openai" and model == PREPARATION_MODEL:
            return Decimal("2.00"), Decimal("10.00")
        if provider == "openai" and model == DEFAULT_MODEL:
            return Decimal("0.10"), Decimal("0.50")
        if provider == "google" and model == GOOGLE_TEXT_MODEL:
            return Decimal("0.30"), Decimal("2.50")
        raise ValueError("This model has no approved price; no request sent")

    def _post(self, url, headers, body, request_id=None):
        try:
            # Preparation runs in a background job. A reasoning model can need
            # more than three minutes to finish a structured visual lesson;
            # keep ordinary tutoring requests on their existing timeout.
            options = ({'timeout': httpx.Timeout(PREPARATION_READ_TIMEOUT, connect=30, write=120, pool=30)}
                       if _preparing_lesson.get() and request_id else {})
            response = self.http.post(url, headers=headers, json=body, **options)
        except httpx.ReadTimeout as exc:
            if request_id:
                self.ledger.mark(request_id, "uncertain")
            raise ValueError("The AI did not finish before the connection timeout. Its outcome is unknown; "
                             "the spending reservation is kept and no automatic retry was sent.") from exc
        except Exception as exc:
            if request_id:
                self.ledger.mark(request_id, "uncertain")
            raise ValueError("The AI connection failed. Saved work is safe; any sent request remains reserved.") from exc
        if response.status_code >= 400:
            if request_id:
                self.ledger.mark(request_id, "rejected" if response.status_code in (400, 401, 402, 403, 404, 429) else "uncertain")
            detail = {401: "Check the API key on the home server.", 402: "Restore prepaid billing before trying again.",
                      403: "Check key permissions and billing.", 429: "Check the provider's quota and billing; try again later."}.get(response.status_code, "Check provider availability and request support.")
            if response.status_code == 429:
                try:
                    delay = float(response.headers.get("retry-after", "60"))
                    if not 1 <= delay <= 120:
                        delay = 60
                except ValueError:
                    delay = 60
                try:
                    error=response.json().get('error',{})
                    provider_code=error.get('code') if isinstance(error,dict) else None
                    provider_type=error.get('type') if isinstance(error,dict) else None
                except (ValueError,AttributeError):
                    provider_code=None
                    provider_type=None
                raise RateLimitError(delay,provider_code,provider_type)
            if response.status_code == 400 and "generativelanguage.googleapis.com" in url:
                # Classify known refusals without returning upstream text, which
                # can echo original book content, credentials or child evidence.
                try:
                    error = response.json().get("error", {})
                    wording = str(error.get("message", "")).lower()
                except (ValueError, AttributeError):
                    wording = ""
                if any(word in wording for word in ("copyright", "recitation")):
                    detail = "Google declined this passage under its copyright controls. Saved passages remain available; use device speech for this part."
                    raise ContentRejectedError(detail)
                elif any(word in wording for word in ("safety", "unsafe", "prohibited", "blocked", "sensitive")):
                    detail = "Google declined this passage under its content filters. Saved passages remain available; use device speech for this part."
                    raise ContentRejectedError(detail)
            # Never expose upstream bodies, which can echo credentials or child data.
            raise ValueError(f"AI provider returned {response.status_code}. {detail}")
        try:
            return response.json()
        except ValueError as exc:
            if request_id:
                self.ledger.mark(request_id, "uncertain")
            raise ValueError("The provider returned unreadable data; any sent request stays reserved.") from exc

    def generate(self, prompt, *, schema=None, images=(), pdf=None, instructions="", category="teaching", max_output=4096, replace_invalid=False):
        cache_id = self.cache_id(prompt, schema=schema, images=images, pdf=pdf, instructions=instructions,
                                 category=category, max_output=max_output)
        with self._cache_lock:
            input_lock = self._input_locks.setdefault(cache_id, threading.RLock())
        with input_lock:
            return self._cached_or_generate(cache_id,prompt,schema=schema,images=images,pdf=pdf,instructions=instructions,
                category=category,max_output=max_output,replace_invalid=replace_invalid)

    def cache_id(self, prompt, *, schema=None, images=(), pdf=None, instructions="", category="teaching", max_output=4096):
        provider, model = self.selection()
        # Reuse only an identical complete input, including source/context, schema and media.
        identity = json.dumps(["exact-input-v1", provider, model, category, prompt, instructions,
                               provider_schema(schema,provider) if schema else None, max_output,
                               [hashlib.sha256(data).hexdigest() + mime for data, mime in images],
                               hashlib.sha256(pdf).hexdigest() if pdf else None], sort_keys=True)
        return "cache:" + hashlib.sha256(identity.encode()).hexdigest()

    def has_valid_cached_reply(self,prompt,**kwargs):
        """A complete exact-input response can be revalidated without a purchase."""
        cached=self.ledger.result(self.cache_id(prompt,**kwargs))
        if cached is None:return False
        try:validated(cached,kwargs.get('schema'));return True
        except ValueError:return False

    def has_invalid_cached_reply(self,prompt,**kwargs):
        """Inspect only the exact saved complete reply; never send a request."""
        cached=self.ledger.result(self.cache_id(prompt,**kwargs))
        if cached is None:return False
        try:validated(cached,kwargs.get('schema'))
        except InvalidStructuredResponseError:
            replacement_id='replacement:'+hashlib.sha256(json.dumps([
                self.cache_id(prompt,**kwargs),hashlib.sha256(cached.encode()).hexdigest(),'format-recovery-v1']).encode()).hexdigest()
            replacement=self.ledger.result(replacement_id)
            if replacement is not None:
                try:validated(replacement,kwargs.get('schema'));return False
                except InvalidStructuredResponseError:pass
            return True
        return False

    def cached_failure(self,prompt,**kwargs):
        outcome=self.ledger.outcome(self.cache_id(prompt,**kwargs))
        if outcome and outcome.get('code'):
            replacement_id='replacement:'+hashlib.sha256(json.dumps([
                self.cache_id(prompt,**kwargs),outcome['request_id'],'known-response-recovery-v1']).encode()).hexdigest()
            replacement=self.ledger.result(replacement_id)
            if replacement is not None:
                try:validated(replacement,kwargs.get('schema'));return None
                except InvalidStructuredResponseError:pass
            failed=self.ledger.outcome(replacement_id)
            return {'code':outcome['code'],'request_id':outcome['request_id'],
                    'replaceable':not failed and outcome['code'] not in ('provider_refusal',),
                    'replacement_used':bool(failed)}
        return None

    def _cached_or_generate(self,cache_id,prompt,*,schema,images,pdf,instructions,category,max_output,replace_invalid):
        cached = self.ledger.result(cache_id)
        if cached is not None:
            try:
                return validated(cached, schema)
            except InvalidStructuredResponseError:
                # One explicitly requested replacement of a known complete,
                # invalid reply. Preserve both raw replies and their charges.
                # Never interpret fragments or turn an uncertain request into
                # a new purchase. This identity survives retries and restarts.
                replacement_id = "replacement:" + hashlib.sha256(
                    json.dumps([cache_id, hashlib.sha256(cached.encode()).hexdigest(), "format-recovery-v1"]).encode()).hexdigest()
                replacement = self.ledger.result(replacement_id)
                if replacement is not None:
                    return validated(replacement, schema)
                if not replace_invalid:raise
                recovery_task=getattr(schema,'replacement_instructions',None) or (
                    "Prepare the same lesson from the supplied sources. Include every supplied source_block_id and worksheet task. Do not invent learner answers." if schema and schema.__name__ in ('GuidePlan','SourceBoundGuidePlan')
                    else "Assess the same observed work and sources above.")
                with self.identified(replacement_id):
                    return self._generate(prompt + "\nFORMAT RECOVERY: Return exactly one complete JSON object matching the supplied schema. No second reply, separators, markdown or trailing text. " + recovery_task,
                        schema=schema, images=images, pdf=pdf, instructions=instructions,
                        category=category, max_output=max_output, cache_id=replacement_id)
        outcome=self.ledger.outcome(cache_id)
        if outcome and outcome.get('code'):
            # An explicit replacement of a KNOWN failed reply has one durable
            # identity. Unknown transport outcomes never enter this path.
            replacement_id='replacement:'+hashlib.sha256(json.dumps(
                [cache_id,outcome['request_id'],'known-response-recovery-v1']).encode()).hexdigest()
            replacement=self.ledger.result(replacement_id)
            if replacement is not None:return validated(replacement,schema)
            failed=self.ledger.outcome(replacement_id)
            if failed and failed.get('code'):raise UnusableResponseError(failed)
            if not replace_invalid or outcome['code']=='provider_refusal':raise UnusableResponseError(outcome)
            with self.identified(replacement_id):
                return self._generate(prompt,schema=schema,images=images,pdf=pdf,instructions=instructions,
                    category=category,max_output=max_output,cache_id=replacement_id)
        if replace_invalid:
            raise StructuredResponseError("A complete saved invalid reply is required before requesting replacement feedback. An unavailable or uncertain reply is not automatically repurchased.")
        return self._generate(prompt, schema=schema, images=images, pdf=pdf, instructions=instructions,
                              category=category, max_output=max_output, cache_id=cache_id)

    def _generate(self, prompt, *, schema=None, images=(), pdf=None, instructions="", category="teaching", max_output=4096, cache_id=None):
        provider, model = self.selection()
        key = self.key(provider)
        if not key:
            raise ValueError(f"Add the {provider.title()} API key in Settings on the home server. Saved work is available.")
        rates = self.rates(provider, model)
        request_id = uuid.uuid4().hex
        request = request_context.current()
        identity_key = _request_identity.get() or cache_id or (request.key if request else None)
        if identity_key or category == "books":
            # Background book units must also survive a crash before their main DB checkpoint.
            identity = json.dumps([identity_key or "book-checkpoint-v1", provider, model, category, prompt, instructions,
                                   schema.__name__ if schema else None, max_output,
                                   [hashlib.sha256(data).hexdigest() for data, _ in images],
                                   hashlib.sha256(pdf).hexdigest() if pdf else None])
            request_id = hashlib.sha256(identity.encode()).hexdigest()
        cached = self.ledger.result(request_id)
        if cached is not None:
            if cache_id:
                self.ledger.save_result(cache_id, cached)
            return validated(cached, schema)
        if self.ledger.completed(request_id):
            raise StructuredResponseError("This request was charged but its complete reply is unavailable. No automatic retry was sent; its source needs review.")
        if provider == "openai":
            headers = {"Authorization": f"Bearer {key}"}
            content = [{"type": "input_text", "text": prompt}]
            content += [{"type": "input_image", "image_url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}
                        for data, mime in images]
            if pdf:
                content.append({"type": "input_file", "filename": "pages.pdf",
                                "file_data": "data:application/pdf;base64," + base64.b64encode(pdf).decode()})
            body = {"model": model, "input": [{"role": "user", "content": content}], "instructions": instructions,
                      "reasoning": {"effort": "low" if _reading_handwriting.get() else PREPARATION_REASONING if model == PREPARATION_MODEL else
                          "low" if (category == "teaching" and (images or pdf)) or (category == "books" and pdf) else "none"},
                      "max_output_tokens": max_output, "store": False}
            if schema:
                body["text"] = {"format": {"type": "json_schema", "name": schema.__name__, "strict": True,
                                           "schema": strict_schema(schema)}}
            count_body = {k: v for k, v in body.items() if k not in ("store", "max_output_tokens")}
            count = self._post("https://api.openai.com/v1/responses/input_tokens", headers, count_body)
            input_tokens = count.get("input_tokens")
            if not isinstance(input_tokens, int) or not 0 <= input_tokens <= 200_000:
                raise ValueError("Could not safely count this request, or its context is too large. No generation sent.")
            # Reserve the higher cache-write input rate even without requesting caching.
            self.ledger.reserve(request_id, category, max(1, token_cost(input_tokens, max_output, rates[0] * Decimal("1.25"), rates[1])), self.limits,
                                provider=provider, model=model, operation=schema.__name__ if schema else "text", scope_id=_generation_scope.get())
            result = self._post("https://api.openai.com/v1/responses", headers, body, request_id)
            usage = result.get("usage") or {}
            text = "".join(c.get("text", "") for item in result.get("output", []) for c in item.get("content", [])
                           if c.get("type") == "output_text")
            complete = result.get("status") == "completed"
        else:
            headers = {"x-goog-api-key": key}
            parts = [{"text": prompt}, *[{"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}
                                         for data, mime in images]]
            if pdf:
                parts.append({"inlineData": {"mimeType": "application/pdf", "data": base64.b64encode(pdf).decode()}})
            body = {"contents": [{"role": "user", "parts": parts}],
                    "generationConfig": {"maxOutputTokens": max_output, "temperature": 0.1}}
            if instructions:
                body["systemInstruction"] = {"parts": [{"text": instructions}]}
            if schema:
                body["generationConfig"].update(responseMimeType="application/json", responseJsonSchema=provider_schema(schema,provider))
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
            count = self._post(url + ":countTokens", headers, {"generateContentRequest": {"model": f"models/{model}", **body}})
            input_tokens = count.get("totalTokens")
            if not isinstance(input_tokens, int) or not 0 <= input_tokens <= 200_000:
                raise ValueError("Could not safely count this request. No generation sent.")
            self.ledger.reserve(request_id, category, max(1, token_cost(input_tokens, max_output, *rates)), self.limits,
                                provider=provider, model=model, operation=schema.__name__ if schema else "text", scope_id=_generation_scope.get())
            result = self._post(url + ":generateContent", headers, body, request_id)
            u = result.get("usageMetadata") or {}
            candidates=u.get('candidatesTokenCount')
            thoughts=u.get('thoughtsTokenCount',0)
            output=candidates+thoughts if isinstance(candidates,int) and isinstance(thoughts,int) else None
            usage = {"input_tokens": u.get("promptTokenCount"), "output_tokens":output}
            candidate = (result.get("candidates") or [{}])[0]
            text = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", []) if not p.get('thought'))
            complete = candidate.get("finishReason") == "STOP"
        refusal=any(c.get('type')=='refusal' for item in result.get('output',[]) for c in item.get('content',[])) if provider=='openai' else bool(result.get('promptFeedback',{}).get('blockReason'))
        reason=(result.get('incomplete_details') or {}).get('reason') if provider=='openai' else candidate.get('finishReason')
        status=result.get('status') if provider=='openai' else candidate.get('finishReason')
        code=('provider_refusal' if refusal or reason in ('content_filter','SAFETY','RECITATION')
              else 'provider_length_limit' if reason in ('max_output_tokens','MAX_TOKENS')
              else 'provider_failed' if status=='failed'
              else 'provider_empty' if not text.strip() else 'provider_incomplete' if not complete else None)
        outcome={'request_id':request_id,'code':code,'status':status,'reason':reason,
                 'response_id':result.get('id'),'usage':usage,'error_code':(result.get('error') or {}).get('code')}
        self.ledger.save_outcome(request_id,cache_id,outcome,text)
        if all(isinstance(usage.get(k), int) and usage[k] >= 0 for k in ("input_tokens", "output_tokens")):
            charged = token_cost(usage["input_tokens"], usage["output_tokens"], *rates)
            if provider == "openai":
                details = usage.get("input_tokens_details") or {}
                writes = details.get("cache_write_tokens", 0)
                if isinstance(writes, int) and writes > 0:
                    charged += token_cost(writes, 0, rates[0] * Decimal("0.25"), 0)
            self.ledger.settle(request_id, charged, usage)
        else:
            self.ledger.mark(request_id, "uncertain")
        if code:raise UnusableResponseError(outcome)
        self.ledger.save_result(request_id, text)
        if cache_id:
            self.ledger.save_result(cache_id, text)
        return validated(text, schema)


def service(ctx=None):
    if ctx is None:
        from dependencies import context
        ctx = context()
    return ctx.ai
