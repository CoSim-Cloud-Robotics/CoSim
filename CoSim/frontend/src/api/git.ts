import { authorizedClient } from './client';

export interface GitStatusEntry {
  path: string;
  staged: string;
  unstaged: string;
}

export interface GitStatusResponse {
  entries: GitStatusEntry[];
}

export interface GitDiffResponse {
  diff: string;
}

export const getGitStatus = async (token: string, workspaceId: string): Promise<GitStatusResponse> => {
  const { data } = await authorizedClient(token).get<GitStatusResponse>(
    `/v1/workspaces/${workspaceId}/git/status`
  );
  return data;
};

export const gitAdd = async (token: string, workspaceId: string, paths?: string[]): Promise<void> => {
  await authorizedClient(token).post(`/v1/workspaces/${workspaceId}/git/add`, {
    paths
  });
};

export const gitCommit = async (token: string, workspaceId: string, message: string): Promise<{ status: string; output: string }> => {
  const { data } = await authorizedClient(token).post<{ status: string; output: string }>(
    `/v1/workspaces/${workspaceId}/git/commit`,
    { message }
  );
  return data;
};

export const gitDiff = async (
  token: string,
  workspaceId: string,
  options: { staged?: boolean; path?: string } = {}
): Promise<GitDiffResponse> => {
  const { data } = await authorizedClient(token).get<GitDiffResponse>(
    `/v1/workspaces/${workspaceId}/git/diff`,
    { params: options }
  );
  return data;
};
