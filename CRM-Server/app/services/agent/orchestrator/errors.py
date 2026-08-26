"""Operational errors crossing internal Root Orchestrator seams."""


class RootContextUnavailableError(RuntimeError):
    """Authoritative session context could not be loaded safely."""


class InteractionResolutionUnavailableError(RuntimeError):
    """A structured interaction could not be authoritatively validated."""


class WorkflowCheckpointUnavailableError(RuntimeError):
    """The durable Workflow checkpoint could not be loaded or resumed."""


class WorkflowExecutionFailedError(RuntimeError):
    """Workflow execution failed after authoritative routing."""
