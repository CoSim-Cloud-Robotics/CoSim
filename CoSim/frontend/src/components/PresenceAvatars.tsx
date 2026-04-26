/**
 * PresenceAvatars
 *
 * Renders a compact avatar strip for every collaborator currently active in
 * the workspace. Subscribes to a Yjs awareness instance so it stays in sync
 * with the in-editor cursor decorations: the same data model powers both the
 * inline cursor "ribbon" and these avatars.
 *
 * Each avatar shows the collaborator's initials over their assigned color
 * and exposes their full name on hover.
 */
import type { CSSProperties } from 'react';
import { useEffect, useState } from 'react';

interface AwarenessLike {
  getStates: () => Map<number, unknown>;
  on: (event: string, handler: (...args: unknown[]) => void) => void;
  off: (event: string, handler: (...args: unknown[]) => void) => void;
  clientID: number;
}

interface PresenceUser {
  clientId: number;
  id?: string;
  name: string;
  color: string;
  isSelf: boolean;
}

interface Props {
  awareness: AwarenessLike | null;
  selfId?: string;
  maxVisible?: number;
}

const containerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '0.35rem'
};

const avatarBase: CSSProperties = {
  width: '1.7rem',
  height: '1.7rem',
  borderRadius: '50%',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: '#0b0b0c',
  fontSize: '0.72rem',
  fontWeight: 600,
  border: '2px solid #1f1f1f',
  cursor: 'default'
};

function initialsFor(name: string): string {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function PresenceAvatars({ awareness, selfId, maxVisible = 5 }: Props) {
  const [users, setUsers] = useState<PresenceUser[]>([]);

  useEffect(() => {
    if (!awareness) {
      setUsers([]);
      return;
    }

    const collect = () => {
      const next: PresenceUser[] = [];
      const seenIds = new Set<string>();
      awareness.getStates().forEach((state, clientId) => {
        const userState = (state as { user?: { id?: string; name?: string; color?: string } } | undefined)?.user;
        if (!userState) return;
        const id = userState.id;
        if (id) {
          if (seenIds.has(id)) return;
          seenIds.add(id);
        }
        next.push({
          clientId,
          id: userState.id,
          name: userState.name || 'Collaborator',
          color: userState.color || '#9ca3af',
          isSelf: id !== undefined && id === selfId
        });
      });
      next.sort((a, b) => {
        if (a.isSelf && !b.isSelf) return -1;
        if (!a.isSelf && b.isSelf) return 1;
        return a.name.localeCompare(b.name);
      });
      setUsers(next);
    };

    collect();
    const handler = () => collect();
    awareness.on('change', handler);
    return () => awareness.off('change', handler);
  }, [awareness, selfId]);

  if (users.length === 0) return null;

  const visible = users.slice(0, maxVisible);
  const overflow = users.length - visible.length;

  return (
    <div style={containerStyle} aria-label={`${users.length} collaborator${users.length === 1 ? '' : 's'} active`}>
      {visible.map((user, index) => (
        <span
          key={`${user.clientId}-${user.id ?? index}`}
          title={user.isSelf ? `${user.name} (you)` : user.name}
          style={{
            ...avatarBase,
            background: user.color,
            marginLeft: index === 0 ? 0 : '-0.35rem',
            zIndex: visible.length - index,
            outline: user.isSelf ? '2px solid #f9fafb' : 'none'
          }}
        >
          {initialsFor(user.name)}
        </span>
      ))}
      {overflow > 0 && (
        <span
          style={{
            ...avatarBase,
            background: '#3f3f46',
            color: '#f9fafb',
            marginLeft: '-0.35rem'
          }}
          title={`${overflow} more collaborator${overflow === 1 ? '' : 's'}`}
        >
          +{overflow}
        </span>
      )}
    </div>
  );
}

export default PresenceAvatars;
