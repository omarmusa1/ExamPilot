"""Groq-powered Question Generation, API Testing & Use-Case Grading (with an offline demo fallback)."""
import json
import os
import random
import re
import ssl
import time
import urllib.error
import urllib.request

LETTERS = ["A", "B", "C", "D"]
CHOICES = ("mcq", "true_false", "use_case", "mixed")
MAX_USE_CASES = 10
PASS_MARK = 0.6

STOPWORDS = set(
    """a an and are as at be but by for from has have he her his i in is it its of on or she that the
    their them there these they this to was we were what when where which who will with you your not
    can could would should do does did than then so if into about over also more most such other some
    any each very been being while after before between during through""".split()
)


class GenerationError(Exception):
    pass


def _resolve_credentials(user=None):
    """Groq is the only provider: the user's own key first, then GROQ_API_KEY from .env, else demo mode."""
    if user:
        api_key = user["api_key"] if "api_key" in user.keys() else ""
        if api_key:
            return "groq", api_key
    if os.environ.get("GROQ_API_KEY"):
        return "groq", os.environ["GROQ_API_KEY"]
    return "demo", ""


def engine_name(user=None):
    provider, _ = _resolve_credentials(user)
    return provider


def test_api_key(provider, api_key):
    """Test provider + key. Returns (ok: bool, message: str).
    Busy/rate-limited service (429/5xx) is NOT a key failure: ok=True so the user can still save the key."""
    provider = (provider or "").strip().lower()
    api_key = (api_key or "").strip()
    if provider == "demo":
        return True, "Demo mode works offline without an API key."
    if not api_key:
        return False, "Please enter an API key first."
    name = provider.upper()
    try:
        raw = _call_provider(provider, api_key, 'Reply with ONLY this exact JSON: {"status": "ok"}')
        if raw:
            return True, f"Success! Connected to {name} and received a valid response."
        return True, f"Connected to {name} successfully."
    except HttpError as exc:
        if exc.code in (400, 401, 403):
            return False, f"{name} key looks invalid or not allowed ({exc})."
        if exc.code in RETRY_CODES:
            return True, (f"{name} servers are temporarily overloaded (HTTP {exc.code}). This is on the provider's side, "
                          f"not a problem with your key. You can save it and try again in a minute.")
        if exc.code == 404:
            return False, f"Model not found ({exc}). Check the model name in your .env file."
        return False, f"{name} Error: {exc}"
    except Exception as exc:
        return False, f"{name} Error: {exc}"


PROMPT = """You are an expert university professor. Create {n} questions ({difficulty} difficulty) \
based ONLY on the lesson text below. Write the questions in this language: {language}.

Question Type Mode: {qtype_instruction}

Return ONLY valid JSON (no markdown) in this exact shape:
{{"questions": [
  {{
    "qtype": "mcq" | "true_false" | "use_case",
    "scenario": "Real-world situation description (required ONLY for use_case, otherwise empty string)",
    "text": "The question or True/False statement",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct": 0,
    "model_answer": "Key points expected in a good student answer (required ONLY for use_case, otherwise empty string)",
    "explanation": "One-sentence explanation of why the answer is right"
  }}
]}}

Rules by qtype:
- For "mcq": 4 distinct plausible options, "correct" is index 0-3.
- For "true_false": "options" MUST be ["True", "False", "", ""], "correct" is 0 (if True) or 1 (if False).
- For "use_case": provide a rich practical "scenario", a clear "text" question, and a comprehensive "model_answer". Set "options" to ["", "", "", ""] and "correct" to 0.

LESSON TEXT:
\"\"\"
{text}
\"\"\"
"""


def _qtype_instruction(qtype):
    if qtype == "true_false":
        return 'All questions MUST have "qtype": "true_false".'
    if qtype == "use_case":
        return 'All questions MUST have "qtype": "use_case" with realistic scenarios and model answers.'
    if qtype == "mixed":
        return 'Create a balanced mix of "mcq", "true_false", and "use_case" questions.'
    return 'All questions MUST have "qtype": "mcq".'


