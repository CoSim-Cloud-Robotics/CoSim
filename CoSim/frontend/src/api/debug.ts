import { authorizedClient } from './client';

export interface DebugStartRequest {
  file_path: string;
  args?: string[];
  port?: number;
}

export interface DebugSessionInfo {
  debug_id: string;
  language?: 'python';
  port: number;
  command: string[];
  working_dir: string;
}

export const startDebugSession = async (
  token: string,
  sessionId: string,
  payload: DebugStartRequest
): Promise<DebugSessionInfo> => {
  const { data } = await authorizedClient(token).post<DebugSessionInfo>(
    `/v1/sessions/${sessionId}/debug/start`,
    payload
  );
  return data;
};

export const stopDebugSession = async (
  token: string,
  sessionId: string,
  debugId: string
): Promise<{ status: string }> => {
  const { data } = await authorizedClient(token).post<{ status: string }>(
    `/v1/sessions/${sessionId}/debug/${debugId}/stop`
  );
  return data;
};
