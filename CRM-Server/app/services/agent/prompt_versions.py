"""
Prompt Version Management - Version registry and A/B testing support

Purpose: Track prompt versions, enable A/B testing, and provide rollback capability.

Used by:
- prompts.py: Get active prompt version
- Future: Admin API for version switching
"""

from typing import Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# Prompt version registry
VERSIONS: Dict[str, Dict[str, Any]] = {
    "v1.0": {
        "created": "2026-06-26",
        "description": "Initial: 4-scenario classification",
        "prompt_key": "SUMMARY_SYSTEM_PROMPT",
        "active": True,
    },
    "v1.1": {
        "created": "2026-06-26",
        "description": "Add edge scenario handling (timeout, partial_success, cache_miss)",
        "prompt_key": "SUMMARY_SYSTEM_PROMPT_V1_1",
        "active": False,
    },
}


class PromptVersionManager:
    """Prompt version management and A/B testing"""

    def get_active_version(self) -> str:
        """
        Get current active version.

        Returns:
            Version string (e.g., "v1.0")
        """
        for version, info in VERSIONS.items():
            if info.get("active", False):
                return version
        return "v1.0"  # Default fallback

    def get_prompt(self, version: str = None) -> str:
        """
        Get prompt text for specified version (or active version).

        Args:
            version: Version string (optional, defaults to active)

        Returns:
            Prompt text
        """
        version = version or self.get_active_version()
        version_info = VERSIONS.get(version, VERSIONS["v1.0"])

        # Import from prompts.py
        from app.services.agent.prompts import AgentPrompts

        prompts = AgentPrompts()

        prompt_key = version_info.get("prompt_key", "SUMMARY_SYSTEM_PROMPT")
        prompt_text = getattr(prompts, prompt_key, prompts.SUMMARY_SYSTEM_PROMPT)

        logger.debug(f"Retrieved prompt for version {version}")
        return prompt_text

    def activate_version(self, version: str) -> bool:
        """
        Activate a version (for A/B testing or rollback).

        Args:
            version: Version string to activate

        Returns:
            True if successful, False if version not found
        """
        if version not in VERSIONS:
            logger.warning(f"Cannot activate unknown version: {version}")
            return False

        # Deactivate all versions
        for v in VERSIONS:
            VERSIONS[v]["active"] = False

        # Activate target version
        VERSIONS[version]["active"] = True
        logger.info(f"Activated prompt version: {version}")
        return True

    def create_version(
        self,
        version: str,
        description: str,
        prompt_key: str,
    ) -> None:
        """
        Create new version entry (does not modify prompts.py).

        Args:
            version: Version string (e.g., "v1.2")
            description: Version description
            prompt_key: Key name for prompt in AgentPrompts class
        """
        VERSIONS[version] = {
            "created": datetime.now().strftime("%Y-%m-%d"),
            "description": description,
            "prompt_key": prompt_key,
            "active": False,
        }
        logger.info(f"Created prompt version entry: {version}")


__all__ = ["PromptVersionManager", "VERSIONS"]