def generate_questions(text, num_questions=5, difficulty="medium", language="same as the text", qtype="mcq", user=None):
    text = (text or "").strip()
    if len(text) < 80:
        raise GenerationError("Please provide a longer lesson text (at least a few sentences).")
    if qtype not in CHOICES:
        qtype = "mcq"
    limit = MAX_USE_CASES if qtype == "use_case" else 20
    num_questions = max(1, min(int(num_questions), limit))

    provider, api_key = _resolve_credentials(user)
    if provider != "demo" and api_key:
        try:
            prompt_text = PROMPT.format(
                n=num_questions,
                difficulty=difficulty,
                language=language,
                qtype_instruction=_qtype_instruction(qtype),
                text=text[:12000],
            )
            try:
                questions = parse_ai_json(_call_provider(provider, api_key, prompt_text), default_qtype=qtype)
            except ValueError:  # includes JSON decode errors: ask once more
                questions = parse_ai_json(_call_provider(provider, api_key, prompt_text), default_qtype=qtype)
            return questions, provider, None
        except Exception as exc:
            questions = _generate_demo(text, num_questions, qtype)
            if not questions:
                raise GenerationError(f"AI generation failed ({provider}): {exc}")
            return questions, "demo", f"AI provider ({provider}) failed ({exc}); fell back to Demo engine."

    questions = _generate_demo(text, num_questions, qtype)
    if not questions:
        raise GenerationError("Could not build questions from this text. Try a longer or richer text.")
    return questions, "demo", None


# --------------------------------------------------------- Use-Case Grading

GRADE_PROMPT = """You are grading student answers to use-case questions.
For each item, score the student's answer from 0.0 to 1.0 based on the scenario and model_answer, and give 1-2 sentences of constructive feedback in the same language as the question.

Return ONLY valid JSON in this shape:
{{"grades": [{{"id": 1, "score": 0.8, "feedback": "..."}}]}}

ITEMS TO GRADE:
{items_json}
"""


def grade_use_cases(items, user=None):
    if not items:
        return {}, "demo", None
    provider, api_key = _resolve_credentials(user)
    if provider != "demo" and api_key:
        try:
            raw = _call_provider(provider, api_key, GRADE_PROMPT.format(items_json=json.dumps(items, ensure_ascii=False)))
            raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            start, end = raw.find("{"), raw.rfind("}")
            data = json.loads(raw[start : end + 1])
            results = {}
            for g in data.get("grades", []):
                qid = int(g["id"])
                score = max(0.0, min(1.0, round(float(g.get("score", 0.0)), 1)))
                feedback = str(g.get("feedback", "")).strip() or "Graded by AI."
                results[qid] = {"score": score, "feedback": feedback}
            for it in items:
                if it["id"] not in results:
                    results[it["id"]] = _grade_demo_single(it["answer"], it["model_answer"])
            return results, provider, None
        except Exception as exc:
            results = {it["id"]: _grade_demo_single(it["answer"], it["model_answer"]) for it in items}
            return results, "demo", f"AI grading failed ({exc}); used keyword grading instead."

    results = {it["id"]: _grade_demo_single(it["answer"], it["model_answer"]) for it in items}
    return results, "demo", None


def _grade_demo_single(answer, model_answer):
    ans_words = {w.lower() for w in _words(answer) if w.lower() not in STOPWORDS}
    ref_words = {w.lower() for w in _words(model_answer) if w.lower() not in STOPWORDS}
    if not ref_words:
        score = 1.0 if len(answer.strip()) >= 20 else 0.3
    else:
        overlap = len(ans_words & ref_words) / max(1, min(len(ref_words), 8))
        score = max(0.0, min(1.0, round(overlap, 1)))
    feedback = f"Keyword match score: {int(score * 100)}%. Compare your response with the reference answer."
    return {"score": score, "feedback": feedback}


# --------------------------------------------------------- HTTP Providers

class HttpError(RuntimeError):
    def __init__(self, code, msg):
        super().__init__(f"HTTP {code}: {msg}")
        self.code = code


RETRY_CODES = (429, 500, 502, 503, 504)


def _http_post(url, headers, payload, max_tries=2):
    """POST JSON with automatic retry (1s, 2s, 4s...) on temporary errors."""
    ctx = ssl.create_default_context()
    body = json.dumps(payload).encode("utf-8")
    last_err = None
    for attempt in range(max_tries):
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "ExamPilot/1.0", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=40, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            try:
                err_json = json.loads(err_body)
                err = err_json.get("error", {})
                msg = (err.get("message") if isinstance(err, dict) else str(err)) or err_body[:200]
            except Exception:
                msg = err_body[:200] or str(e)
            last_err = HttpError(e.code, msg)
            if e.code in RETRY_CODES and attempt < max_tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise last_err
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = RuntimeError(f"Network error: {e}")
            if attempt < max_tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise last_err
    raise last_err


