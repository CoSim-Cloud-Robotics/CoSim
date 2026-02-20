import { authorizedClient } from './client';

export interface WorkspaceFile {
  id: string;
  workspace_id: string;
  path: string;
  content: string;
  language?: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceFilePayload {
  path: string;
  content: string;
  language?: string | null;
}

export const listWorkspaceFiles = async (token: string, workspaceId: string): Promise<WorkspaceFile[]> => {
  const { data } = await authorizedClient(token).get<WorkspaceFile[]>(`/v1/workspaces/${workspaceId}/files`);
  return data;
};

export const upsertWorkspaceFile = async (
  token: string,
  workspaceId: string,
  payload: WorkspaceFilePayload
): Promise<WorkspaceFile> => {
  const { data } = await authorizedClient(token).put<WorkspaceFile>(
    `/v1/workspaces/${workspaceId}/files`,
    payload
  );
  return data;
};

export const deleteWorkspacePath = async (
  token: string,
  workspaceId: string,
  path: string,
  recursive: boolean = false
): Promise<void> => {
  await authorizedClient(token).delete(`/v1/workspaces/${workspaceId}/files`, {
    params: { path, recursive }
  });
};

export const renameWorkspacePath = async (
  token: string,
  workspaceId: string,
  sourcePath: string,
  destinationPath: string
): Promise<WorkspaceFile[]> => {
  const { data } = await authorizedClient(token).post<WorkspaceFile[]>(
    `/v1/workspaces/${workspaceId}/files/rename`,
    {
      source_path: sourcePath,
      destination_path: destinationPath
    }
  );
  return data;
};
