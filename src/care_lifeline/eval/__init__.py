from __future__ import annotations

from care_lifeline.db import session_store
from care_lifeline.eval.promote import promote_review


def main() -> None:
    import sys

    review_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if review_id is None:
        print("用法: python -m care_lifeline.eval.promote <review_id>")
        raise SystemExit(1)
    review = session_store.get_review(review_id)
    if review is None:
        print(f"审阅项 {review_id} 不存在")
        raise SystemExit(1)
    case = promote_review(review)
    print(f"已写入评测样本: {case['thread_id']} -> {case['decision']}")


if __name__ == "__main__":
    main()
