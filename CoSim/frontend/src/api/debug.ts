import { authorizedClient } from './client';

export interface DebugStartRequest {
  language: 'python' | 'cpp';
  file_path?: string;
  binary_path?: string;
  args?: string[];
  adapter?: 'gdb' | 'lldb';
  port?: number;
}

export interface DebugSessionInfo {
  debug_id: string;
  language: 'python' | 'cpp';
  adapter?: string;
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
