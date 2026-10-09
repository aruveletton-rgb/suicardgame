import type { AvatarId } from '../types';

export type AvatarOption = {
  id: AvatarId;
  label: string;
  image: string | null;
  accent: string;
};

export const avatarOptions: AvatarOption[] = [
  { id: 'default', label: '岁', image: null, accent: '#d8b66d' },
  { id: 'wang', label: '望', image: '/assets/avatars/wang.webp', accent: '#b7ad87' },
  { id: 'yu', label: '余', image: '/assets/avatars/yu.webp', accent: '#b43562' },
  { id: 'yi', label: '易', image: '/assets/avatars/yi.webp', accent: '#e781a2' },
  { id: 'zuole', label: '左乐', image: '/assets/avatars/zuole.webp', accent: '#315881' },
  { id: 'xi', label: '夕', image: '/assets/avatars/xi.webp', accent: '#68aaa5' },
  { id: 'shu', label: '黍', image: '/assets/avatars/shu.webp', accent: '#e6b500' },
  { id: 'chongyue', label: '重岳', image: '/assets/avatars/chongyue.webp', accent: '#b99b83' },
  { id: 'ling', label: '令', image: '/assets/avatars/ling.webp', accent: '#2da7d5' },
];

export const avatarById = Object.fromEntries(
  avatarOptions.map((avatar) => [avatar.id, avatar]),
) as Record<AvatarId, AvatarOption>;
