import { useAuth0 } from '@auth0/auth0-react';
import { createContext, ReactNode, useCallback, useEffect, useMemo, useState } from 'react';

import { exchangeAuth0Token, me } from '../api/auth';
import type { User } from '../api/types';

export interface AuthContextValue {
  token: string | null;
  user: User | null;
  login: (token: string, options?: { user?: User; source?: 'auth0' | 'legacy' }) => void;
  logout: () => void;
  refreshUser: () => Promise<void>;
  isLoading: boolean;
  isAuthenticated: boolean;
  authSource: 'auth0' | 'legacy' | null;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

interface Props {
  children: ReactNode;
}

export const AuthProvider = ({ children }: Props) => {
  const {
    isAuthenticated: auth0IsAuthenticated,
    isLoading: auth0IsLoading,
    logout: auth0Logout,
    user: auth0User,
    getIdTokenClaims,
  } = useAuth0();

  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authSource, setAuthSource] = useState<'auth0' | 'legacy' | null>(null);

  useEffect(() => {
    const storedToken = window.localStorage.getItem('cosim-token');
    const storedSource = window.localStorage.getItem('cosim-auth-source') as 'auth0' | 'legacy' | null;

    if (storedToken && storedSource === 'legacy') {
      setToken(storedToken);
      setAuthSource('legacy');
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authSource === 'legacy' && token) {
      window.localStorage.setItem('cosim-token', token);
      window.localStorage.setItem('cosim-auth-source', 'legacy');
    } else if (!token) {
      window.localStorage.removeItem('cosim-token');
      window.localStorage.removeItem('cosim-auth-source');
    } else if (authSource === 'auth0') {
      window.localStorage.removeItem('cosim-token');
      window.localStorage.removeItem('cosim-auth-source');
    }
  }, [token, authSource]);

    // Get Auth0 access token when authenticated
  useEffect(() => {
    const syncAuth0Token = async () => {
      if (authSource === 'legacy') {
        setIsLoading(false);
        return;
      }

      if (auth0IsAuthenticated && !auth0IsLoading) {
        try {
          const claims = await getIdTokenClaims();
          const auth0IdToken = claims?.__raw;

          if (!auth0IdToken) {
            throw new Error('Missing Auth0 ID token');
          }

          // Exchange Auth0 ID token for backend token
          const { access_token: backendToken } = await exchangeAuth0Token(auth0IdToken);
          
          setToken(backendToken);
          setAuthSource('auth0');
          setIsLoading(false);
        } catch (error) {
          console.error('Failed to exchange Auth0 token:', error);
          setToken(null);
          setAuthSource(null);
          setIsLoading(false);
        }
      } else if (!auth0IsLoading) {
        if (authSource === 'auth0') {
          setToken(null);
          setAuthSource(null);
        }
        setIsLoading(false);
      } else {
        setIsLoading(true);
      }
    };

    syncAuth0Token();
  }, [auth0IsAuthenticated, auth0IsLoading, authSource, getIdTokenClaims]);

  const refreshUser = useCallback(async () => {
    if (!token) return null;
    const latestUser = await me(token);
    setUser(latestUser);
    return latestUser;
  }, [token]);

  // Fetch user profile from backend when we have a token
  useEffect(() => {
    if (!token) {
      setUser(null);
      return;
    }

    refreshUser().catch((error: any) => {
      if (error.response?.status === 404 && authSource === 'auth0' && auth0User) {
        setUser({
          id: auth0User.sub || '',
          email: auth0User.email || '',
          full_name: auth0User.name || auth0User.nickname || null,
          display_name: auth0User.name || auth0User.nickname || null,
          bio: null,
          is_active: true,
          is_superuser: false,
          plan: 'free',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        } as User);
      } else if (error.response?.status === 404 && authSource === 'legacy') {
        setUser((current) => current);
      } else {
        console.error('Failed to fetch user:', error);
        setUser(null);
      }
    });
  }, [token, auth0User, authSource, refreshUser]);

  const handleLogin = useCallback(
    (newToken: string, options?: { user?: User; source?: 'auth0' | 'legacy' }) => {
      setToken(newToken);
      if (options?.user) {
        setUser(options.user);
      }
      setAuthSource(options?.source ?? 'legacy');
      setIsLoading(false);
    },
    []
  );

  const handleLogout = useCallback(() => {
    setUser(null);
    setToken(null);
    if (authSource === 'legacy') {
      window.localStorage.removeItem('cosim-token');
      window.localStorage.removeItem('cosim-auth-source');
      setAuthSource(null);
      if (typeof window !== 'undefined') {
        window.location.assign(`${window.location.origin}/`);
      }
    } else {
      setAuthSource(null);
      auth0Logout({ logoutParams: { returnTo: `${window.location.origin}/` } });
    }
  }, [auth0Logout, authSource]);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      user,
      login: handleLogin,
      logout: handleLogout,
      refreshUser,
      isLoading,
      isAuthenticated: !!token,
      authSource,
    }),
    [token, user, handleLogin, handleLogout, refreshUser, isLoading, authSource]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export default AuthContext;
