from __future__ import annotations
from typing import Any
from .repository import repository
from .router import DOMAIN_LABELS


def build_mcp_servers() -> dict[str,Any]:
    try:
        from mcp.server import MCPServer
    except Exception:
        return {}
    servers={}
    for domain,labels in DOMAIN_LABELS.items():
        server=MCPServer(name=f"Qanoni {labels['en']}")
        def make_search(d):
            def search_official_law(query:str,top_k:int=6)->dict:
                """Search the official Jordanian legal corpus for this domain."""
                return {'domain':d,'results':[x.model_dump() for x in repository.search(query,[d],min(max(top_k,1),12))]}
            return search_official_law
        def make_article(d):
            def get_article(article_number:str,law_hint:str='')->dict:
                """Retrieve official legal text for an article number and optional law hint."""
                q=f'المادة {article_number} {law_hint}'.strip()
                return {'domain':d,'article':article_number,'results':[x.model_dump() for x in repository.search(q,[d],10)]}
            return get_article
        def make_sources(d):
            def list_official_sources()->dict:
                """List official Jordanian authorities registered for this legal domain."""
                sources=[s for s in repository.source_registry() if d=='general' or d in s['domains']]
                return {'domain':d,'sources':sources}
            return list_official_sources
        server.tool(name='search_official_law')(make_search(domain))
        server.tool(name='get_article')(make_article(domain))
        server.tool(name='list_official_sources')(make_sources(domain))
        servers[domain]=server
    return servers
