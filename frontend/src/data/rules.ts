export type RuleCategory = 'active' | 'reaction' | 'passive' | 'field';

export type SpecialRule = {
  assetKey: string;
  name: string;
  shortName: string;
  category: RuleCategory;
  categoryLabel: string;
  timing: string;
  summary: string;
  steps: string[];
  notes: string[];
  cardArt: string;
  originalImage: string;
};

export type GeneralRule = {
  id: string;
  title: string;
  summary: string;
  details: string[];
};

export const generalRules: GeneralRule[] = [
  {
    id: 'seniority',
    title: '高辈分规避',
    summary: '响应岁牌时，可在自己的回合弃一张辈分更高的岁牌，规避该次指定效果。',
    details: [
      '规避牌只作为本次响应支付，不发动其自身主动能力。',
      '规避只作用于对应效果，不产生跨回合或永久免疫。',
      '左乐等合法响应在效果影响目标前处理，目标可以是使用者自己。',
    ],
  },
  {
    id: 'timers',
    title: '操作时限与暂停',
    summary: '普通回合 90 秒；必选 30 秒；可选响应 15 秒；质疑 10 秒。',
    details: [
      '普通回合或必选操作超时后牌局暂停，不自动代选、摸牌、弃牌或推进回合。',
      '普通回合没有可出牌时，摸牌会持续到获得可出牌；获得后保留当前回合，先出掉该牌再交给下一位。',
      '手中已有可出的普通牌或满足条件的主动岁牌时，不能通过摸牌跳过回合。',
      '可选响应到期视为放弃。房主可继续等待并重置原步骤时限，或中止本局。',
    ],
  },
];

const ORIGINAL_ROOT = '/assets/cards/sui';
const CARD_ART_ROOT = '/assets/cards/portraits';

