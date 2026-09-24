export type SpecialRule = {
  assetKey: string;
  name: string;
  timing: string;
  summary: string;
};

export const specialRules: SpecialRule[] = [
  { assetKey: 'sui_wang', name: '望牌', timing: '别人无法打出合理牌时', summary: '查看并控制该玩家操作，自己的手牌也视为可用，持续到自己的回合开始。' },
  { assetKey: 'sui_ji', name: '绩牌', timing: '自己回合内', summary: '声明颜色，其他玩家依次弃该色任意数量，你可再弃不超过总数的同色牌。' },
  { assetKey: 'sui_yu', name: '余牌', timing: '自己回合内', summary: '支付四张不同颜色牌，其他玩家依次弃本轮未出现颜色的牌，可重新支付并从放弃者重启。' },
  { assetKey: 'sui_yi', name: '易牌', timing: '自己回合内', summary: '弃置两张数字牌，点数之和为 8，使所有其他玩家各摸 1 张。' },
  { assetKey: 'sui_zuole', name: '左乐牌', timing: '任何人使用岁牌时', summary: '选择一名玩家，本回合内该次岁牌效果对其无效。' },
  { assetKey: 'sui_xi', name: '夕牌', timing: '被动需要牌时', summary: '可当作任意一张被要求使用的牌，使用后立即弃掉。' },
  { assetKey: 'sui_nian', name: '年牌', timing: '吃碰杠机会', summary: '引入摸、吃、碰、杠；竞争优先级为杠、碰、吃。' },
  { assetKey: 'sui_sui_xiang', name: '岁相牌', timing: '被看到时', summary: '翻至有色牌，所有玩家依次弃同色牌，否则摸四张。' },
  { assetKey: 'sui_shu', name: '黍牌', timing: '自己回合内', summary: '选择一种颜色，将你手中该颜色的所有牌平均分给其他玩家；若有剩余，交给手牌最少的玩家之一。' },
  { assetKey: 'sui_chongyue', name: '重岳牌', timing: '自己回合内', summary: '所有玩家依次展示四种颜色，不足则摸；其他玩家可阶段性质疑使用者。' },
  { assetKey: 'sui_ling', name: '令牌', timing: '自己回合内', summary: '所有手牌数低于当前最大手牌数的玩家摸牌，直到与最大手牌数相同。' },
  { assetKey: 'field_cannot', name: '坎诺特牌', timing: '开局前场地', summary: '场地 NPC，放置 8 张真实卡牌商品，每回合买/刷新各最多一次。' },
  { assetKey: 'sui_fuzhou', name: '符咒牌', timing: '被摸到时', summary: '其他玩家按顺序可给摸到者一张手牌，随后弃掉符咒牌。' },
];
