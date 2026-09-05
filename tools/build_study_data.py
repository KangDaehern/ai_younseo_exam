"""Build the 30-passage web data from the extracted worksheet and public translations."""

from __future__ import annotations

import html
import ast
import json
import re
from collections import Counter
from pathlib import Path

import pdfplumber
import requests


ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "data" / "extracted" / "2026_2학년_2학기_1차" / "pages"
OUTPUT = ROOT / "web" / "data" / "passages.json"

TRANSLATIONS = {
    "26-6": ROOT / "references" / "2026-06-go2" / "flowedu_한줄해석.pdf",
    "25-9": ROOT / "references" / "2025-09-go2" / "flowedu_한줄해석.pdf",
}

ANSWERS = {
    "26-6": {20: 3, 21: 1, 22: 2, 23: 3, 24: 4, 29: 2, 30: 3, 31: 1, 32: 2, 33: 2, 34: 5, 36: 2, 37: 5, 38: 5, 39: 2, 40: 4, 41: 1, 42: 5},
    "25-9": {21: 2, 24: 1, 29: 2, 30: 3, 31: 2, 32: 5, 33: 5, 34: 1, 36: 5, 37: 3, 39: 4, 40: 2, 41: 5, 42: 4},
}

SOURCES = {
    "26-6": {
        "label": "2026년 6월 고2 한줄해석·관련 자료 안내",
        "url": "https://flowedu.tistory.com/934",
        "note": "같은 시험의 무료 한줄해석과 별도 연계 자료를 안내하는 페이지",
    },
    "25-9": {
        "label": "2025년 9월 고2 변형문제 샘플 240문항",
        "url": "https://files-scs.pstatic.net/2025/09/16/QPWmYOaRtv/%5BSAMPLE%5D%20%EB%B3%80%ED%98%95%EB%AC%B8%EC%A0%9C%20(%EC%9C%A0%ED%98%95%ED%8E%B8)%20(240%EB%AC%B8%ED%95%AD)-%209%EC%9B%94%20%EA%B3%A02%20%EB%AA%A8%EC%9D%98%EA%B3%A0%EC%82%AC.pdf",
        "note": "같은 시험 지문을 유형별로 변형한 공개 샘플 PDF",
    },
}

STOPWORDS = set("a an the and or but if then when while as at by for from in into of on to with without is are was were be been being have has had do does did can could may might must will would should this that these those it its they them their we our you your he she his her not no so than too very more most much many some any each all both other another such how what which who whom where why because about over under up down out only even still also just make made get got use used using one two way people time thing things".split())

PHRASES = {
    "as well as": "~뿐만 아니라 ~도",
    "in charge of": "~을 담당하는",
    "allow for": "~을 고려하다",
    "interact with": "~와 상호작용하다",
    "be composed of": "~로 구성되다",
    "be made of": "~로 만들어지다",
    "be associated with": "~와 관련되다",
    "be likely to": "~할 가능성이 있다",
    "lead to": "~로 이어지다",
    "result in": "~을 초래하다",
    "result from": "~에서 비롯되다",
    "due to": "~ 때문에",
    "rather than": "~라기보다",
    "in order to": "~하기 위해",
    "in contrast to": "~와 대조적으로",
    "on the other hand": "반면에",
    "for example": "예를 들어",
    "as a result": "그 결과",
    "in other words": "다시 말해",
    "take into account": "~을 고려하다",
    "take place": "일어나다",
    "deal with": "~을 다루다",
    "depend on": "~에 달려 있다",
    "focus on": "~에 집중하다",
    "contribute to": "~에 기여하다",
    "refer to": "~을 가리키다",
    "prevent from": "~하지 못하게 막다",
    "regardless of": "~와 관계없이",
    "be capable of": "~할 수 있다",
    "be responsible for": "~을 책임지다",
    "have an effect on": "~에 영향을 미치다",
    "play a role in": "~에서 역할을 하다",
    "come to": "~하게 되다",
    "turn into": "~로 바뀌다",
    "keep up with": "~을 따라가다",
    "stand in contrast to": "~와 대조를 이루다",
    "bring on board": "합류시키다, 참여시키다",
    "work on": "~을 진행하다",
    "see to it that": "반드시 ~하게 조치하다",
    "starve to death": "굶어 죽다",
    "be based on": "~에 근거하다",
    "pay for": "~의 값을 지불하다",
    "benefit from": "~로부터 이익을 얻다",
    "be familiar to": "~에게 익숙하다",
    "be sensitive to": "~에 민감하다",
    "be unable to": "~할 수 없다",
    "be ready to": "~할 준비가 되다",
    "think about": "~에 관해 생각하다",
    "think of": "~을 생각해 내다",
    "try to": "~하려고 노력하다",
    "empathize with": "~에게 공감하다",
    "because of": "~ 때문에",
    "distinguish from": "~와 구별하다",
    "adapt to": "~에 적응하다",
    "be involved in": "~에 관련되다",
    "be known as": "~로 알려져 있다",
    "be expected to": "~할 것으로 예상되다",
    "have to do with": "~와 관련이 있다",
    "make it possible to": "~하는 것을 가능하게 하다",
    "in the form of": "~의 형태로",
    "in response to": "~에 대응하여",
    "at the same time": "동시에",
    "for instance": "예를 들어",
    "in this way": "이런 방식으로",
    "a great deal of": "많은 양의",
    "be different from": "~와 다르다",
}


