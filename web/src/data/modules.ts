export type CoreIcon = 'compliance' | 'conviction' | 'sentencing' | 'review'

export type CoreModule = {
  key: string
  title: string
  desc: string
  /** 目标路径，可用 ':caseId' 占位，由 modulePath 解析 */
  to: string
  icon: CoreIcon
  /** 功能中心用的单字图标 */
  glyph: string
  /** 为 true 表示尚未接通后端数据，标记「开发中」 */
  dev?: boolean
}

export const CORE_MODULES: CoreModule[] = [
  {
    key: 'compliance',
    title: '合规筛查',
    desc: '上传跨境业务与企业合规材料，自动体检风险并生成整改建议清单。',
    to: '/compliance',
    icon: 'compliance',
    glyph: '筛',
    dev: true,
  },
  {
    key: 'conviction',
    title: '定罪研判',
    desc: '解析行为要素，输出主观罪过四层识别、法域冲突研判与定罪结论。',
    to: '/conviction',
    icon: 'conviction',
    glyph: '判',
    dev: true,
  },
  {
    key: 'sentencing',
    title: '量刑分析',
    desc: '配置三维量刑参数，输出合规情节评估、刑期区间与文书模板。',
    to: '/cases/:caseId/analysis',
    icon: 'sentencing',
    glyph: '析',
    dev: true,
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

/** 把模块 to 里的 ':caseId' 替换成真实案件 id */
export function modulePath(module: CoreModule, caseId: string): string {
  return module.to.replace(':caseId', caseId)
}
