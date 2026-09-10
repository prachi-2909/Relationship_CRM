"""Aggregate every route module under one router, mounted at the API prefix."""

from fastapi import APIRouter

from .routes import (
    audit_logs,
    auth,
    connections,
    dashboard,
    health,
    imports,
    interactions,
    moments,
    officials,
    organization,
    relationships,
    tasks,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(users.router)
api_router.include_router(organization.router)
api_router.include_router(officials.router)
api_router.include_router(relationships.router)
api_router.include_router(interactions.router)
api_router.include_router(connections.router)
api_router.include_router(tasks.router)
api_router.include_router(imports.router)
api_router.include_router(moments.router)
api_router.include_router(audit_logs.router)