export const specialRules: SpecialRule[] = [
  {
    assetKey: 'sui_wang', name: '望牌', shortName: '望', category: 'active', categoryLabel: '控制',
    timing: '别人无法打出合理牌时即刻使用',
    summary: '查看并控制该玩家进行游戏，你的手牌同时视为其可用手牌，持续到你的回合开始。',
    steps: ['选择无法正常跟牌的玩家，查看其被授权的手牌信息。', '由望牌使用者代替该玩家作出后续操作；使用者自己的手牌也可作为可用手牌。', '依次继续控制下一位玩家，直到望牌使用者自己的回合开始。'],
    notes: ['控制链允许合法岁牌与 +4 等父子效果嵌套；子效果结束后必须恢复原控制步骤。', '场地牌不视为任何玩家的合法手牌。'],
    cardArt: `${CARD_ART_ROOT}/sui_wang.webp`, originalImage: `${ORIGINAL_ROOT}/15aefb709c02084fbf08600c51e42d85.jpg`,
  },
  {
    assetKey: 'sui_yu', name: '余牌', shortName: '余', category: 'active', categoryLabel: '颜色支付', timing: '自己的回合内使用',
    summary: '先支付四张颜色各不相同的牌；其他玩家依次弃一张本轮尚未出现颜色的牌。',
    steps: ['弃置红、黄、绿、蓝各一张作为本轮支付。', '其他玩家按出牌方向依次弃一张本轮此前未出现过颜色的牌，或选择放弃。', '使用者可选择停止，或再次支付四色牌，并从本轮选择放弃的玩家开始新一轮。'],
    notes: ['重新开始时清空上一轮的颜色记录；每一轮都必须重新完成四色支付。'],
    cardArt: `${CARD_ART_ROOT}/sui_yu.webp`, originalImage: `${ORIGINAL_ROOT}/23db64326534b6478c57bae78d1c1590.jpg`,
  },
  {
    assetKey: 'sui_yi', name: '易牌', shortName: '易', category: 'active', categoryLabel: '数字组合', timing: '自己的回合内使用',
    summary: '同时弃两张点数之和为 8 的数字牌，使其他玩家各摸一张；本回合可重复。',
    steps: ['选择恰好两张数字牌。', '两张牌点数之和必须等于 8。', '弃置所选牌，其他每位玩家各摸一张。'],
    notes: ['多次发动时，每次都重新选择并验证两张支付牌。'],
    cardArt: `${CARD_ART_ROOT}/sui_yi.webp`, originalImage: `${ORIGINAL_ROOT}/23f1f0c5d35242bc5a52bba759946770.jpg`,
  },
  {
    assetKey: 'sui_zuole', name: '左乐牌', shortName: '左乐', category: 'reaction', categoryLabel: '即时响应', timing: '任何人使用岁牌、效果尚未影响目标时响应',
    summary: '选择一名玩家，使该次岁牌效果在本回合内对其无效；可以选择自己。',
    steps: ['在合法响应窗口内打出左乐牌。', '选择本次要保护的玩家，目标可以是自己。', '仅对当前来源岁牌的对应效果生效。'],
    notes: ['令等即时影响牌也必须先经过合法响应窗口。', '不会产生对其他岁牌或后续回合的永久免疫。'],
    cardArt: `${CARD_ART_ROOT}/sui_zuole.webp`, originalImage: `${ORIGINAL_ROOT}/2f42240353fbe94ad44e1ee11070299b.jpg`,
  },
  {
    assetKey: 'sui_xi', name: '夕牌', shortName: '夕', category: 'passive', categoryLabel: '被动替代', timing: '被动需要使用、展示或弃置特定牌时',
    summary: '可代替一张当前步骤要求的牌，完成替代后立即弃置夕牌。',
    steps: ['在当前规则步骤明确要求你提供一张牌时选择夕牌。', '声明它在本步骤中替代的颜色或要求。', '结算该次替代并立即将夕牌弃置。'],
    notes: ['夕不是可在主阶段随意发动的万能主动牌；只能在真实的被动需求中替代。'],
    cardArt: `${CARD_ART_ROOT}/sui_xi.webp`, originalImage: `${ORIGINAL_ROOT}/3e25cb360344c2f96a7120b0bdc36335.jpg`,
  },
  {
    assetKey: 'sui_shu', name: '黍牌', shortName: '黍', category: 'active', categoryLabel: '均分手牌', timing: '自己的回合内，某色手牌数不少于其他玩家数时',
    summary: '将所选颜色的全部手牌平均分给其他玩家；余牌交给当前手牌最少者之一。',
    steps: ['选择一种符合数量要求的普通颜色。', '把自己手中该颜色的全部牌尽量平均分给其他玩家。', '若有余牌，交给当前手牌最少的玩家；并列时由使用者选择其中一人。'],
    notes: ['分配过程保持牌张守恒，候选接收者只从合法并列者中选择。'],
    cardArt: `${CARD_ART_ROOT}/sui_shu.webp`, originalImage: `${ORIGINAL_ROOT}/941e81d9c480f062462aed1364e55ad1.jpg`,
  },
  {
    assetKey: 'sui_chongyue', name: '重岳牌', shortName: '重岳', category: 'active', categoryLabel: '展示与质疑', timing: '自己的回合内使用',
    summary: '玩家依次展示四张不同颜色手牌；颜色不足则摸牌并展示，阶段后可质疑使用者。',
    steps: ['按当前出牌方向，每位玩家展示红、黄、绿、蓝各一张。', '缺少颜色时持续摸牌，并展示摸到的牌，直到颜色齐全。', '其他玩家的展示阶段结束后可质疑使用者；按重岳牌的成功/失败结果结算。'],
    notes: ['展示仅公开必要牌，不公开完整手牌；质疑结算完成后继续原效果。'],
    cardArt: `${CARD_ART_ROOT}/sui_chongyue.webp`, originalImage: `${ORIGINAL_ROOT}/9bf6f1118300add4e001671f90641b5d.jpg`,
  },
  {
    assetKey: 'sui_ling', name: '令牌', shortName: '令', category: 'active', categoryLabel: '补齐手牌', timing: '自己的回合内使用',
    summary: '冻结发动时的单人最高手牌数，所有低于该数的玩家摸至相同数量，使用者也包括在内。',
    steps: ['发动时记录当前所有玩家中的最高手牌数。', '按出牌方向，让低于该数的玩家依次摸牌补齐。', '以发动时冻结的数字完成全部结算，不因中途摸牌重新抬高目标。'],
    notes: ['目标受到影响前可进行合法左乐或高辈分规避响应。'],
    cardArt: `${CARD_ART_ROOT}/sui_ling.webp`, originalImage: `${ORIGINAL_ROOT}/a096ad301444ccefec6871995adafdef.jpg`,
  },
  {
    assetKey: 'field_cannot', name: '坎诺特牌', shortName: '坎诺特', category: 'field', categoryLabel: '场地 NPC', timing: '开局前置于场上',
    summary: '在场地周围放置 8 张真实卡牌作为商品；玩家每回合最多购买一次、刷新一次。',
    steps: ['开局前把坎诺特放入场地区域，不加入任何玩家手牌。', '从牌堆布置 8 张商品牌，万能牌不会进入商店。', '玩家支付符合商品颜色或数字的牌购买；无色商品可用任意牌支付。', '玩家可在自己的回合刷新一次商店，旧商品回到弃牌堆并重新布置商品。'],
    notes: ['坎诺特是场地 NPC，不是可手持的岁牌；商店移动保持牌张守恒，Wild 与 Wild Draw Four 始终排除在商品外。'],
    cardArt: `${CARD_ART_ROOT}/field_cannot.webp`, originalImage: `${ORIGINAL_ROOT}/ddc008e08c2dc031c8a7f115a3832c43.jpg`,
  },
];

export const specialRuleByAssetKey = Object.fromEntries(
  specialRules.map((rule) => [rule.assetKey, rule]),
) as Record<string, SpecialRule>;