def _model_list(env_name, defaults):
    """Model from .env first (if set), then the built-in fallbacks (no duplicates)."""
    primary = os.environ.get(env_name, "").strip()
    models = ([primary] if primary else []) + list(defaults)
    seen, out = set(), []
    for m in models:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _with_fallback(models, fn):
    """Run fn(model) for each model; move to the next one if busy / missing."""
    last_exc = None
    for model in models:
        try:
            return fn(model)
        except HttpError as e:
            last_exc = e
            if e.code in RETRY_CODES or e.code in (404, 410) or "terms acceptance" in str(e).lower() \
                    or "decommissioned" in str(e).lower():
                continue
            raise
    raise last_exc


def _http_get(url, headers):
    req = urllib.request.Request(url, headers={"User-Agent": "ExamPilot/1.0", **headers}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode("utf-8", errors="ignore")[:200] or str(e))


def _discover_models(provider, api_key):
    """Ask the provider which models this key can really use (used when the built-in names give 404)."""
    try:
        if provider == "groq":
            data = _http_get("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {api_key}"})
            ids = [m["id"] for m in data.get("data", [])
                   if any(k in m["id"] for k in ("llama", "qwen", "gpt-oss", "kimi", "gemma", "mixtral"))
                   and not any(x in m["id"] for x in ("whisper", "guard", "tts", "playai", "orpheus", "distil", "safeguard", "prompt-guard"))]
            return sorted(ids, key=lambda i: (0 if "70b" in i or "versatile" in i or "120b" in i else 1, i))
    except Exception:
        pass
    return []


def _run_with_discovery(provider, api_key, models, call):
    """Try the known model names; on 404 fall back to the models the account actually has."""
    try:
        return _with_fallback(models, call)
    except HttpError as exc:
        if exc.code not in (404, 410) and "decommissioned" not in str(exc).lower():
            raise
        found = [m for m in _discover_models(provider, api_key) if m not in models][:5]
        if not found:
            raise
        return _with_fallback(found, call)


def _call_provider(provider, api_key, prompt_text):
    if provider == "groq":
        def call(model):
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}"}
            payload = {"model": model, "messages": [{"role": "user", "content": prompt_text}],
                       "temperature": 0.3, "response_format": {"type": "json_object"}}
            try:
                data = _http_post(url, headers, payload)
            except HttpError as e:
                # Strict JSON mode rejects the whole reply when the model slips once; retry in plain mode
                # (parse_ai_json extracts the JSON itself).
                if e.code == 400 and "json" in str(e).lower():
                    payload.pop("response_format")
                    payload["temperature"] = 0.2
                    data = _http_post(url, headers, payload)
                else:
                    raise
            return data["choices"][0]["message"]["content"]
        return _run_with_discovery(provider, api_key, _model_list("GROQ_MODEL", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]), call)

    raise ValueError(f"Unsupported provider: {provider}")


# --------------------------------------------------- JSON Parser & Demo

