"""Post-write maintenance policy matching for RP Phase A."""
from __future__ import annotations

from fnmatch import fnmatchcase

from rp.models.post_write_policy import (
    PolicyDecision,
    PolicyRule,
    PostWriteMaintenancePolicy,
)


class PostWriteApplyHandler:
    """Decide how one proposal should be governed under the current policy."""

    def decide(
        self,
        *,
        mode: str,
        domain: str,
        operation_kind: str,
        policy: PostWriteMaintenancePolicy,
        domain_path: str | None = None,
    ) -> PolicyDecision:
        candidate = domain_path or f"{domain}.*"
        matching_rules = [
            rule
            for rule in policy.rules
            if self._matches(rule, mode=mode, operation_kind=operation_kind, candidate=candidate)
        ]
        if not matching_rules:
            return policy.fallback_decision

        best_rule = sorted(
            matching_rules,
            key=self._specificity_key,
            reverse=True,
        )[0]
        return best_rule.decision

    @staticmethod
    def _matches(
        rule: PolicyRule,
        *,
        mode: str,
        operation_kind: str,
        candidate: str,
    ) -> bool:
        if rule.mode != mode:
            return False
        if rule.operation_kind not in {"*", operation_kind}:
            return False
        return fnmatchcase(candidate, rule.domain_pattern)

    @staticmethod
    def _specificity_key(rule: PolicyRule) -> tuple[int, int, int]:
        wildcard_count = rule.domain_pattern.count("*")
        exact_operation = 0 if rule.operation_kind == "*" else 1
        return (exact_operation, -wildcard_count, len(rule.domain_pattern))

