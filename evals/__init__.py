"""Buddi eval harness — manual §2.2 week 3 deliverable.

This package houses the offline regression suite used to:

  * Tune the agent confidence floor in ``core/agent.py``
    (``BUDDI_HCC_CONFIDENCE_FLOOR``).
  * Gate every PR via the CI workflow on top-3-codes precision /
    recall regression.
  * Produce the precision / recall / abstain-rate numbers the founder
    cites in security questionnaires and pilot reviews.

See ``evals/README.md`` for the contract a new golden-set case must
satisfy and ``evals/run_eval.py`` for the entry point CI runs.
"""
