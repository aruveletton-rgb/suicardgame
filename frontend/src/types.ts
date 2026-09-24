export type CardState = {
  card_id: string;
  category: 'number' | 'action' | 'wild' | 'sui' | 'field';
  kind: string;
  color: 'red' | 'yellow' | 'green' | 'blue' | null;
  value: number | null;
  asset_key: string;
};

export type PlayerState = {
  player_id: string;
  nickname: string;
  seat_index: number;
  online: boolean;
  is_host: boolean;
  ready: boolean;
  hand_count: number;
};

export type PendingAction = {
  prompt_id: string;
  kind: string;
  source_player_id: string | null;
  status: 'open' | 'resolved' | 'expired' | 'cancelled';
  resolution_policy: 'single' | 'first_wins' | 'sequential' | 'all';
  display_title: string | null;
  display_message: string | null;
  created_at: number;
  deadline_at: number;
  responder_count: number;
  responded_count: number;
  can_respond: boolean;
  legal_responses: string[];
  default_action: string | null;
  resolution_reason: string | null;
  effect: Record<string, unknown>;
};

export type ActiveGameState = {
  game_id: string;
  game_epoch: number;
  status: string;
  deck_count: number;
  discard_count: number;
  shop_count: number;
  field_count: number;
  current_player_id: string | null;
  current_color: CardState['color'];
  direction: number;
  winner_player_id: string | null;
  top_discard: CardState | null;
  shop_goods: CardState[];
  field_card: CardState | null;
  reveal_area: CardState[];
  pending_action: PendingAction | null;
  special_state: Record<string, unknown>;
  uno: {
    pending_player_id: string | null;
    catchable_by: string[];
    last_event: Record<string, unknown> | null;
  };
};

export type RoomState = {
  room_code: string;
  phase: string;
  state_version: number;
  players: PlayerState[];
  active_game: ActiveGameState | null;
};

export type PrivatePlayerState = {
  player_id: string;
  session_id: string;
  seat_index: number;
  nickname: string;
  is_host: boolean;
  ready: boolean;
  online: boolean;
  hand: CardState[];
  uno: {
    must_declare: boolean;
    can_catch_player_id: string | null;
  };
};

export type SessionState = {
  room_code: string;
  player_id: string;
  reconnect_token: string;
  session_id: string;
  seat_index: number;
  is_host: boolean;
};

export type ServerEvent =
  | { event: 'snapshot' | 'state_patch'; state: RoomState }
  | { event: 'private_snapshot'; state: RoomState; you: PrivatePlayerState }
  | { event: 'command_result'; action_id: string; result: Record<string, unknown> }
  | { event: 'error'; error: string; message?: string };
