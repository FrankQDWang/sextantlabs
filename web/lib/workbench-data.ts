// Sextant 写作工作台 — mock 数据
// 示例项目：Harbor Nine · Ch.03 西档案室 · POV Mira

export const project = {
  name: "Harbor Nine",
  chapter: "Ch.03 西档案室",
  pov: "Mira",
  wordCount: 1284,
}

// 正文段落（作者已写入的 Manuscript Text）
export const manuscript = [
  "Mira 把空的地图筒推过桌面。黄铜的筒身在灯下泛着旧光，里面什么也没有。",
  "「你昨晚在西档案室附近。」她说，没有抬头。",
  "Kestrel 的拇指找到了外衣上的黄铜锁扣，停在那里——静止得足以算作一种回答。窗外，西塔的钟声敲过了两下。",
  "她把钥匙放在两人之间。钥匙是冷的，比这间屋子里任何东西都冷。",
]

// 当前场景小卡 —— 只和当前写作相关，不是数据库
export const sceneCard = {
  pov: "Mira",
  knows: [
    "地图筒是空的",
    "Kestrel 昨晚在西档案室附近",
    "钥匙摸起来是冷的",
  ],
  notKnows: [
    "钥匙的来源",
    "Kestrel 是否拿走了地图",
    "西档案室昨晚发生了什么",
  ],
  // 可能穿帮：作者若顺着写容易越界的点
  pitfalls: [
    "她还不能确认钥匙来源",
    "她还不知道 Kestrel 的动机",
  ],
  // 可用压力点：可以继续施加张力的素材
  pressurePoints: [
    "钥匙发冷",
    "Kestrel 回避来源",
    "地图失踪",
  ],
  // 开放悬念
  openThreads: [
    "钥匙来源仍未确认",
    "地图的下落",
  ],
}

export type RiskLevel = "low" | "medium" | "high"

export type CandidateSentence = {
  id: string
  text: string
}

export type Candidate = {
  id: string
  label: string
  direction: string // 这条候选走的方向，一句话概括
  sentences: CandidateSentence[]
  usedMemory: string[] // 用了哪些 Memory
  avoided: string[] // 避开了哪些未证实事实
  risk: { level: RiskLevel; note: string } | null
}

export const candidates: Candidate[] = [
  {
    id: "a",
    label: "克制",
    direction: "保持沉默的张力，不揭示动机",
    sentences: [
      { id: "a1", text: "「我不知道你在说什么。」Kestrel 抬起头，目光平静地与她对视。" },
      { id: "a2", text: "但他的手指仍然没有离开那个锁扣。" },
    ],
    usedMemory: ["Kestrel 昨晚在西档案室附近", "钥匙摸起来是冷的"],
    avoided: ["钥匙的来源", "Kestrel 是否拿走了地图"],
    risk: null,
  },
  {
    id: "b",
    label: "施压",
    direction: "让 Mira 追问，逼出一次回避",
    sentences: [
      { id: "b1", text: "沉默在他们之间延展，像某种有形的东西。" },
      { id: "b2", text: "「钥匙是从哪来的？」她问。Kestrel 没有回答，只是把锁扣扣得更紧了一些。" },
    ],
    usedMemory: ["钥匙摸起来是冷的", "Kestrel 回避来源"],
    avoided: ["钥匙的来源"],
    risk: { level: "medium", note: "不要写成 Kestrel 已经承认了什么" },
  },
  {
    id: "c",
    label: "外推",
    direction: "引入新人物 Orrin 转移焦点",
    sentences: [
      { id: "c1", text: "「档案室的事与我无关。」他站起身，椅子在石板地面上发出刺耳的声响。" },
      { id: "c2", text: "「你该去问问 Orrin。」" },
    ],
    usedMemory: ["Kestrel 昨晚在西档案室附近"],
    avoided: ["西档案室昨晚发生了什么"],
    risk: { level: "high", note: "不要写成 Kestrel 已经背叛；Orrin 尚未在前文出现" },
  },
]

// 采纳后「我准备记住这些」的回写项
export type WritebackKind = "fact" | "perception" | "thread"
export type WritebackItem = {
  id: string
  text: string
  kind: WritebackKind
  kindLabel: string
  evidence?: string
  risk?: string
  status?: string
  actions: { label: string; primary?: boolean }[]
  level: RiskLevel
}

export const writebackItems: WritebackItem[] = [
  {
    id: "w1",
    text: "Mira 注意到 Kestrel 的迟疑。",
    kind: "fact",
    kindLabel: "故事事实 · 观察",
    evidence: "刚加入的句子",
    actions: [{ label: "确认", primary: true }, { label: "改弱" }],
    level: "low",
  },
  {
    id: "w2",
    text: "Mira 开始怀疑 Kestrel 隐瞒了什么。",
    kind: "perception",
    kindLabel: "角色认知 · 怀疑",
    risk: "不能写成 Kestrel 已经背叛",
    actions: [{ label: "确认", primary: true }, { label: "改成只是觉得奇怪" }],
    level: "medium",
  },
  {
    id: "w3",
    text: "钥匙来源仍然未知。",
    kind: "thread",
    kindLabel: "开放悬念",
    status: "继续保持开放",
    actions: [{ label: "确认", primary: true }, { label: "稍后处理" }],
    level: "low",
  },
]

// Review —— 用写作语言表达，不用内部枚举
export type ReviewItem = {
  id: string
  text: string
  hint: string
}

export const reviewItems: ReviewItem[] = [
  {
    id: "r1",
    text: "这里可能让 Mira 知道了她不该知道的事",
    hint: "第 3 段提到钥匙来源，但 Mira 还无法确认",
  },
  {
    id: "r2",
    text: "这里可能把暗示写得太实",
    hint: "Kestrel 的迟疑被描述得接近承认",
  },
]