def pdf_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "").replace("\x00", "") for page in pdf.pages)


def parse_translation_pdf(path: Path, year: str, month: str) -> dict[int, dict]:
    text = pdf_text(path)
    header = re.compile(rf"\[고2\]\s*(?:20)?{year}년\s*{month}월\s*-\s*(\d+)(?:~\d+)?번:\s*([^\n]+)")
    matches = list(header.finditer(text))
    sections: dict[int, dict] = {}
    marker_re = re.compile(r"(?m)^([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮])\s*")
    for index, match in enumerate(matches):
        number = int(match.group(1))
        body = text[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        pieces = marker_re.split(body)
        values = []
        for position in range(1, len(pieces), 2):
            content = re.sub(r"\s*flowedu\.tistory\.com\s*", " ", pieces[position + 1])
            content = re.sub(r"\s+", " ", content).strip()
            if content:
                values.append(content)
        pairs = []
        for position in range(0, len(values) - 1, 2):
            english, korean = values[position], values[position + 1]
            if re.search(r"[A-Za-z]", english) and re.search(r"[가-힣]", korean):
                pairs.append({"en": english, "ko": korean})
        sections[number] = {"title": match.group(2).strip(), "sentences": pairs}
    return sections


def clean_raw(text: str) -> str:
    return text.replace("\r", "").replace("­", "-").strip()


def extract_choices(text: str) -> list[list[str]]:
    lines = text.splitlines()
    groups: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        match = re.match(r"^([①②③④⑤])\s*(.*)", stripped)
        if match:
            symbol_index = "①②③④⑤".index(match.group(1))
            if symbol_index == 0:
                if len(current) == 5:
                    groups.append(current)
                current = []
            if symbol_index == len(current):
                current.append(match.group(2).strip())
            continue
        if current and len(current) < 5 and stripped and not re.match(r"^[*\[(]", stripped):
            current[-1] += " " + stripped
    if len(current) == 5:
        groups.append(current)
    return groups


def question_prompt(text: str, page: int, number: int) -> str:
    if page >= 29:
        return "윗글의 제목으로 가장 적절한 것은?" if number == 41 else "밑줄 친 (a)~(e) 중 문맥상 낱말의 쓰임이 적절하지 않은 것은?"
    lines = [line.strip() for line in text.splitlines()]
    code_pos = next((i for i, line in enumerate(lines) if re.search(r"\d{2}-\d{1,2}-\d{1,2}", line)), 0)
    numbered_pos = next((i for i in range(code_pos, -1, -1) if re.match(r"^\d+\.\s*", lines[i])), code_pos)
    numbered = " ".join(lines[numbered_pos : code_pos + 1])
    numbered = re.sub(r"^\d+\.\s*", "", numbered)
    numbered = re.sub(r"\s*\d{2}-\d{1,2}-\d{1,2}(?:~\d+)?\s*", "", numbered).strip()
    if numbered and re.search(r"[가-힣?]", numbered):
        return numbered
    instruction = next((re.sub(r"^\[[^]]+\]\s*", "", line) for line in reversed(lines[: code_pos + 1]) if re.search(r"[가-힣]", line) and ("고르시오" in line or "적절" in line)), "다음 글을 읽고 물음에 답하시오.")
    return instruction


def translate_terms(terms: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0"}
    for start in range(0, len(terms), 25):
        batch = terms[start : start + 25]
        try:
            response = session.get("https://translate.google.com/m", params={"sl": "en", "tl": "ko", "q": "\n".join(batch)}, headers=headers, timeout=20)
            response.encoding = "utf-8"
            match = re.search(r'<div class="result-container">(.*?)</div>', response.text, re.S)
            translated = html.unescape(match.group(1)) if match else ""
            translated = re.sub(r"<br\s*/?>", "\n", translated, flags=re.I)
            lines = [re.sub(r"<[^>]+>", "", line).strip() for line in translated.splitlines()]
            if len(lines) != len(batch):
                lines = []
            for index, term in enumerate(batch):
                result[term] = lines[index] if lines else "문맥 속 뜻 확인"
        except requests.RequestException:
            for term in batch:
                result[term] = "문맥 속 뜻 확인"
    return result


def select_words(sentences: list[dict], count: int = 200) -> list[str]:
    # 윤서의 현재 어휘 수준에 맞춰 관사·대명사 같은 기초 기능어만 제외하고,
    # 세 글자 이상의 내용어는 사실상 모두 뜻을 확인할 수 있게 한다.
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", " ".join(item["en"] for item in sentences).lower())
    frequencies = Counter(word.strip("'-") for word in words if word.strip("'-") not in STOPWORDS)
    ranked = sorted(frequencies, key=lambda word: (frequencies[word], len(word)), reverse=True)
    return ranked[:count]


EASY_STUDY_WORDS = STOPWORDS | set(
    "good bad new old big small long short high low same different right left first last next "
    "day days year years man men woman women child children name place part kind point group team "
    "work works worked working person project school home world life hand help need want know think "
    "look see come came go went take took give gave make made say said tell told find found show "
    "start stop keep put set let call try ask answer problem question change move lead live learn read "
    "example parts everyone result results overall involved highly sometimes suppose equally charge "
    "you're you've we're we've they're they've isn't aren't wasn't weren't don't doesn't didn't can't couldn't won't wouldn't".split()
)


def select_study_words(sentences: list[dict], count: int = 20) -> list[str]:
    """Return a compact memorization list while the click dictionary stays broad."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", " ".join(item["en"] for item in sentences).lower())
    frequencies = Counter(word.strip("'-") for word in words if word.strip("'-") not in EASY_STUDY_WORDS)
    ranked = sorted(frequencies, key=lambda word: (frequencies[word], len(word)), reverse=True)
    return ranked[:count]


def split_chunks(sentence: str) -> list[str]:
    """Split a sentence into short meaning units while preserving every word."""
    normalized = re.sub(r"\s+", " ", sentence).strip()
    parts = re.split(
        r"(?<=[,;:])\s+|\s+(?=(?:but|because|although|while|when|if|which|who|that|so that|in order to)\b)",
        normalized,
        flags=re.I,
    )
    chunks: list[str] = []
    for part in parts:
        if len(part.split()) > 14:
            chunks.extend(re.split(r"\s+(?=(?:and|or|as|than|to)\b)", part, maxsplit=1, flags=re.I))
        else:
            chunks.append(part)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def build() -> list[dict]:
    translated = {
        "26-6": parse_translation_pdf(TRANSLATIONS["26-6"], "26", "6"),
        "25-9": parse_translation_pdf(TRANSLATIONS["25-9"], "25", "9"),
    }
    drafts = []
    all_terms: list[str] = []
    all_chunks: list[str] = []
    for page in range(1, 31):
        raw = clean_raw((PAGES / f"{page:02}.txt").read_text(encoding="utf-8"))
        code_match = re.search(r"(25-9|26-6)-(\d+)(?:~(\d+))?", raw)
        if not code_match:
            raise ValueError(f"Missing exam code on page {page}")
        exam, first_number = code_match.group(1), int(code_match.group(2))
        section = translated[exam][first_number]
        words = select_words(section["sentences"])
        study_words = select_study_words(section["sentences"])
        for sentence in section["sentences"]:
            sentence["chunkTexts"] = split_chunks(sentence["en"])
            all_chunks.extend(chunk for chunk in sentence["chunkTexts"] if chunk not in all_chunks)
        all_terms.extend(word for word in words if word not in all_terms)
        drafts.append((page, raw, exam, first_number, section, words, study_words))

    meanings: dict[str, str] = {}
    chunk_meanings: dict[str, str] = {}
    choice_meanings: dict[str, str] = {}
    if OUTPUT.exists():
        try:
            previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
            meanings = {word: meaning for item in previous for key in ("words", "lookupWords") for word, meaning in item.get(key, [])}
            chunk_meanings = {chunk[0]: chunk[1] for item in previous for sentence in item.get("sentences", []) for chunk in sentence.get("chunks", [])}
            choice_meanings = {choice: meaning for item in previous for question in item.get("questions", []) for choice, meaning in zip(question.get("choices", []), question.get("choiceMeanings", [])) if meaning}
        except (json.JSONDecodeError, OSError, ValueError):
            meanings = {}
    meanings.update(translate_terms([term for term in all_terms if term not in meanings]))
    chunk_meanings.update(translate_terms([chunk for chunk in all_chunks if chunk not in chunk_meanings]))
    passages = []
    for page, raw, exam, first_number, section, words, study_words in drafts:
        groups = extract_choices(raw)
        if not groups and 8 <= page <= 11:
            marked = re.findall(r"[①②③④⑤]\s*([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2})", raw)
            if len(marked) >= 5:
                groups = [marked[:5]]
        if not groups and 24 <= page <= 26:
            groups = [["①의 위치", "②의 위치", "③의 위치", "④의 위치", "⑤의 위치"]]
        question_numbers = [first_number] if page < 29 else [41, 42]
        original_questions = []
        for q_index, choices in enumerate(groups[: len(question_numbers)]):
            number = question_numbers[q_index]
            original_questions.append({
                "title": f"원래 기출 {number}번",
                "question": question_prompt(raw, page, number),
                "choices": choices,
                "answer": ANSWERS[exam].get(number, 1) - 1,
                "explanation": f"공식 정답은 {ANSWERS[exam].get(number, 1)}번입니다. 글의 핵심: {section['title']}",
                "kind": "original",
            })
        if page == 1:
            legacy = (ROOT / "web" / "01_fallacy-of-composition.html").read_text(encoding="utf-8")
            match = re.search(r"const quizzes = (\[.*?\]);\s*\n\s*function emptyState", legacy, re.S)
            if match:
                literal = re.sub(r"([{,])\s*(title|q|passage|choices|correct|why)\s*:", r"\1'\2':", match.group(1))
                try:
                    old_quizzes = ast.literal_eval(literal)
                    original_questions = [{"title": item["title"], "question": item["q"], "passage": item.get("passage", ""), "choices": item["choices"], "answer": item["correct"], "explanation": item["why"], "kind": "reconstructed"} for item in old_quizzes]
                except (SyntaxError, ValueError):
                    pass
        english = " ".join(item["en"] for item in section["sentences"])
        phrases = [[phrase, meaning] for phrase, meaning in PHRASES.items() if phrase.lower() in english.lower()]
        for sentence in section["sentences"]:
            sentence["chunks"] = [[chunk, chunk_meanings.get(chunk, "문맥 속 뜻 확인")] for chunk in sentence.pop("chunkTexts")]
        passages.append({
            "id": f"{page:02}",
            "exam": exam,
            "examLabel": "2026년 6월" if exam == "26-6" else "2025년 9월",
            "examNumber": first_number,
            "title": section["title"],
            "sentences": section["sentences"],
            "words": [[word, meanings[word]] for word in study_words],
            "lookupWords": [[word, meanings[word]] for word in words],
            "phrases": phrases,
            "questions": original_questions,
            "relatedSource": SOURCES[exam],
        })
    choices_to_translate = []
    choice_words_by_passage: dict[str, list[str]] = {}
    extra_choice_terms: list[str] = []
    for passage in passages:
        choice_text = " ".join(choice for question in passage["questions"] for choice in question["choices"])
        choice_words = select_words([{"en": choice_text}], count=200)
        existing_words = {word for word, _ in passage["lookupWords"]}
        choice_words_by_passage[passage["id"]] = [word for word in choice_words if word not in existing_words]
        extra_choice_terms.extend(word for word in choice_words_by_passage[passage["id"]] if word not in meanings and word not in extra_choice_terms)
        existing_phrases = {phrase for phrase, _ in passage["phrases"]}
        passage["phrases"].extend(
            [phrase, meaning]
            for phrase, meaning in PHRASES.items()
            if phrase.lower() in choice_text.lower() and phrase not in existing_phrases
        )
        for question in passage["questions"]:
            choices_to_translate.extend(choice for choice in question["choices"] if re.search(r"[A-Za-z]", choice) and choice not in choice_meanings and choice not in choices_to_translate)
    meanings.update(translate_terms(extra_choice_terms))
    choice_meanings.update(translate_terms(choices_to_translate))
    for passage in passages:
        passage["lookupWords"].extend([word, meanings[word]] for word in choice_words_by_passage[passage["id"]])
        for question in passage["questions"]:
            question["choiceMeanings"] = [choice_meanings.get(choice, "") if re.search(r"[A-Za-z]", choice) else "" for choice in question["choices"]]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(passages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return passages


if __name__ == "__main__":
    built = build()
    print(f"Built {len(built)} passages, {sum(len(item['sentences']) for item in built)} sentences, {sum(len(item['questions']) for item in built)} original questions")
