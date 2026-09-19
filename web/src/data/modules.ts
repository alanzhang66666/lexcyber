import { isPlaceholderCaseId } from './placeholder-cases'

export type CoreIcon = 'compliance' | 'conviction' | 'sentencing' | 'review'

export type CoreModule = {
  key: string
  title: string
  desc: string
  /** 目标路径，可用 ':caseId' 占位，由 modulePath 解析 */
  to: string
  icon: CoreIcon
  /** 首页功能卡用的单字图标 */
  glyph: string
}

export const CORE_MODULES: CoreModule[] = [
  {
    key: 'compliance',
    title: '合规筛查',
    desc: '上传材料并解析要素，输出合规事实梳理与风险时间线。',
    to: '/cases/:caseId/compliance',
    icon: 'compliance',
    glyph: '筛',
  },
  {
    key: 'conviction',
    title: '定罪研判',
    desc: '事实结构化整理、主观认识分析、罪名界分与法域冲突研判、定罪结论。',
    to: '/cases/:caseId/conviction',
    icon: 'conviction',
    glyph: '判',
  },
  {
    key: 'sentencing',
    title: '量刑分析',
    desc: '量刑情节识别、金额口径、参数配置、刑期区间与文书生成。',
    to: '/cases/:caseId/analysis',
    icon: 'sentencing',
    glyph: '析',
  },
  {
    key: 'review',
    title: '复核归档',
    desc: '复核工作台与审计归档视图，研判结论可人工修改并留痕。',
    to: '/reviews',
    icon: 'review',
    glyph: '审',
  },
]

/** 把模块 to 里的 ':caseId' 替换成真实 T1 案件 id；没有真案时回到案件中心 */
export function modulePath(module: CoreModule, caseId: string | null | undefined): string {
  if (!module.to.includes(':caseId')) return module.to
  if (!caseId || isPlaceholderCaseId(caseId)) return '/cases'
  return module.to.replace(':caseId', caseId)
}

/** 模块 key → 中文名（如 compliance→合规筛查）；未知 key 原样返回。 */
export function moduleTitle(key: string | null | undefined): string {
  if (!key) return '未关联模块'
  return CORE_MODULES.find((m) => m.key === key)?.title || key
}
