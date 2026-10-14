"""对一份已生成报告做无需 API Key 的回归检查。"""

import argparse
import json
import re
from pathlib import Path


def load_case(path: Path, case_id: str) -> dict:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            if case.get("case_id") == case_id:
                return case
    raise SystemExit(f"case not found: {case_id}")


def evaluate(case: dict, report: str) -> dict:
    checks = [{"name": f"contains:{term}", "passed": term in report} for term in case.get("must_contain", [])]
    citation_ids = re.findall(r"\[(?:WEB|LOC)[^\]]+\]", report)
    checks.append({"name": "citation", "passed": bool(citation_ids) if case.get("must_have_citation") else True})
    checks.append({"name": "no-json-fence", "passed": "```json" not in report})
    passed = sum(1 for check in checks if check["passed"])
    return {"case_id": case["case_id"], "score": round(passed / len(checks) * 100), "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(load_case(args.case, args.case_id), args.report.read_text(encoding="utf-8"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["score"] == 100 else 1)


if __name__ == "__main__":
    main()
