import { useCallback, useState } from 'react';
import type { CardState } from '../../types';

export type CardPickRole = 'primary' | 'support' | 'payment';

export function useGameSelection() {
  const [primaryCardId, setPrimaryCardId] = useState<string | null>(null);
  const [supportCardIds, setSupportCardIds] = useState<string[]>([]);
  const [paymentCardId, setPaymentCardId] = useState<string | null>(null);
  const [chosenColor, setChosenColor] = useState<NonNullable<CardState['color']>>('red');
  const [targetPlayerId, setTargetPlayerId] = useState('');
  const [pickRole, setPickRole] = useState<CardPickRole>('primary');

  const selectCard = useCallback((cardId: string) => {
    if (pickRole === 'primary') {
      setPrimaryCardId(cardId);
      return;
    }
    if (pickRole === 'payment') {
      setPaymentCardId((current) => current === cardId ? null : cardId);
      return;
    }
    setSupportCardIds((current) =>
      current.includes(cardId) ? current.filter((item) => item !== cardId) : [...current, cardId],
    );
  }, [pickRole]);

  const clearCards = useCallback(() => {
    setPrimaryCardId(null);
    setSupportCardIds([]);
    setPaymentCardId(null);
    setPickRole('primary');
  }, []);

  return {
    primaryCardId,
    supportCardIds,
    paymentCardId,
    chosenColor,
    targetPlayerId,
    pickRole,
    setPrimaryCardId,
    setSupportCardIds,
    setPaymentCardId,
    setChosenColor,
    setTargetPlayerId,
    setPickRole,
    selectCard,
    clearCards,
  };
}
