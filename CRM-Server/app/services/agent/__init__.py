"""CRM AI Agent services."""

__all__ = ["crm_agent_graph_service"]


def __getattr__(name: str) -> object:
    if name == "crm_agent_graph_service":
        from app.services.agent.graph import crm_agent_graph_service

        return crm_agent_graph_service
    raise AttributeError(name)
