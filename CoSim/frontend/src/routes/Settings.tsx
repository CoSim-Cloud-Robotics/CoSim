import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Layout from '../components/Layout';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../contexts/ThemeContext';
import { getUserSettings, updateUserSettings } from '../api/user';
import type { UserSettingsPayload } from '../api/types';

// Icons
const SettingsIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="3"></circle>
    <path d="M12 1v6m0 6v6m9-9h-6m-6 0H3"></path>
  </svg>
);

const BellIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
    <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
  </svg>
);

const ShieldIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
  </svg>
);

const PaletteIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="13.5" cy="6.5" r=".5"></circle>
    <circle cx="17.5" cy="10.5" r=".5"></circle>
    <circle cx="8.5" cy="7.5" r=".5"></circle>
    <circle cx="6.5" cy="12.5" r=".5"></circle>
    <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"></path>
  </svg>
);

const DatabaseIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
  </svg>
);

const SaveIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path>
    <polyline points="17 21 17 13 7 13 7 21"></polyline>
    <polyline points="7 3 7 8 15 8"></polyline>
  </svg>
);

const SettingsPage = () => {
  const { user, token, refreshUser } = useAuth();
  const { theme, setTheme } = useTheme();
  const queryClient = useQueryClient();
  
  // Notification Settings
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [projectUpdates, setProjectUpdates] = useState(true);
  const [sessionAlerts, setSessionAlerts] = useState(true);
  const [billingAlerts, setBillingAlerts] = useState(true);

  // Appearance Settings - now using theme context
  const [editorFontSize, setEditorFontSize] = useState(14);

  // Privacy Settings
  const [profileVisibility, setProfileVisibility] = useState<'public' | 'private'>('private');
  const [showActivity, setShowActivity] = useState(false);

  // Resource Settings
  const [autoHibernate, setAutoHibernate] = useState(true);
  const [hibernateMinutes, setHibernateMinutes] = useState(5);

  const settingsQuery = useQuery({
    queryKey: ['user-settings'],
    queryFn: () => getUserSettings(token!),
    enabled: Boolean(token),
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!settingsQuery.data) return;

    const { notifications, appearance, privacy, resources } = settingsQuery.data;
    setEmailNotifications(notifications.email_enabled);
    setProjectUpdates(notifications.project_updates);
    setSessionAlerts(notifications.session_alerts);
    setBillingAlerts(notifications.billing_alerts);

    setEditorFontSize(appearance.editor_font_size);
    if (appearance.theme !== theme) {
      setTheme(appearance.theme);
    }

    setProfileVisibility(privacy.profile_visibility);
    setShowActivity(privacy.show_activity);

    setAutoHibernate(resources.auto_hibernate);
    setHibernateMinutes(resources.hibernate_minutes);
  }, [settingsQuery.data, setTheme, theme]);

  const saveSettingsMutation = useMutation({
    mutationFn: async (settings: UserSettingsPayload) => updateUserSettings(token!, settings),
    onSuccess: async (updatedSettings) => {
      queryClient.setQueryData(['user-settings'], updatedSettings);
      try {
        await refreshUser();
      } catch (error) {
        /* ignore refresh failure */
      }
    }
  });

  const handleSaveSettings = () => {
    if (!token) return;

    const payload: UserSettingsPayload = {
      notifications: {
        email_enabled: emailNotifications,
        project_updates: projectUpdates,
        session_alerts: sessionAlerts,
        billing_alerts: billingAlerts,
      },
      appearance: {
        theme,
        editor_font_size: editorFontSize,
      },
      privacy: {
        profile_visibility: profileVisibility,
        show_activity: showActivity,
      },
      resources: {
        auto_hibernate: autoHibernate,
        hibernate_minutes: hibernateMinutes,
      },
    };

    saveSettingsMutation.mutate(payload);
  };

  const originalSettings = settingsQuery.data;

  const hasUnsavedChanges = useMemo(() => {
    if (!originalSettings) {
      return false;
    }

    return (
      originalSettings.notifications.email_enabled !== emailNotifications ||
      originalSettings.notifications.project_updates !== projectUpdates ||
      originalSettings.notifications.session_alerts !== sessionAlerts ||
      originalSettings.notifications.billing_alerts !== billingAlerts ||
      originalSettings.appearance.theme !== theme ||
      originalSettings.appearance.editor_font_size !== editorFontSize ||
      originalSettings.privacy.profile_visibility !== profileVisibility ||
      originalSettings.privacy.show_activity !== showActivity ||
      originalSettings.resources.auto_hibernate !== autoHibernate ||
      originalSettings.resources.hibernate_minutes !== hibernateMinutes
    );
  }, [
    originalSettings,
    emailNotifications,
    projectUpdates,
    sessionAlerts,
    billingAlerts,
    theme,
    editorFontSize,
    profileVisibility,
    showActivity,
    autoHibernate,
    hibernateMinutes,
  ]);

  const SettingSection = ({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) => (
    <div className="card" style={{ marginBottom: '1.5rem' }}>
      <h3 style={{
        margin: '0 0 1.5rem 0',
        fontSize: '1.25rem',
        color: '#1e293b',
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        paddingBottom: '1rem',
        borderBottom: '2px solid #e2e8f0'
      }}>
        {icon}
        {title}
      </h3>
      {children}
    </div>
  );

  const ToggleSetting = ({ 
    label, 
    description, 
    checked, 
    onChange 
  }: { 
    label: string; 
    description: string; 
    checked: boolean; 
    onChange: (checked: boolean) => void;
  }) => (
    <div style={{
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: '1rem',
      padding: '1rem 0',
      borderBottom: '1px solid #f1f5f9'
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: '0.25rem' }}>
          {label}
        </div>
        <div style={{ fontSize: '0.875rem', color: '#64748b' }}>
          {description}
        </div>
      </div>
      <label style={{
        position: 'relative',
        display: 'inline-block',
        width: '48px',
        height: '24px',
        flexShrink: 0
      }}>
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          style={{ opacity: 0, width: 0, height: 0 }}
        />
        <span style={{
          position: 'absolute',
          cursor: 'pointer',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: checked ? '#667eea' : '#cbd5e1',
          transition: '0.3s',
          borderRadius: '24px'
        }}>
          <span style={{
            position: 'absolute',
            content: '""',
            height: '18px',
            width: '18px',
            left: checked ? '27px' : '3px',
            bottom: '3px',
            backgroundColor: 'white',
            transition: '0.3s',
            borderRadius: '50%'
          }} />
        </span>
      </label>
    </div>
  );

  return (
    <Layout title="Settings">
      <div style={{ maxWidth: '900px', margin: '0 auto' }}>
        {settingsQuery.isLoading && (
          <div style={{ padding: '1.5rem 0', textAlign: 'center' }}>Loading your settings…</div>
        )}

        {settingsQuery.isError && (
          <div style={{
            marginBottom: '1.5rem',
            padding: '0.75rem',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '8px',
            color: '#b91c1c',
            fontSize: '0.9rem',
          }}>
            Unable to load saved settings. You can still adjust preferences and try saving again.
          </div>
        )}
        {/* Header */}
        <div style={{
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          borderRadius: '16px',
          padding: '2rem',
          color: 'white',
          marginBottom: '2rem',
          boxShadow: '0 20px 60px rgba(102, 126, 234, 0.3)'
        }}>
          <h1 style={{
            margin: '0 0 0.5rem 0',
            fontSize: '2rem',
            fontWeight: '700',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem'
          }}>
            <SettingsIcon />
            Settings
          </h1>
          <p style={{ margin: 0, fontSize: '1rem', opacity: 0.95 }}>
            Customize your CoSim experience
          </p>
        </div>

        {/* Notifications */}
        <SettingSection title="Notifications" icon={<BellIcon />}>
          <ToggleSetting
            label="Email Notifications"
            description="Receive email notifications for important updates"
            checked={emailNotifications}
            onChange={setEmailNotifications}
          />
          <ToggleSetting
            label="Project Updates"
            description="Get notified when collaborators make changes to your projects"
            checked={projectUpdates}
            onChange={setProjectUpdates}
          />
          <ToggleSetting
            label="Session Alerts"
            description="Alerts when sessions are ready, idle, or terminated"
            checked={sessionAlerts}
            onChange={setSessionAlerts}
          />
          <ToggleSetting
            label="Billing Alerts"
            description="Notifications about usage and billing thresholds"
            checked={billingAlerts}
            onChange={setBillingAlerts}
          />
        </SettingSection>

        {/* Appearance */}
        <SettingSection title="Appearance" icon={<PaletteIcon />}>
          <div style={{ padding: '1rem 0', borderBottom: '1px solid #f1f5f9' }}>
            <label style={{
              display: 'block',
              fontWeight: 600,
              color: '#1e293b',
              marginBottom: '0.75rem'
            }}>
              Theme
            </label>
            <div style={{ display: 'flex', gap: '1rem' }}>
              {(['light', 'dark', 'auto'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setTheme(t)}
                  style={{
                    flex: 1,
                    padding: '0.75rem',
                    border: `2px solid ${theme === t ? '#667eea' : '#e2e8f0'}`,
                    borderRadius: '8px',
                    background: theme === t ? '#f5f3ff' : 'white',
                    color: '#1e293b',
                    cursor: 'pointer',
                    fontWeight: theme === t ? 600 : 400,
                    transition: 'all 0.2s ease',
                    textTransform: 'capitalize'
                  }}
                >
                  {t === 'light' && '☀️ '}{t === 'dark' && '🌙 '}{t === 'auto' && '🔄 '}
                  {t}
                </button>
              ))}
            </div>
            <p style={{ 
              fontSize: '0.875rem', 
              color: '#64748b', 
              marginTop: '0.75rem',
              marginBottom: 0 
            }}>
              {theme === 'auto' 
                ? 'Theme will automatically switch based on your system preferences' 
                : `Using ${theme} theme across the platform`}
            </p>
          </div>

          <div style={{ padding: '1rem 0' }}>
            <label style={{
              display: 'block',
              fontWeight: 600,
              color: '#1e293b',
              marginBottom: '0.75rem'
            }}>
              Editor Font Size: {editorFontSize}px
            </label>
            <input
              type="range"
              min="10"
              max="20"
              value={editorFontSize}
              onChange={(e) => setEditorFontSize(Number(e.target.value))}
              style={{
                width: '100%',
                height: '6px',
                borderRadius: '3px',
                background: '#e2e8f0',
                outline: 'none'
              }}
            />
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: '0.75rem',
              color: '#64748b',
              marginTop: '0.5rem'
            }}>
              <span>10px</span>
              <span>20px</span>
            </div>
          </div>
        </SettingSection>

        {/* Privacy */}
        <SettingSection title="Privacy & Security" icon={<ShieldIcon />}>
          <div style={{ padding: '1rem 0', borderBottom: '1px solid #f1f5f9' }}>
            <label style={{
              display: 'block',
              fontWeight: 600,
              color: '#1e293b',
              marginBottom: '0.5rem'
            }}>
              Profile Visibility
            </label>
            <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '0.75rem' }}>
              Control who can see your profile and projects
            </p>
            <div style={{ display: 'flex', gap: '1rem' }}>
              {(['public', 'private'] as const).map(v => (
                <button
                  key={v}
                  onClick={() => setProfileVisibility(v)}
                  style={{
                    flex: 1,
                    padding: '0.75rem',
                    border: `2px solid ${profileVisibility === v ? '#667eea' : '#e2e8f0'}`,
                    borderRadius: '8px',
                    background: profileVisibility === v ? '#f5f3ff' : 'white',
                    color: '#1e293b',
                    cursor: 'pointer',
                    fontWeight: profileVisibility === v ? 600 : 400,
                    transition: 'all 0.2s ease',
                    textTransform: 'capitalize'
                  }}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>

          <ToggleSetting
            label="Show Activity Status"
            description="Let others see when you're active in collaborative sessions"
            checked={showActivity}
            onChange={setShowActivity}
          />
        </SettingSection>

        {/* Resources */}
        <SettingSection title="Resource Management" icon={<DatabaseIcon />}>
          <ToggleSetting
            label="Auto-Hibernate Sessions"
            description="Automatically hibernate idle sessions to save resources"
            checked={autoHibernate}
            onChange={setAutoHibernate}
          />

          {autoHibernate && (
            <div style={{ padding: '1rem 0' }}>
              <label style={{
                display: 'block',
                fontWeight: 600,
                color: '#1e293b',
                marginBottom: '0.75rem'
              }}>
                Hibernate after {hibernateMinutes} minutes of inactivity
              </label>
              <input
                type="range"
                min="1"
                max="30"
                value={hibernateMinutes}
                onChange={(e) => setHibernateMinutes(Number(e.target.value))}
                style={{
                  width: '100%',
                  height: '6px',
                  borderRadius: '3px',
                  background: '#e2e8f0',
                  outline: 'none'
                }}
              />
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '0.75rem',
                color: '#64748b',
                marginTop: '0.5rem'
              }}>
                <span>1 min</span>
                <span>30 min</span>
              </div>
            </div>
          )}
        </SettingSection>

        {/* Save Button */}
        <div style={{
          position: 'sticky',
          bottom: '1rem',
          padding: '1.5rem',
          background: 'white',
          borderRadius: '12px',
          boxShadow: '0 -4px 24px rgba(15, 23, 42, 0.1)',
          border: '1px solid #e2e8f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          opacity: hasUnsavedChanges ? 1 : 0.6,
        }}>
          <div>
            <div style={{ fontWeight: 600, color: '#1e293b' }}>
              {hasUnsavedChanges ? 'Unsaved Changes' : 'All Changes Saved'}
            </div>
            <div style={{ fontSize: '0.875rem', color: '#64748b' }}>
              {hasUnsavedChanges
                ? 'Remember to save your preferences'
                : 'You’re using your latest saved preferences'}
            </div>
          </div>
          <button
            onClick={handleSaveSettings}
            className="primary-button"
            disabled={!hasUnsavedChanges || saveSettingsMutation.isPending}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            {saveSettingsMutation.isPending ? (
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
                Save All Changes
              </>
            )}
          </button>
        </div>

        {saveSettingsMutation.isError && (
          <div style={{
            marginTop: '1rem',
            padding: '0.75rem',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '8px',
            color: '#b91c1c',
            fontSize: '0.875rem'
          }}>
            Failed to save settings. Please try again.
          </div>
        )}

        {saveSettingsMutation.isSuccess && (
          <div style={{
            marginTop: '1rem',
            padding: '0.75rem',
            background: '#f0fdf4',
            border: '1px solid #bbf7d0',
            borderRadius: '8px',
            color: '#15803d',
            fontSize: '0.875rem'
          }}>
            ✓ Settings saved successfully!
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </Layout>
  );
};

export default SettingsPage;