def parse_ai_json(raw, default_qtype="mcq"):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in AI response")
    data = json.loads(raw[start : end + 1])
    result = []
    for item in data.get("questions", []):
        qtype = str(item.get("qtype") or default_qtype).strip().lower()
        if qtype not in ("mcq", "true_false", "use_case"):
            qtype = "mcq" if default_qtype == "mixed" else default_qtype
        text = str(item.get("text", "")).strip()
        explanation = str(item.get("explanation", "")).strip()
        if not text:
            continue

        if qtype == "use_case":
            scenario = str(item.get("scenario", "")).strip() or "Consider the concepts presented in the course material."
            model_answer = str(item.get("model_answer", "")).strip() or explanation or "Refer to the lesson text."
            result.append({
                "qtype": "use_case",
                "scenario": scenario,
                "text": text,
                "options": ["", "", "", ""],
                "correct": "A",
                "model_answer": model_answer,
                "explanation": explanation,
            })
        elif qtype == "true_false":
            correct = item.get("correct", 0)
            if isinstance(correct, bool):
                correct = 0 if correct else 1
            elif isinstance(correct, str):
                c_up = correct.strip().upper()
                if c_up in ("A", "TRUE", "T", "0"):
                    correct = 0
                elif c_up in ("B", "FALSE", "F", "1"):
                    correct = 1
            if not isinstance(correct, int) or correct not in (0, 1):
                correct = 0
            result.append({
                "qtype": "true_false",
                "scenario": "",
                "text": text,
                "options": ["True", "False", "", ""],
                "correct": LETTERS[correct],
                "model_answer": "",
                "explanation": explanation,
            })
        else:
            options = [str(o).strip() for o in item.get("options", [])]
            correct = item.get("correct")
            if isinstance(correct, str) and correct.upper() in LETTERS:
                correct = LETTERS.index(correct.upper())
            if len(options) != 4 or not isinstance(correct, int) or not 0 <= correct <= 3:
                continue
            if len(set(options)) < 4:
                continue
            result.append({
                "qtype": "mcq",
                "scenario": "",
                "text": text,
                "options": options,
                "correct": LETTERS[correct],
                "model_answer": "",
                "explanation": explanation,
            })

    if not result:
        raise ValueError("AI response contained no valid questions")
    return result


def _sentences(text):
    parts = re.split(r"(?<=[.!?؟])\s+|\n+", text)
    return [p.strip() for p in parts if 40 <= len(p.strip()) <= 300]


def _words(sentence):
    return re.findall(r"[^\W\d_]{4,}", sentence, flags=re.UNICODE)


def _generate_demo(text, n, qtype="mcq"):
    rng = random.Random(len(text))
    sentences = _sentences(text)
    vocab = {}
    for w in _words(text):
        if w.lower() not in STOPWORDS:
            vocab.setdefault(w.lower(), w)
    vocab_list = list(vocab.values())
    questions = []
    positions = []
    rng.shuffle(sentences)

    types_cycle = ["mcq", "true_false", "use_case"]
    for idx, sentence in enumerate(sentences):
        if len(questions) >= n:
            break
        candidates = [w for w in _words(sentence) if w.lower() not in STOPWORDS]
        if not candidates:
            continue
        answer = max(candidates, key=len)
        in_sentence = {w.lower() for w in _words(sentence)}
        pool = [w for w in vocab_list if w.lower() not in in_sentence]
        cur_type = types_cycle[idx % 3] if qtype == "mixed" else qtype
        if cur_type == "mcq" and len(pool) < 3:
            continue

        if cur_type == "use_case":
            questions.append({
                "qtype": "use_case",
                "scenario": f"In a practical project, a team is applying the following principle from the course: \"{sentence[:120]}...\"",
                "text": f"How does the concept of '{answer}' apply in this situation, and what should the team do?",
                "options": ["", "", "", ""],
                "correct": "A",
                "model_answer": sentence,
                "explanation": f'Based on the lesson: "{sentence}"',
            })
        elif cur_type == "true_false":
            is_true = (idx % 2 == 0)
            if is_true:
                stmt = sentence
                corr = "A"
            else:
                wrong_pool = pool or [w for w in candidates if w.lower() != answer.lower()]
                if wrong_pool:
                    wrong_word = rng.choice(wrong_pool)
                    stmt = re.sub(re.escape(answer), wrong_word, sentence, count=1, flags=re.IGNORECASE)
                else:
                    stmt = f"It is not true that {sentence}"
                corr = "B"
            questions.append({
                "qtype": "true_false",
                "scenario": "",
                "text": f"True or False: {stmt}",
                "options": ["True", "False", "", ""],
                "correct": corr,
                "model_answer": "",
                "explanation": f'From the lesson: "{sentence}"',
            })
        else:
            distractors = rng.sample(pool, 3)
            if not positions:
                positions = [0, 1, 2, 3]
                rng.shuffle(positions)
            options = list(distractors)
            options.insert(positions.pop(), answer)
            blanked = re.sub(re.escape(answer), "_____", sentence, count=1, flags=re.IGNORECASE)
            questions.append({
                "qtype": "mcq",
                "scenario": "",
                "text": f"Fill in the blank: {blanked}",
                "options": options,
                "correct": LETTERS[options.index(answer)],
                "model_answer": "",
                "explanation": f'From the lesson: "{sentence}"',
            })
    return questions
