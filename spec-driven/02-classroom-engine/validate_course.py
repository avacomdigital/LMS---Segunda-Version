#!/usr/bin/env python3
"""
Reference validator for AVACOM course.json (schema 1.0).

Two layers:
  1. Structure: JSON Schema (course.schema.json).
  2. Semantics: rules a schema cannot express (unique ids, references,
     modes, answer completeness, exam feasibility, offline safety, licenses).

The C# implementation in the Content app must produce the same rule codes
for the same input. This file is the executable definition of the rules.

Requires Python 3.9+ and jsonschema 4.18+ (pip install 'jsonschema>=4.18').

Usage:
  python3 validate_course.py course.json            validate, exit 1 on errors
  python3 validate_course.py course.json --json     machine readable report
  python3 validate_course.py course.json --visible l2-exam
                                                    print what a student device may
                                                    receive for one object
  python3 validate_course.py course.json --evaluate l1-act-q1 '{"selectedOptionIds":["b"]}'
                                                    reference scoring of one response
"""
import argparse
import copy
import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    sys.exit("Requires jsonschema 4.18 or newer: pip install 'jsonschema>=4.18'")

SCHEMA_PATH = Path(__file__).with_name("course.schema.json")

PHET_NC_CUTOFF = date(2026, 3, 29)
EXTERNAL_URL = re.compile(r"(https?:)?//|\bwww\.", re.IGNORECASE)
# Markers are case sensitive on purpose: "todo" is a common Spanish word.
PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|(?i:lorem ipsum|\[placeholder\])")
BRAND_TERMS = [("—", "em dash"), ("tablero", "use 'pantalla' or 'eScreen'"), ("aula virtual", "use 'aula digital'")]
BLANK_PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9]+(?:[._-][a-z0-9]+)*)\s*\}\}")

BLOCK_MEDIA_KIND = {"image": "image", "video": "video", "audio": "audio", "pdf": "pdf"}

# Fields that reveal the correct answer. Never sent to a student device for exams,
# never returned by the Content API outside /evaluate and the grading guide.
ANSWER_KEY_FIELDS = {
    "multiple_choice": ["feedback"],
    "true_false": ["answer", "feedback"],
    "fill_blanks": ["feedback"],
    "matching": ["pairs", "wrongPairs", "feedback"],
    "ordering": ["correctOrder", "wrongOrders", "feedback"],
    "open": ["modelAnswer", "rubric", "incorrectExamples", "keywords", "feedback"],
}
ANSWER_KEY_OPTION_FIELDS = ["isCorrect", "feedback"]
ANSWER_KEY_BLANK_FIELDS = ["acceptedAnswers", "wrongAnswers", "numericTolerance"]


class Report:
    def __init__(self):
        self.items = []

    def error(self, code, path, msg):
        self.items.append({"severity": "error", "code": code, "path": path, "message": msg})

    def warn(self, code, path, msg):
        self.items.append({"severity": "warning", "code": code, "path": path, "message": msg})

    @property
    def errors(self):
        return [i for i in self.items if i["severity"] == "error"]


def json_path(parts):
    out = "$"
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else f".{p}"
    return out


def validate_structure(course, report):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for e in sorted(validator.iter_errors(course), key=lambda e: list(e.absolute_path)):
        report.error("E-SCHEMA", json_path(e.absolute_path), e.message)


