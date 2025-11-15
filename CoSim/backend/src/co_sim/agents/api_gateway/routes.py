from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from co_sim.agents.api_gateway.client import forward_request

router = APIRouter(prefix="/v1")


@router.post("/auth/register")
async def register_user(request: Request, payload: dict[str, Any] = Body(...)) -> Any:
    response = await forward_request(request, "auth", "/v1/auth/register", method="POST", json=payload)
    return response.json()


@router.post("/auth/token")
async def login_for_token(request: Request) -> Any:
    body = await request.body()
    response = await forward_request(
        request,
        "auth",
        "/v1/auth/token",
        method="POST",
        content=body,
    )
    return response.json()


@router.get("/auth/me")
async def get_current_user(request: Request) -> Any:
    response = await forward_request(request, "auth", "/v1/auth/me")
    return response.json()


@router.post("/auth/auth0/exchange")
async def exchange_auth0_token(request: Request) -> Any:
    response = await forward_request(request, "auth", "/v1/auth/auth0/exchange", method="POST")
    return response.json()


@router.get("/users/me")
async def gateway_get_user_profile(request: Request) -> Any:
    response = await forward_request(request, "auth", "/v1/users/me")
    return response.json()


@router.patch("/users/me")
async def gateway_update_user_profile(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> Any:
    response = await forward_request(request, "auth", "/v1/users/me", method="PATCH", json=payload)
    return response.json()


@router.get("/users/me/settings")
async def gateway_get_user_settings(request: Request) -> Any:
    response = await forward_request(request, "auth", "/v1/users/me/settings")
    return response.json()


@router.patch("/users/me/settings")
async def gateway_update_user_settings(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> Any:
    response = await forward_request(request, "auth", "/v1/users/me/settings", method="PATCH", json=payload)
    return response.json()


@router.post("/sessions")
async def create_session(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> Any:
    response = await forward_request(request, "session", "/v1/sessions", method="POST", json=payload)
    return response.json()


@router.get("/sessions")
async def list_sessions(request: Request) -> Any:
    params = dict(request.query_params)
    response = await forward_request(request, "session", "/v1/sessions", method="GET", params=params)
    return response.json()


@router.get("/sessions/{session_id}")
async def get_session(request: Request, session_id: str) -> Any:
    response = await forward_request(request, "session", f"/v1/sessions/{session_id}")
    return response.json()


@router.post("/sessions/{session_id}/pause")
async def pause_session(request: Request, session_id: str) -> Any:
    response = await forward_request(request, "session", f"/v1/sessions/{session_id}/pause", method="POST")
    return response.json()


@router.post("/sessions/{session_id}/resume")
async def resume_session(request: Request, session_id: str) -> Any:
    response = await forward_request(request, "session", f"/v1/sessions/{session_id}/resume", method="POST")
    return response.json()


@router.post("/sessions/{session_id}/terminate")
async def terminate_session(request: Request, session_id: str) -> Any:
    response = await forward_request(request, "session", f"/v1/sessions/{session_id}/terminate", method="POST")
    return response.json()


@router.get("/organizations")
async def gateway_list_organizations(request: Request) -> Any:
    response = await forward_request(request, "project", "/v1/organizations", method="GET", params=dict(request.query_params))
    return response.json()


@router.post("/organizations")
async def gateway_create_organization(request: Request, payload: dict[str, Any] = Body(...)) -> Any:
    response = await forward_request(request, "project", "/v1/organizations", method="POST", json=payload)
    return response.json()


@router.post("/projects")
async def gateway_create_project(request: Request, payload: dict[str, Any] = Body(...)) -> Any:
    response = await forward_request(request, "project", "/v1/projects", method="POST", json=payload)
    return response.json()


@router.get("/projects")
async def gateway_list_projects(request: Request) -> Any:
    params = dict(request.query_params)
    response = await forward_request(request, "project", "/v1/projects", method="GET", params=params)
    return response.json()


@router.get("/projects/{project_id}")
async def gateway_get_project(request: Request, project_id: str) -> Any:
    response = await forward_request(request, "project", f"/v1/projects/{project_id}")
    return response.json()


@router.patch("/projects/{project_id}")
async def gateway_update_project(request: Request, project_id: str, payload: dict[str, Any] = Body(default_factory=dict)) -> Any:
    response = await forward_request(
        request, "project", f"/v1/projects/{project_id}", method="PATCH", json=payload
    )
    return response.json()


@router.delete("/projects/{project_id}")
async def gateway_delete_project(request: Request, project_id: str) -> Any:
    response = await forward_request(request, "project", f"/v1/projects/{project_id}", method="DELETE")
    if response.content:
        return response.json()
    return {"status": "deleted"}


@router.post("/workspaces")
async def gateway_create_workspace(request: Request, payload: dict[str, Any] = Body(...)) -> Any:
    response = await forward_request(request, "project", "/v1/workspaces", method="POST", json=payload)
    return response.json()


@router.get("/workspaces")
async def gateway_list_workspaces(request: Request) -> Any:
    params = dict(request.query_params)
    response = await forward_request(request, "project", "/v1/workspaces", method="GET", params=params)
    return response.json()


@router.patch("/workspaces/{workspace_id}")
async def gateway_update_workspace(
    request: Request, workspace_id: str, payload: dict[str, Any] = Body(default_factory=dict)
) -> Any:
    response = await forward_request(
        request, "project", f"/v1/workspaces/{workspace_id}", method="PATCH", json=payload
    )
    return response.json()


@router.delete("/workspaces/{workspace_id}")
async def gateway_delete_workspace(request: Request, workspace_id: str) -> Any:
    response = await forward_request(request, "project", f"/v1/workspaces/{workspace_id}", method="DELETE")
    if response.content:
        return response.json()
    return {"status": "deleted"}


@router.get("/workspaces/{workspace_id}/files")
async def gateway_list_workspace_files(request: Request, workspace_id: str) -> Any:
    response = await forward_request(request, "project", f"/v1/workspaces/{workspace_id}/files", method="GET")
    return response.json()


@router.put("/workspaces/{workspace_id}/files")
async def gateway_upsert_workspace_file(
    request: Request, workspace_id: str, payload: dict[str, Any] = Body(default_factory=dict)
) -> Any:
    response = await forward_request(
        request, "project", f"/v1/workspaces/{workspace_id}/files", method="PUT", json=payload
    )
    return response.json()


@router.post("/runs/build")
async def gateway_trigger_build(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> Any:
    # Placeholder: will be wired to build agent in later phases
    return {"status": "accepted", "payload": payload}


@router.post("/runs/python")
async def gateway_trigger_python_run(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> Any:
    return {"status": "accepted", "payload": payload}


@router.post("/rl/jobs")
async def gateway_create_rl_job(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> Any:
    return {"status": "scheduled", "payload": payload}


@router.post("/slam/experiments")
async def gateway_create_slam_experiment(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> Any:
    return {"status": "scheduled", "payload": payload}

@router.post("/collab/documents")
async def create_document_session(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> Any:
    response = await forward_request(request, "collab", "/v1/collab/documents", method="POST", json=payload)
    return response.json()


@router.get("/collab/documents/{document_id}")
async def get_document_session(request: Request, document_id: str) -> Any:
    response = await forward_request(request, "collab", f"/v1/collab/documents/{document_id}")
    return response.json()


@router.post("/collab/documents/{document_id}/participants")
async def add_document_participant(request: Request, document_id: str, payload: dict[str, Any] = Body(default_factory=dict)) -> Any:
    response = await forward_request(request, "collab", f"/v1/collab/documents/{document_id}/participants", method="POST", json=payload)
    return response.json()
