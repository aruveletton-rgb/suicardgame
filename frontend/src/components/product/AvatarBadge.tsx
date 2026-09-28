import type { CSSProperties } from 'react';
import { avatarById } from '../../data/avatars';
import type { AvatarId } from '../../types';

type AvatarBadgeProps = {
  avatarId: AvatarId;
  label?: string;
  size?: 'small' | 'medium' | 'large';
};

export function AvatarBadge({ avatarId, label, size = 'medium' }: AvatarBadgeProps) {
  const avatar = avatarById[avatarId] ?? avatarById.default;
  return (
    <span
      className={`product-avatar product-avatar--${size}`}
      style={{ '--avatar-accent': avatar.accent } as CSSProperties}
      role="img"
      aria-label={label ? `${label}的头像：${avatar.label}` : `头像：${avatar.label}`}
    >
      {avatar.image ? <img src={avatar.image} alt="" draggable={false} /> : <strong aria-hidden="true">岁</strong>}
    </span>
  );
}
