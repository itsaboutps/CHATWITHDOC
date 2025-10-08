"""Evaluation harness for Document Q&A.

Usage (inside backend container):

python -m scripts.evaluate --questions data/questions.csv --output results.json

questions.csv format:
question,expected_keywords (semicolon separated)
"What is the leave policy?","leave;policy;days"
"""
from __future__ import annotations
import csv, json, argparse, time, os
import httpx

def load_questions(path: str):
    rows = []
    with open(path) as f:
        r = csv.DictReader(f)
        for row in r:
            kws = [k.strip() for k in row.get("expected_keywords", "").split(";") if k.strip()]
            rows.append({"question": row["question"], "expected_keywords": kws})
    return rows

def score_answer(answer: str, keywords: list[str]):
    answer_l = answer.lower()
    hits = sum(1 for k in keywords if k.lower() in answer_l)
    return hits / max(1, len(keywords))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--api", default=os.environ.get("API_URL", "http://localhost:8000"))
    args = ap.parse_args()
    qs = load_questions(args.questions)
    results = []
    with httpx.Client(timeout=60) as client:
        for q in qs:
            t0 = time.time()
            r = client.post(f"{args.api}/ask", json={"question": q["question"]})
            data = r.json()
            latency = data.get("latency_ms", int((time.time() - t0) * 1000))
            score = score_answer(data.get("answer", ""), q["expected_keywords"])
            results.append({
                "question": q["question"],
                "keywords": q["expected_keywords"],
                "answer": data.get("answer"),
                "answer_type": data.get("answer_type"),
                "score": score,
                "latency_ms": latency
            })
    with open(args.output, "w") as f:
        json.dump({"results": results}, f, indent=2)
    avg = sum(r["score"] for r in results)/max(1,len(results))
    print(f"Average keyword coverage: {avg:.2%} across {len(results)} questions")

if __name__ == "__main__":
    main()
