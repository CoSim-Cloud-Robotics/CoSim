import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Layout from '../components/Layout';
import { useAuth } from '../hooks/useAuth';
import { getUserProfile, updateUserProfile } from '../api/user';
import type { UserProfileUpdatePayload } from '../api/types';

// Icons
const UserIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
    <circle cx="12" cy="7" r="4"></circle>
  </svg>
);

const MailIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
    <polyline points="22,6 12,13 2,6"></polyline>
  </svg>
);

const CalendarIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
    <line x1="16" y1="2" x2="16" y2="6"></line>
    <line x1="8" y1="2" x2="8" y2="6"></line>
    <line x1="3" y1="10" x2="21" y2="10"></line>
  </svg>
);

const EditIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
  </svg>
);

const SaveIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path>
    <polyline points="17 21 17 13 7 13 7 21"></polyline>
    <polyline points="7 3 7 8 15 8"></polyline>
  </svg>
);

const ProfilePage = () => {
  const { user, token, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [displayName, setDisplayName] = useState(
    user?.display_name || user?.full_name || user?.email?.split('@')[0] || ''
  );
  const [bio, setBio] = useState(user?.bio || '');

  const profileQuery = useQuery({
    queryKey: ['user-profile'],
    queryFn: () => getUserProfile(token!),
    enabled: Boolean(token),
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!profileQuery.data || isEditing) return;
    setDisplayName(
      profileQuery.data.display_name ||
        profileQuery.data.full_name ||
        profileQuery.data.email?.split('@')[0] ||
        ''
    );
    setBio(profileQuery.data.bio || '');
  }, [profileQuery.data, isEditing]);

  const updateProfileMutation = useMutation({
    mutationFn: async (payload: UserProfileUpdatePayload) => {
      return updateUserProfile(token!, payload);
    },
    onSuccess: async (updatedProfile) => {
      queryClient.setQueryData(['user-profile'], updatedProfile);
      setIsEditing(false);
      try {
        await refreshUser();
      } catch (error) {
        // Refresh is best-effort; errors are logged upstream
      }
    }
  });

  const handleSave = () => {
    if (!token) return;
    const payload: UserProfileUpdatePayload = {
      display_name: displayName,
      bio,
    };

    updateProfileMutation.mutate(payload);
  };

  const profile = profileQuery.data;

  const getInitials = (name?: string | null, email?: string | null | undefined) => {
    const source = name || (email ? email.split('@')[0] : '');
    if (!source) return 'U';
    return source.slice(0, 2).toUpperCase();
  };

  const memberSince = useMemo(() => {
    const createdAt = profile?.created_at || user?.created_at;
    if (!createdAt) return '';
    return new Date(createdAt).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  }, [profile?.created_at, user?.created_at]);

  if (profileQuery.isLoading) {
    return (
      <Layout title="Profile">
        <div style={{ padding: '2rem', textAlign: 'center' }}>Loading profile…</div>
      </Layout>
    );
  }

  if (profileQuery.isError) {
    return (
      <Layout title="Profile">
        <div style={{ padding: '2rem', textAlign: 'center', color: '#b91c1c' }}>
          Unable to load your profile right now. Please try again later.
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Profile">
      <div style={{ maxWidth: '800px', margin: '0 auto' }}>
        {/* Profile Header Card */}
        <div className="card" style={{
          marginBottom: '2rem',
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          color: 'white',
          textAlign: 'center',
          padding: '3rem 2rem'
        }}>
          <div style={{
            width: '120px',
            height: '120px',
            borderRadius: '50%',
            background: 'rgba(255, 255, 255, 0.25)',
            backdropFilter: 'blur(10px)',
            border: '4px solid rgba(255, 255, 255, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '3rem',
            fontWeight: 700,
            margin: '0 auto 1.5rem',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.2)'
          }}>
            {getInitials(profile?.display_name || profile?.full_name, profile?.email || user?.email)}
          </div>
          <h1 style={{ margin: '0 0 0.5rem 0', fontSize: '2rem', fontWeight: 700 }}>
            {displayName || profile?.email}
          </h1>
          <p style={{ margin: 0, fontSize: '1.125rem', opacity: 0.95 }}>
            {profile?.email ?? user?.email}
          </p>
        </div>

        {/* Profile Details Card */}
        <div className="card" style={{ marginBottom: '2rem' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '1.5rem',
            paddingBottom: '1rem',
            borderBottom: '2px solid #e2e8f0'
          }}>
            <h2 style={{ margin: 0, fontSize: '1.5rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <UserIcon />
              Profile Information
            </h2>
            {!isEditing && (
              <button
                onClick={() => setIsEditing(true)}
                className="secondary-button"
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <EditIcon />
                Edit
              </button>
            )}
          </div>

          {/* Info Grid */}
          <div style={{ display: 'grid', gap: '1.5rem' }}>
            {/* Display Name */}
            <div>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: 600,
                color: '#475569',
                fontSize: '0.875rem',
                textTransform: 'uppercase',
                letterSpacing: '0.05em'
              }}>
                Display Name
              </label>
              {isEditing ? (
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    fontSize: '1rem',
                    border: '2px solid #e2e8f0',
                    borderRadius: '8px'
                  }}
                />
              ) : (
                <p style={{ margin: 0, fontSize: '1.125rem', color: '#1e293b' }}>
                  {displayName}
                </p>
              )}
            </div>

            {/* Email */}
            <div>
              <label style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                marginBottom: '0.5rem',
                fontWeight: 600,
                color: '#475569',
                fontSize: '0.875rem',
                textTransform: 'uppercase',
                letterSpacing: '0.05em'
              }}>
                <MailIcon />
                Email Address
              </label>
              <p style={{ margin: 0, fontSize: '1.125rem', color: '#1e293b' }}>
                {profile?.email ?? user?.email}
              </p>
              <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.875rem', color: '#64748b' }}>
                Email cannot be changed
              </p>
            </div>

            {/* Bio */}
            <div>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: 600,
                color: '#475569',
                fontSize: '0.875rem',
                textTransform: 'uppercase',
                letterSpacing: '0.05em'
              }}>
                Bio
              </label>
              {isEditing ? (
                <textarea
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Tell us about yourself..."
                  rows={4}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    fontSize: '1rem',
                    border: '2px solid #e2e8f0',
                    borderRadius: '8px',
                    resize: 'vertical'
                  }}
                />
              ) : (
                <p style={{ margin: 0, fontSize: '1rem', color: '#64748b', fontStyle: bio ? 'normal' : 'italic' }}>
                  {bio || 'No bio added yet'}
                </p>
              )}
            </div>

            {/* Member Since */}
            <div>
              <label style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                marginBottom: '0.5rem',
                fontWeight: 600,
                color: '#475569',
                fontSize: '0.875rem',
                textTransform: 'uppercase',
                letterSpacing: '0.05em'
              }}>
                <CalendarIcon />
                Member Since
              </label>
              <p style={{ margin: 0, fontSize: '1.125rem', color: '#1e293b' }}>
                {memberSince}
              </p>
            </div>
          </div>

          {/* Edit Actions */}
          {isEditing && (
            <div style={{
              display: 'flex',
              gap: '1rem',
              justifyContent: 'flex-end',
              marginTop: '2rem',
              paddingTop: '1.5rem',
              borderTop: '2px solid #e2e8f0'
            }}>
              <button
                onClick={() => setIsEditing(false)}
                className="secondary-button"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="primary-button"
                disabled={updateProfileMutation.isPending}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                {updateProfileMutation.isPending ? (
                  <>
                    <div style={{
                      width: '16px',
                      height: '16px',
                      border: '2px solid white',
                      borderTopColor: 'transparent',
                      borderRadius: '50%',
                      animation: 'spin 0.8s linear infinite'
                    }} />
                    Saving...
                  </>
                ) : (
                  <>
                    <SaveIcon />
                    Save Changes
                  </>
                )}
              </button>
            </div>
          )}

          {updateProfileMutation.isError && (
            <div style={{
              marginTop: '1rem',
              padding: '0.75rem',
              background: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: '8px',
              color: '#b91c1c',
              fontSize: '0.875rem'
            }}>
              Failed to update profile. Please try again.
            </div>
          )}

          {updateProfileMutation.isSuccess && (
            <div style={{
              marginTop: '1rem',
              padding: '0.75rem',
              background: '#f0fdf4',
              border: '1px solid #bbf7d0',
              borderRadius: '8px',
              color: '#15803d',
              fontSize: '0.875rem'
            }}>
              ✓ Profile updated successfully!
            </div>
          )}
        </div>

        {/* Stats Card */}
        <div className="card">
          <h2 style={{ margin: '0 0 1.5rem 0', fontSize: '1.5rem', color: '#1e293b' }}>
            Activity Stats
          </h2>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '1.5rem'
          }}>
            <div style={{
              padding: '1.5rem',
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              borderRadius: '12px',
              color: 'white',
              textAlign: 'center'
            }}>
              <div style={{ fontSize: '2.5rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                {profile?.activity_stats.projects_created ?? 0}
              </div>
              <div style={{ fontSize: '0.875rem', opacity: 0.95 }}>
                Projects Created
              </div>
            </div>
            <div style={{
              padding: '1.5rem',
              background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
              borderRadius: '12px',
              color: 'white',
              textAlign: 'center'
            }}>
              <div style={{ fontSize: '2.5rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                {profile?.activity_stats.active_sessions ?? 0}
              </div>
              <div style={{ fontSize: '0.875rem', opacity: 0.95 }}>
                Active Sessions
              </div>
            </div>
            <div style={{
              padding: '1.5rem',
              background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
              borderRadius: '12px',
              color: 'white',
              textAlign: 'center'
            }}>
              <div style={{ fontSize: '2.5rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                {(profile?.activity_stats.compute_hours ?? 0).toFixed(2)}h
              </div>
              <div style={{ fontSize: '0.875rem', opacity: 0.95 }}>
                Compute Hours
              </div>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </Layout>
  );
};

export default ProfilePage;
