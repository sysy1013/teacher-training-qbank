"""영재교육 문제은행 빌드.

사용: python -I -X utf8 build.py [입력폴더] [index.html 출력경로] [artifact.html 출력경로]
기본: 입력 = scratchpad/q, 출력 = 문제은행/index.html, site/artifact.html
"""
import json
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
SCRATCH = SITE.parent
DEFAULT_IN = SCRATCH / "q"
DEFAULT_INDEX = Path(r"D:\Users\User\Desktop\연수\영재교육\문제은행\index.html")
DEFAULT_ART = SITE / "artifact.html"
TEMPLATE = SITE / "template.html"
PLACEHOLDER = "/*__DATA__*/null"

warnings = []


def warn(msg):
    warnings.append(msg)
    print("[경고] " + msg)


def nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def check_question(q, fname):
    qid = q.get("id") if isinstance(q, dict) else None
    tag = f"{fname} 문항 {qid!r}"
    if not isinstance(q, dict):
        return f"{tag}: 객체 아님"
    for k in ("id", "q", "explain"):
        if not nonempty_str(q.get(k)):
            return f"{tag}: '{k}' 누락/빈 값"
    ch = q.get("choices")
    if not isinstance(ch, list) or len(ch) != 5 or not all(nonempty_str(c) for c in ch):
        return f"{tag}: choices 5개(비어있지 않은 문자열) 아님"
    a = q.get("answer")
    if not isinstance(a, int) or isinstance(a, bool) or not 1 <= a <= 5:
        return f"{tag}: answer 1~5 정수 아님 ({a!r})"
    box = q.get("box")
    if box is not None and not isinstance(box, str):
        return f"{tag}: box는 문자열 또는 null"
    src = q.get("source")
    if not isinstance(src, dict):
        return f"{tag}: source 누락"
    return None


def clean_question(q):
    src = q.get("source") or {}
    page = src.get("page")
    if isinstance(page, str) and page.strip().isdigit():
        page = int(page)
    return {
        "id": q["id"].strip(),
        "type": (q.get("type") or "").strip(),
        "q": q["q"],
        "box": q["box"] if nonempty_str(q.get("box")) else None,
        "choices": [c.strip() for c in q["choices"]],
        "answer": q["answer"],
        "explain": q["explain"],
        "source": {
            "page": page,
            "section": (src.get("section") or "").strip(),
            "quote": (src.get("quote") or "").strip(),
        },
    }


def load_lessons(in_dir: Path):
    lessons = {}
    seen_ids = set()
    if not in_dir.is_dir():
        warn(f"입력 폴더 없음: {in_dir} → 빈 데이터로 빌드")
        return []
    files = sorted(in_dir.glob("*.json"))
    if not files:
        warn(f"JSON 파일 없음: {in_dir} → 빈 데이터로 빌드")
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            warn(f"{f.name}: JSON 읽기 실패 ({e}) → 파일 제외")
            continue
        if not isinstance(d, dict):
            warn(f"{f.name}: 최상위 객체 아님 → 제외")
            continue
        lesson = d.get("lesson")
        if not isinstance(lesson, int) or not 1 <= lesson <= 60:
            m = re.match(r"(\d+)", f.stem)
            if m and 1 <= int(m.group(1)) <= 60:
                warn(f"{f.name}: lesson 값 이상({lesson!r}) → 파일명 기준 {int(m.group(1))}")
                lesson = int(m.group(1))
            else:
                warn(f"{f.name}: lesson 값 이상({lesson!r}) → 제외")
                continue
        if lesson in lessons:
            warn(f"{f.name}: {lesson}차시 중복 → 제외")
            continue
        title = d.get("title") if nonempty_str(d.get("title")) else f"{lesson}차시"
        if not nonempty_str(d.get("title")):
            warn(f"{f.name}: title 누락")
        summary = [s for s in (d.get("summary") or []) if nonempty_str(s)]
        if not summary:
            warn(f"{f.name}: summary 비어 있음")
        qs = []
        for q in d.get("questions") or []:
            err = check_question(q, f.name)
            if err:
                warn(err + " → 문항 제외")
                continue
            cq = clean_question(q)
            if cq["id"] in seen_ids:
                warn(f"{f.name} 문항 {cq['id']!r}: id 중복 → 제외")
                continue
            if cq["source"]["page"] is None or not cq["source"]["quote"]:
                warn(f"{f.name} 문항 {cq['id']!r}: source page/quote 누락 (문항은 포함)")
            seen_ids.add(cq["id"])
            qs.append(cq)
        if not qs:
            warn(f"{f.name}: 유효 문항 0개 → 차시 제외")
            continue
        lessons[lesson] = {
            "lesson": lesson,
            "title": title.strip(),
            "file": (d.get("file") or "").strip(),
            "summary": summary,
            "questions": qs,
        }
    return [lessons[k] for k in sorted(lessons)]


def js_json(obj):
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
             .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def make_artifact(full: str) -> str:
    head = re.search(r"<head>(.*?)</head>", full, re.S).group(1)
    body = re.search(r"<body[^>]*>(.*)</body>", full, re.S).group(1)
    head = re.sub(r"<meta[^>]*>\s*", "", head)
    return head.strip() + "\n" + body.strip() + "\n"


def main():
    args = sys.argv[1:]
    in_dir = Path(args[0]) if len(args) > 0 else DEFAULT_IN
    out_index = Path(args[1]) if len(args) > 1 else DEFAULT_INDEX
    out_art = Path(args[2]) if len(args) > 2 else DEFAULT_ART

    tpl = TEMPLATE.read_text(encoding="utf-8")
    if tpl.count(PLACEHOLDER) != 1:
        sys.exit("템플릿에 자리표시자 /*__DATA__*/null 이 정확히 1개 있어야 함")

    lessons = load_lessons(in_dir)
    data = {"total": 60, "lessons": lessons}
    full = tpl.replace(PLACEHOLDER, js_json(data))

    # guard: 데이터가 </script 를 만들지 않음
    script = full.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    assert "</script" not in script.lower(), "script 블록 내부에 </script 존재"

    out_index.parent.mkdir(parents=True, exist_ok=True)
    out_index.write_text(full, encoding="utf-8", newline="\n")
    out_art.parent.mkdir(parents=True, exist_ok=True)
    out_art.write_text(make_artifact(full), encoding="utf-8", newline="\n")

    nq = sum(len(L["questions"]) for L in lessons)
    have = {L["lesson"] for L in lessons}
    missing = [n for n in range(1, 61) if n not in have]
    print(f"차시 {len(lessons)}개 / 문항 {nq}개")
    if lessons:
        print("차시별: " + ", ".join(f"{L['lesson']}:{len(L['questions'])}" for L in lessons))
    if missing:
        print(f"미수록 차시 {len(missing)}개: {missing[:20]}{' …' if len(missing) > 20 else ''}")
    dist = [0] * 5
    for L in lessons:
        for q in L["questions"]:
            dist[q["answer"] - 1] += 1
    if nq:
        print("정답 분포 ①~⑤: " + " / ".join(str(x) for x in dist))
    print(f"경고 {len(warnings)}건")
    print(f"→ {out_index} ({out_index.stat().st_size:,} B)")
    print(f"→ {out_art} ({out_art.stat().st_size:,} B)")


if __name__ == "__main__":
    main()
