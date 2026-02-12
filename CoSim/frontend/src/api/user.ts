import { authorizedClient } from './client';
import type {
  UserPreferences,
  UserProfile,
  UserProfileUpdatePayload,
  UserSettingsPayload,
} from './types';

export const getUserProfile = async (token: string): Promise<UserProfile> => {
  const client = authorizedClient(token);
  const { data } = await client.get<UserProfile>('/v1/users/me');
  return data;
};

export const updateUserProfile = async (
  token: string,
  payload: UserProfileUpdatePayload
): Promise<UserProfile> => {
  const client = authorizedClient(token);
  const { data } = await client.patch<UserProfile>('/v1/users/me', payload);
  return data;
};

export const getUserSettings = async (token: string): Promise<UserPreferences> => {
  const client = authorizedClient(token);
  const { data } = await client.get<UserPreferences>('/v1/users/me/settings');
  return data;
};

export const updateUserSettings = async (
  token: string,
  payload: UserSettingsPayload
): Promise<UserPreferences> => {
  const client = authorizedClient(token);
  const { data } = await client.patch<UserPreferences>('/v1/users/me/settings', payload);
  return data;
};
