"""Quick smoke-test for the retrieval engine."""
import sys
sys.path.insert(0, ".")

from app.retrieval_engine import engine

TESTS = [
    # Should match
    ("whats the capital of france",          True),
    ("tell me about machine learning",       True),
    ("how do i sleep better at night",       True),
    ("hey",                                  True),   # casual → "hey whats up"
    ("what does CPU mean",                   True),
    ("difference between ram and harddrive", True),   # paraphrase
    ("python 2 vs python 3",                 True),
    ("thank you",                            True),   # paraphrase of "thanks"
    # Should NOT match (below threshold)
    ("xkzqw florp bazzle",                   False),
    ("1234567890",                           False),
]

print(f"\n{'QUERY':<45} {'MATCHED':<8} {'SCORE':<7} {'BEST MATCH'}")
print("-" * 110)

passed = 0
for query, expect_match in TESTS:
    result = engine.query(query)
    ok = result["matched"] == expect_match
    passed += ok
    flag   = "" if ok else " << FAIL"
    matched_q = result["matched_question"] or "(no match)"
    print(
        f"{query:<45} {str(result['matched']):<8} "
        f"{result['combined_score']:.3f}  {matched_q}{flag}"
    )

print(f"\n{passed}/{len(TESTS)} tests passed.")