def walk_strings(node, parts, skip_keys=()):
    """Yield (path_parts, string) for every string value, skipping given keys."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in skip_keys:
                continue
            yield from walk_strings(v, parts + [k], skip_keys)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, parts + [i], skip_keys)
    elif isinstance(node, str):
        yield parts, node


def validate_semantics(course, report):
    media = {}
    media_used = set()
    global_ids = {}
    topic_ids = set()

    def claim(id_, path):
        if id_ in global_ids:
            report.error("E-ID-DUP", path, f"id '{id_}' already used at {global_ids[id_]}")
        else:
            global_ids[id_] = path

    def use_media(mid, path, expected_kinds):
        m = media.get(mid)
        if m is None:
            report.error("E-REF-MEDIA", path, f"media '{mid}' does not exist")
            return
        media_used.add(mid)
        if expected_kinds and m["kind"] not in expected_kinds:
            report.error("E-REF-MEDIA-KIND", path, f"media '{mid}' is {m['kind']}, expected {', '.join(sorted(expected_kinds))}")

    # Media registry
    paths_seen = {}
    for i, m in enumerate(course.get("media", [])):
        p = ["media", i]
        claim(m["id"], json_path(p))
        media[m["id"]] = m
        if m["path"] in paths_seen:
            report.error("E-MEDIA-PATH-DUP", json_path(p + ["path"]), f"path already used by media '{paths_seen[m['path']]}'")
        paths_seen[m["path"]] = m["id"]
        lic = m.get("license", {})
        if lic.get("type", "").startswith("cc-by") and not lic.get("attribution"):
            report.error("E-LIC-ATTRIBUTION", json_path(p + ["license"]), "Creative Commons license requires attribution text")
        if lic.get("type") == "cc-by-nc-4.0" and not lic.get("agreementRef"):
            report.error("E-LIC-NONCOMMERCIAL", json_path(p + ["license"]), "non commercial license inside a commercial product requires agreementRef")
        sim = m.get("simulation") or {}
        if sim.get("provider") == "phet" and not lic.get("agreementRef"):
            pub = lic.get("publishedDate")
            if not pub:
                report.error("E-LIC-PHET-DATE", json_path(p + ["license"]), "PhET simulation needs publishedDate to prove the applicable license, or an agreementRef")
            elif date.fromisoformat(pub) >= PHET_NC_CUTOFF:
                report.error("E-LIC-PHET-NC", json_path(p + ["license"]), f"PhET version published on or after {PHET_NC_CUTOFF} is CC BY-NC: requires agreementRef")
        if "scale_to_fit" in sim.get("shims", []) and not (sim.get("designWidth") and sim.get("designHeight")):
            report.error("E-SIM-DESIGN-SIZE", json_path(p + ["simulation"]), "scale_to_fit requires designWidth and designHeight")

    if "coverMediaId" in course:
        use_media(course["coverMediaId"], "$.coverMediaId", {"image"})

    course_modes = set(course.get("modes", []))

    # First pass: collect topic ids course-wide
    for li, lesson in enumerate(course.get("lessons", [])):
        for ti, t in enumerate(lesson.get("topics", [])):
            claim(t["id"], json_path(["lessons", li, "topics", ti]))
            topic_ids.add(t["id"])
            for si, st in enumerate(t.get("subtopics", [])):
                claim(st["id"], json_path(["lessons", li, "topics", ti, "subtopics", si]))
                topic_ids.add(st["id"])

    def check_topic(ref, path):
        if ref is not None and ref not in topic_ids:
            report.error("E-REF-TOPIC", path, f"topic '{ref}' does not exist in the course")

    for li, lesson in enumerate(course.get("lessons", [])):
        lp = ["lessons", li]
        claim(lesson["id"], json_path(lp))
        lesson_modes = set(lesson.get("modes", []))
        extra = lesson_modes - course_modes
        if extra:
            report.error("E-MODE-SUBSET", json_path(lp + ["modes"]), f"modes {sorted(extra)} not allowed by the course")

        for oi, obj in enumerate(lesson.get("objects", [])):
            op = lp + ["objects", oi]
            claim(obj["id"], json_path(op))
            otype = obj.get("type")
            omodes = set(obj.get("modes", []))
            extra = omodes - lesson_modes
            if extra:
                report.error("E-MODE-SUBSET", json_path(op + ["modes"]), f"modes {sorted(extra)} not allowed by the lesson")
            if otype == "exam" and omodes != {"exam"}:
                report.error("E-MODE-EXAM-ONLY", json_path(op + ["modes"]), "exam objects work only in exam mode")
            if otype != "exam" and "exam" in omodes:
                report.error("E-MODE-EXAM-ONLY", json_path(op + ["modes"]), "only exam objects can be used in exam mode")
            check_topic(obj.get("topicRef"), json_path(op + ["topicRef"]))

            for key in ("slides", "pages"):
                for pi, page in enumerate(obj.get(key, [])):
                    pp = op + [key, pi]
                    claim(page["id"], json_path(pp))
                    for bi, block in enumerate(page.get("blocks", [])):
                        bp = pp + ["blocks", bi]
                        kind = BLOCK_MEDIA_KIND.get(block.get("type"))
                        if kind:
                            use_media(block["mediaId"], json_path(bp + ["mediaId"]), {kind})
                            m = media.get(block["mediaId"])
                            if block["type"] == "video" and "startSec" in block and "endSec" in block and block["endSec"] <= block["startSec"]:
                                report.error("E-RANGE", json_path(bp), "endSec must be greater than startSec")
                            if block["type"] == "pdf":
                                f, t = block.get("fromPage"), block.get("toPage")
                                if f and t and t < f:
                                    report.error("E-RANGE", json_path(bp), "toPage must be >= fromPage")
                                if m and m.get("pageCount") and ((f and f > m["pageCount"]) or (t and t > m["pageCount"])):
                                    report.error("E-RANGE", json_path(bp), f"page outside the pdf ({m['pageCount']} pages)")

            if otype == "simulation_lab":
                use_media(obj["mediaId"], json_path(op + ["mediaId"]), {"simulation"})

            if otype in ("activity", "exam"):
                questions = obj.get("questions", [])
                for qi, q in enumerate(questions):
                    validate_question(q, op + ["questions", qi], otype, omodes, claim, use_media, check_topic, report)
                if otype == "exam":
                    validate_exam(obj, op, report)

    for mid in media:
        if mid not in media_used:
            report.warn("W-MEDIA-ORPHAN", "$.media", f"media '{mid}' is never referenced")

    # Offline safety, placeholders and brand terms over every string.
    # license holds provenance text (sourceUrl, attribution) that is never loaded.
    for parts, text in walk_strings(course, [], skip_keys=("license",)):
        p = json_path(parts)
        if EXTERNAL_URL.search(text):
            report.error("E-NET-EXTERNAL", p, "external address found: the classroom has no internet")
        if PLACEHOLDER.search(text):
            report.error("E-PLACEHOLDER", p, "placeholder text found: a course with placeholders is not published")
        low = text.lower()
        for term, hint in BRAND_TERMS:
            if term in low:
                report.warn("W-BRAND-TERM", p, f"'{term}': {hint}")


def validate_question(q, qp, otype, omodes, claim, use_media, check_topic, report):
    claim(q["id"], json_path(qp))
    qtype = q.get("type")
    for mi, mid in enumerate(q.get("mediaIds", [])):
        use_media(mid, json_path(qp + ["mediaIds", mi]), {"image", "video", "audio", "pdf"})
    check_topic(q.get("topicRef"), json_path(qp + ["topicRef"]))
    if otype == "exam" and not q.get("topicRef"):
        report.error("E-EXAM-TOPIC", json_path(qp), "exam questions require topicRef")
    if qtype == "open" and "simple" in omodes:
        report.error("E-MODE-SIMPLE-OPEN", json_path(qp), "open questions need a teacher to grade: not allowed in simple mode")

    if qtype == "multiple_choice":
        opts = q.get("options", [])
        ids = {o["id"] for o in opts}
        if len(ids) != len(opts):
            report.error("E-ID-DUP-LOCAL", json_path(qp + ["options"]), "option ids repeated")
        correct = sum(1 for o in opts if o.get("isCorrect"))
        if correct == 0:
            report.error("E-KEY-NO-CORRECT", json_path(qp), "at least one option must be correct")
        if correct == len(opts):
            report.error("E-KEY-NO-INCORRECT", json_path(qp), "at least one option must be incorrect")
        if not q.get("allowMultiple") and correct > 1:
            report.error("E-KEY-SINGLE", json_path(qp), "allowMultiple is false but more than one option is correct")
        for oi, o in enumerate(opts):
            if "mediaId" in o:
                use_media(o["mediaId"], json_path(qp + ["options", oi, "mediaId"]), {"image"})

    elif qtype == "fill_blanks":
        blanks = q.get("blanks", [])
        blank_ids = [b["id"] for b in blanks]
        used = BLANK_PLACEHOLDER.findall(q.get("template", ""))
        if len(set(blank_ids)) != len(blank_ids):
            report.error("E-ID-DUP-LOCAL", json_path(qp + ["blanks"]), "blank ids repeated")
        if sorted(used) != sorted(set(used)):
            report.error("E-BLANK-TEMPLATE", json_path(qp + ["template"]), "a placeholder appears more than once")
        if set(used) != set(blank_ids):
            report.error("E-BLANK-TEMPLATE", json_path(qp + ["template"]), f"placeholders {sorted(set(used))} do not match blanks {sorted(blank_ids)}")
        for bi, b in enumerate(blanks):
            bp = qp + ["blanks", bi]
            accepted = b.get("acceptedAnswers", [])
            wrong = [w["value"] for w in b.get("wrongAnswers", [])]
            norm = (lambda s: s) if b.get("caseSensitive") else (lambda s: s.lower())
            if {norm(w) for w in wrong} & {norm(a) for a in accepted}:
                report.error("E-KEY-CONFLICT", json_path(bp), "a wrong answer is also listed as accepted")
            if b.get("inputMode") == "numeric":
                for a in accepted + wrong:
                    try:
                        float(a)
                    except ValueError:
                        report.error("E-BLANK-NUMERIC", json_path(bp), f"'{a}' is not a number")
            if b.get("inputMode") == "select":
                choices = b.get("choices", [])
                if not set(accepted) & set(choices):
                    report.error("E-BLANK-SELECT", json_path(bp), "choices must include an accepted answer")
                if not set(choices) - set(accepted):
                    report.error("E-BLANK-SELECT", json_path(bp), "choices must include at least one wrong option")

    elif qtype == "matching":
        left = {i["id"] for i in q.get("left", [])}
        right = {i["id"] for i in q.get("right", [])}
        if len(left) != len(q.get("left", [])) or len(right) != len(q.get("right", [])) or left & right:
            report.error("E-ID-DUP-LOCAL", json_path(qp), "left and right item ids must be unique and not shared")
        pairs = q.get("pairs", [])
        seen_left = set()
        correct_set = set()
        for pi, pr in enumerate(pairs):
            if pr["leftId"] not in left or pr["rightId"] not in right:
                report.error("E-MATCH-REF", json_path(qp + ["pairs", pi]), "pair references an unknown item")
            if pr["leftId"] in seen_left:
                report.error("E-MATCH-LEFT-TWICE", json_path(qp + ["pairs", pi]), "a left item has more than one correct pair")
            seen_left.add(pr["leftId"])
            correct_set.add((pr["leftId"], pr["rightId"]))
        if seen_left != left:
            report.error("E-MATCH-INCOMPLETE", json_path(qp + ["pairs"]), "every left item needs a correct pair")
        for wi, wp in enumerate(q.get("wrongPairs", [])):
            if wp["leftId"] not in left or wp["rightId"] not in right:
                report.error("E-MATCH-REF", json_path(qp + ["wrongPairs", wi]), "wrong pair references an unknown item")
            if (wp["leftId"], wp["rightId"]) in correct_set:
                report.error("E-KEY-CONFLICT", json_path(qp + ["wrongPairs", wi]), "wrong pair is also a correct pair")

    elif qtype == "ordering":
        items = [i["id"] for i in q.get("items", [])]
        if len(set(items)) != len(items):
            report.error("E-ID-DUP-LOCAL", json_path(qp + ["items"]), "item ids repeated")
        correct = q.get("correctOrder", [])
        if sorted(correct) != sorted(items):
            report.error("E-ORDER-PERMUTATION", json_path(qp + ["correctOrder"]), "correctOrder must contain every item exactly once")
        for wi, w in enumerate(q.get("wrongOrders", [])):
            if sorted(w["order"]) != sorted(items):
                report.error("E-ORDER-PERMUTATION", json_path(qp + ["wrongOrders", wi]), "wrong order must contain every item exactly once")
            if w["order"] == correct:
                report.error("E-KEY-CONFLICT", json_path(qp + ["wrongOrders", wi]), "wrong order equals the correct order")

    elif qtype == "open":
        rubric = q.get("rubric", [])
        total = sum(r["points"] for r in rubric)
        if abs(total - q.get("points", 0)) > 1e-9:
            report.error("E-OPEN-RUBRIC-POINTS", json_path(qp + ["rubric"]), f"rubric adds {total} points, question is worth {q.get('points')}")
        for ri, r in enumerate(rubric):
            for lv in r.get("levels", []):
                if lv["points"] > r["points"]:
                    report.error("E-OPEN-RUBRIC-LEVEL", json_path(qp + ["rubric", ri]), f"level '{lv['label']}' exceeds criterion points")

    for key in ("left", "right", "items"):
        for ii, it in enumerate(q.get(key, [])):
            if "mediaId" in it:
                use_media(it["mediaId"], json_path(qp + [key, ii, "mediaId"]), {"image"})


def validate_exam(obj, op, report):
    settings = obj.get("settings", {})
    sel = settings.get("selection", {})
    pool = obj.get("questions", [])
    count = sel.get("questionCount")
    topics = {q.get("topicRef") for q in pool if q.get("topicRef")}
    sp = json_path(op + ["settings", "selection"])
    if sel.get("strategy") == "fixed":
        if count is not None and count != len(pool):
            report.error("E-EXAM-COUNT", sp, "fixed strategy: questionCount must equal the pool size or be omitted")
        return
    if count is None:
        return
    if count > len(pool):
        report.error("E-EXAM-COUNT", sp, f"questionCount {count} is larger than the pool ({len(pool)})")
        return
    if sel.get("coverAllTopics") and count < len(topics):
        report.error("E-EXAM-TOPICS", sp, f"coverAllTopics needs at least {len(topics)} questions, questionCount is {count}")
    if len(pool) < 3 * count:
        report.warn("W-EXAM-POOL-SMALL", sp, f"pool of {len(pool)} for {count} questions: students will see very similar exams (recommended 3x or more)")
    if sel.get("difficultyTolerancePct") == 0 or sel.get("timeTolerancePct") == 0:
        report.warn("W-EXAM-TOLERANCE-ZERO", sp, "zero tolerance usually makes balanced selection impossible")


def visible_object(obj, profile="student", include_activity_keys=False):
    """What the API returns for one object (see spec section 14).
    Exam answer keys are always removed. Activity keys stay only when
    include_activity_keys is requested and feedback is immediate."""
    out = copy.deepcopy(obj)
    if profile == "student":
        out.pop("teacherNotes", None)
        for key in ("slides", "pages"):
            for page in out.get(key, []):
                page.pop("teacherNotes", None)
    keep_keys = (include_activity_keys and out.get("type") == "activity"
                 and out.get("settings", {}).get("feedback") == "immediate")
    for q in out.get("questions", []):
        if profile == "student":
            q.pop("teacherNotes", None)
        if keep_keys:
            continue
        for f in ANSWER_KEY_FIELDS.get(q["type"], []):
            q.pop(f, None)
        for o in q.get("options", []):
            for f in ANSWER_KEY_OPTION_FIELDS:
                o.pop(f, None)
        for b in q.get("blanks", []):
            for f in ANSWER_KEY_BLANK_FIELDS:
                b.pop(f, None)
    return out


def _normalize(text, case_sensitive, ignore_accents):
    import unicodedata
    t = " ".join(str(text).split())
    if not case_sensitive:
        t = t.lower()
    if ignore_accents:
        t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return t


def evaluate_response(q, response):
    """Reference scoring. Returns score, maxScore, correct (None when manual),
    requiresManualGrading and the feedback texts to show."""
    pts = q["points"]
    partial = q.get("partialCredit", False)
    fb = q["feedback"]
    out = {"questionId": q["id"], "maxScore": pts, "requiresManualGrading": False, "feedback": []}
    t = q["type"]

    if t == "open":
        out.update(score=None, correct=None, requiresManualGrading=True)
        return out

    if t == "true_false":
        ok = response.get("value") is q["answer"]
        ratio = 1.0 if ok else 0.0

    elif t == "multiple_choice":
        chosen = set(response.get("selectedOptionIds", []))
        correct = {o["id"] for o in q["options"] if o["isCorrect"]}
        for o in q["options"]:
            if o["id"] in chosen and not o["isCorrect"] and o.get("feedback"):
                out["feedback"].append(o["feedback"])
        if q["allowMultiple"] and partial:
            hits = len(chosen & correct)
            misses = len(chosen - correct)
            ratio = max(0.0, (hits - misses) / len(correct))
        else:
            ratio = 1.0 if chosen == correct else 0.0

    elif t == "fill_blanks":
        given = response.get("blanks", {})
        good = 0
        for b in q["blanks"]:
            val = given.get(b["id"], "")
            if b["inputMode"] == "numeric":
                try:
                    v = float(str(val).replace(",", "."))
                    ok = any(abs(v - float(a)) <= b.get("numericTolerance", 0) for a in b["acceptedAnswers"])
                except ValueError:
                    ok = False
            else:
                norm = lambda x: _normalize(x, b.get("caseSensitive", False), b.get("ignoreAccents", True))
                ok = norm(val) in {norm(a) for a in b["acceptedAnswers"]}
            if ok:
                good += 1
            else:
                for w in b["wrongAnswers"]:
                    if w.get("feedback") and _normalize(w["value"], False, True) == _normalize(val, False, True):
                        out["feedback"].append(w["feedback"])
        ratio = good / len(q["blanks"]) if partial else (1.0 if good == len(q["blanks"]) else 0.0)

    elif t == "matching":
        given = {(p["leftId"], p["rightId"]) for p in response.get("pairs", [])}
        correct = {(p["leftId"], p["rightId"]) for p in q["pairs"]}
        for w in q["wrongPairs"]:
            if (w["leftId"], w["rightId"]) in given:
                out["feedback"].append(w["feedback"])
        good = len(given & correct)
        ratio = good / len(correct) if partial else (1.0 if given == correct else 0.0)

    elif t == "ordering":
        order = response.get("order", [])
        correct = q["correctOrder"]
        for w in q["wrongOrders"]:
            if w["order"] == order:
                out["feedback"].append(w["feedback"])
        if partial:
            ratio = sum(1 for a, b in zip(order, correct) if a == b) / len(correct)
        else:
            ratio = 1.0 if order == correct else 0.0
    else:
        raise ValueError(f"unknown question type {t}")

    out["score"] = round(pts * ratio, 4)
    out["correct"] = ratio == 1.0
    out["feedback"].insert(0, fb["correct"] if ratio == 1.0 else fb["incorrect"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("course")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--visible", metavar="OBJECT_ID")
    ap.add_argument("--evaluate", nargs=2, metavar=("QUESTION_ID", "RESPONSE_JSON"),
                    help='e.g. --evaluate l1-act-q1 \'{"selectedOptionIds":["b"]}\'')
    args = ap.parse_args()

    course = json.loads(Path(args.course).read_text(encoding="utf-8"))

    if args.evaluate:
        qid, raw = args.evaluate
        for lesson in course["lessons"]:
            for obj in lesson["objects"]:
                for q in obj.get("questions", []):
                    if q["id"] == qid:
                        print(json.dumps(evaluate_response(q, json.loads(raw)), ensure_ascii=False, indent=2))
                        return 0
        print(f"question '{qid}' not found", file=sys.stderr)
        return 2

    if args.visible:
        for lesson in course["lessons"]:
            for obj in lesson["objects"]:
                if obj["id"] == args.visible:
                    print(json.dumps(visible_object(obj), ensure_ascii=False, indent=2))
                    return 0
        print(f"object '{args.visible}' not found", file=sys.stderr)
        return 2

    report = Report()
    validate_structure(course, report)
    if not report.errors:
        validate_semantics(course, report)

    if args.json:
        print(json.dumps({"valid": not report.errors, "items": report.items}, ensure_ascii=False, indent=2))
    else:
        for it in report.items:
            print(f"{it['severity'].upper():7} {it['code']:24} {it['path']}  {it['message']}")
        print(f"\n{len(report.errors)} errors, {len(report.items) - len(report.errors)} warnings")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
