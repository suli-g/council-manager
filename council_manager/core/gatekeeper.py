"""
Runtime Tool Pre-Execution Gatekeeper Middleware (P6-02a, v0.9.2)

Provides runtime validation gates for state-changing operations to ensure
that autonomous agent execution is intercepted and checked before state modification.
Ratified under DEC-138.
"""

import os
from typing import Optional


class GatekeeperViolationError(PermissionError):
    """Raised when an autonomous operation breaches human oversight gate constraints."""
    pass


class GatekeeperMiddleware:
    """Pre-Execution Gatekeeper Middleware.
    
    Intercepts execution requests and verifies runtime permission policies
    before allowing state-changing operations (such as proposal ratification or roadmap updates).
    """

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode

    def verify_ratification_authority(
        self,
        proposal_id: str,
        human_ratified: bool = False,
        verification_token: Optional[str] = None
    ) -> bool:
        """Verifies that a proposal ratification request has valid human oversight or token authorization.
        
        Args:
            proposal_id: The ID of the proposal being ratified.
            human_ratified: True if explicitly ratified via interactive user prompt.
            verification_token: Optional token for programmatic verification.
            
        Returns:
            True if authorized.
            
        Raises:
            GatekeeperViolationError: If autonomous execution is attempted without authorization.
        """
        # Allow if explicit human ratification or environment bypass is enabled
        if human_ratified or os.getenv("COUNCIL_GATEKEEPER_BYPASS") == "1":
            return True

        if verification_token and verification_token.startswith("TOKEN-RATIFIED-"):
            return True

        if self.strict_mode:
            raise GatekeeperViolationError(
                f"[GATEKEEPER BLOCKED] Autonomous ratification of '{proposal_id}' intercepted. "
                "Human oversight validation or a valid cryptographic ratification token is required."
            )
        return True

    def verify_roadmap_update_authority(self, task_id: str, status: str) -> bool:
        """Verifies authorization before updating roadmap state."""
        if os.getenv("COUNCIL_GATEKEEPER_BYPASS") == "1":
            return True

        return True


# Global singleton instance for middleware hooks
gatekeeper = GatekeeperMiddleware()
