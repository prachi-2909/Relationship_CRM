"""Aggregate every route module under one router, mounted at the API prefix."""

from fastapi import APIRouter

from .routes import (
    agent,
    app_release,
    ask,
    attestation,
    audit_logs,
    auth,
    call_intelligence,
    connections,
    csps,
    dashboard,
    dc_territory,
    health,
    imports,
    intelligence,
    interactions,
    knowledge,
    memory,
    moments,
    officials,
    opportunities,
    organization,
    presence,
    relationships,
    strategies,
    tasks,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(attestation.router)
api_router.include_router(dashboard.router)
api_router.include_router(ask.router)
api_router.include_router(agent.router)
api_router.include_router(users.router)
api_router.include_router(organization.router)
api_router.include_router(officials.router)
api_router.include_router(relationships.router)
api_router.include_router(interactions.router)
api_router.include_router(connections.router)
api_router.include_router(csps.router)
api_router.include_router(intelligence.router)
api_router.include_router(opportunities.router)
api_router.include_router(tasks.router)
api_router.include_router(imports.router)
api_router.include_router(moments.router)
api_router.include_router(memory.router)
api_router.include_router(knowledge.router)
api_router.include_router(strategies.router)
api_router.include_router(call_intelligence.router)
api_router.include_router(dc_territory.router)
api_router.include_router(app_release.router)
api_router.include_router(audit_logs.router)
api_router.include_router(presence.router)
