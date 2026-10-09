const ERROR_TEXT: Record<string, string> = {
  SPECIAL_TIMING_INVALID: '该特殊牌当前不能使用',
  SPECIAL_TARGET_INVALID: '所选目标不符合使用条件',
  SPECIAL_TARGET_REQUIRED: '请选择目标',
  NOT_YOUR_TURN: '还没有轮到你',
  DRAW_NOT_ALLOWED: '手中有可出的牌，不能摸牌跳过回合',
  EMPTY_DECK: '牌库已空',
  SHOP_BUY_LIMIT: '本回合已购买过商店物品',
  SHOP_GOOD_NOT_FOUND: '未找到所选商店物品',
  SHOP_PAYMENT_INVALID: '支付牌与商店物品不匹配',
  SHOP_REFRESH_LIMIT: '本回合已刷新过商店',
  ILLEGAL_PLAY: '这张牌当前不能打出',
  CARD_NOT_IN_HAND: '所选牌不在你的手牌中',
  PROMPT_PENDING: '请先处理当前待响应操作',
  PROMPT_EXPIRED: '该响应窗口已过期',
  ILLEGAL_PROMPT_RESPONSE: '该响应不在允许范围内',
  COLOR_REQUIRED: '请选择有效颜色',
  RECONNECT_FAILED: '重连失败，请重新加入房间',
  COMMAND_TYPE_REQUIRED: '缺少命令类型',
  BAD_PAYLOAD: '命令参数格式无效',
};

export function userErrorText(code: string, message?: string): string {
  if (message && /[\u3400-\u9fff]/.test(message)) return message;
  return ERROR_TEXT[code] ?? '操作未能完成，请检查当前牌局状态后重试';
}
