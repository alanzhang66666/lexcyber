import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ConvictionPage from './ConvictionPage.vue'
import { useCaseModule } from '../composables/useCaseModule'

vi.mock('../composables/useCaseModule', () => ({ useCaseModule: vi.fn() }))

const mockedUseCaseModule = vi.mocked(useCaseModule)

function moduleState(content: Record<string, unknown>) {
  return {
    caseId: 'case-1', module: 'conviction', schemaVersion: 'case.module.v1', applicability: 'applicable',
    status: 'draft', version: 1, content, sourceVersion: 'case.conviction.v2', factsStale: false,
    updatedAt: '2026-10-08T00:00:00Z', confirmedAt: null,
  }
}

async function mountPage(content: Record<string, unknown>) {
  const load = vi.fn().mockResolvedValue(undefined)
  mockedUseCaseModule.mockReturnValue({
    loading: ref(false), error: ref(''), caseItem: ref({ id: 'case-1', title: '测试案件', createdAt: 't', updatedAt: 't' }),
    moduleState: ref(moduleState(content)), confirming: ref(false), confirmError: ref(''), dispatching: ref(false), dispatchError: ref(''),
    isPlaceholder: ref(false), load, dispatch: vi.fn(), confirm: vi.fn(),
  } as never)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/cases/:caseId/conviction', component: ConvictionPage },
      { path: '/cases/:caseId', component: { template: '<div />' } },
      { path: '/cases', component: { template: '<div />' } },
      { path: '/reviews', component: { template: '<div />' } },
    ],
  })
  await router.push('/cases/case-1/conviction')
  await router.isReady()
  const wrapper = mount(ConvictionPage, { global: { plugins: [router] } })
  await flushPromises()
  ;(wrapper as typeof wrapper & { __testRouter?: typeof router }).__testRouter = router
  return wrapper
}

afterEach(() => {
  mockedUseCaseModule.mockReset()
})

const base = {
  schema_version: 'case.conviction.v2', status: 'calculated', rules: [{ ruleId: 'r-1', ruleVersion: '1', fired: true, trace: [] }],
  blockers: [], divergence: [], human_review_required: true,
}

describe('ConvictionPage v2 candidate paths', () => {
  it('renders actor-bound candidate and excluded/conflicted paths beside rules and temporal panel', async () => {
    const wrapper = await mountPage({
      ...base,
      candidate_paths: [
        {
          id: 'cp-1', path_id: 'path-candidate', actor_id: 'actor-1', label: '帮信候选路径', charge_key: 'help_info',
          baseline_position: null, supporting_evidence_ids: ['ev-support'], contrary_evidence_ids: ['ev-against'], legal_source_ids: ['law-1'],
          rule_id: 'r-1', rule_version: '1', point: 'conduct', verification_status: 'conflicted', status: 'blocked', exclusion_reason: null, blockers: [{ code: 'EVIDENCE_CONFLICT' }],
        },
        {
          id: 'cp-2', path_id: 'path-excluded', actor_id: 'actor-1', label: '诈骗共犯排除路径', charge_key: 'fraud_accomplice',
          baseline_position: 'excluded', supporting_evidence_ids: [], contrary_evidence_ids: ['ev-exclude'], legal_source_ids: ['law-1'],
          rule_id: 'r-1', rule_version: '1', point: 'judgment', verification_status: 'candidate', status: 'calculated', exclusion_reason: '主观认识证据不足', blockers: [],
        },
        {
          id: 'cp-3', path_id: 'path-candidate', actor_id: 'actor-2', label: '另一行为人路径', charge_key: 'help_info',
          baseline_position: 'candidate', supporting_evidence_ids: ['ev-3'], contrary_evidence_ids: [], legal_source_ids: ['law-1'],
          rule_id: 'r-1', rule_version: '1', point: 'judgment', verification_status: 'candidate', status: 'calculated', exclusion_reason: null, blockers: [],
        },
      ],
      temporal_paths: [{ point: 'conduct', as_of_date: '2026-01-01', status: 'calculated', rules: [] }],
    })
    const text = wrapper.text()
    expect(text).toContain('规则执行结果')
    expect(text).toContain('帮信候选路径')
    expect(text).toContain('actor-1')
    expect(text).toContain('证据冲突')
    expect(text).toContain('支持证据')
    expect(text).toContain('相反证据')
    expect(text).toContain('待复核排除路径')
    expect(text).toContain('主观认识证据不足')
    expect(wrapper.findAll('.path-card')).toHaveLength(3)
    expect(text).toContain('双时点复核对照')
    wrapper.unmount()
  })

  it('shows pending indication for absent paths and diagnostics for malformed paths', async () => {
    const absent = await mountPage(base)
    expect(absent.text()).toContain('本次结果尚未返回定罪路径计划')
    absent.unmount()

    const malformed = await mountPage({ ...base, candidate_paths: [{ path_id: 'p', actor_id: 'a', label: '畸形路径' }] })
    expect(malformed.text()).toContain('路径结果待确认')
    expect(malformed.text()).toContain('candidate_paths[0]')
    malformed.unmount()
  })

  it('does not label a blocked excluded path as completed exclusion', async () => {
    const wrapper = await mountPage({
      ...base,
      candidate_paths: [{
        id: 'cp-blocked', path_id: 'path-blocked', actor_id: 'actor-2', label: '待核路径', charge_key: 'help_info',
        baseline_position: 'excluded', supporting_evidence_ids: [], contrary_evidence_ids: [], legal_source_ids: [],
        rule_id: 'r-1', rule_version: '1', point: 'as_of', verification_status: 'candidate', status: 'blocked', exclusion_reason: '待核对', blockers: [{ code: 'MISSING_FACT' }],
      }],
    })
    expect(wrapper.text()).toContain('路径结果待确认')
    expect(wrapper.text()).toContain('PATH_FORMAT_INVALID')
    expect(wrapper.text()).not.toContain('已排除路径')
    wrapper.unmount()
  })

  it('submits each entered charge verbatim and preserves the request in raw payload', async () => {
    const wrapper = await mountPage({ ...base, requested_charges: [{ requestedCharge: '自定义罪名', chargeKey: '自定义罪名' }], charge_coverage: [], missing_items: [] })
    const inputs = wrapper.findAll('input')
    const input = inputs.find((item) => item.attributes('aria-label') === '请求罪名 1')!
    const keyInput = inputs.find((item) => item.attributes('aria-label') === '会签标识 1')!
    await input.setValue('  自定义罪名  ')
    await keyInput.setValue('  自定义罪名  ')
    const addButton = wrapper.findAll('button.text-button').find((button) => button.text() === '增加请求')!
    await addButton.trigger('click')
    const secondInputs = wrapper.findAll('input')
    await secondInputs.find((item) => item.attributes('aria-label') === '请求罪名 2')!.setValue('标识-X')
    await wrapper.find('.action-box .button-quiet').trigger('click')
    const dispatch = (mockedUseCaseModule.mock.results[0]?.value as { dispatch: ReturnType<typeof vi.fn> }).dispatch
    expect(dispatch).toHaveBeenCalledWith({ requestedCharges: [
      { requestedCharge: '  自定义罪名  ', chargeKey: '  自定义罪名  ' },
      { requestedCharge: '标识-X', chargeKey: null },
    ]})
    expect((input.element as HTMLInputElement).value).toContain('  自定义罪名  ')
    await wrapper.findAll('button.text-button').find((button) => button.text() === '查看')!.trigger('click')
    expect(wrapper.text()).toContain('requested_charges')
    wrapper.unmount()
  })

  it('keeps legacy v2 payloads compatible and blocks malformed coverage shapes', async () => {
    const legacy = await mountPage(base)
    expect(legacy.find('[data-testid="charge-coverage"]').exists()).toBe(false)
    legacy.unmount()

    const malformed = await mountPage({ ...base, requested_charges: [{ requested_charge: '帮信' }] })
    expect(malformed.text()).toContain('CHARGE_COVERAGE_INVALID')
    expect(malformed.text()).toContain('覆盖结果待确认')
    expect(malformed.text()).toContain('已阻断')
    malformed.unmount()
  })

  it('resubmits restored requested charges without edits and clears them on case switch', async () => {
    const wrapper = await mountPage({ ...base, requested_charges: [{ requestedCharge: '案件A罪名' }], charge_coverage: [], missing_items: [] })
    await wrapper.find('.action-box .button-quiet').trigger('click')
    const dispatch = (mockedUseCaseModule.mock.results[0]?.value as { dispatch: ReturnType<typeof vi.fn> }).dispatch
    expect(dispatch).toHaveBeenCalledWith({ requestedCharges: [{ requestedCharge: '案件A罪名', chargeKey: null }] })
    await (wrapper as typeof wrapper & { __testRouter: { push: (path: string) => Promise<void> } }).__testRouter.push('/cases/case-2/conviction')
    await flushPromises()
    expect((wrapper.find('input[aria-label="请求罪名 1"]').element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })

  it('shows per-point coverage and rule/source provenance', async () => {
    const wrapper = await mountPage({
      ...base,
      requested_charges: [{ requestedCharge: '自定义罪名', chargeKey: 'charge-x' }],
      charge_coverage: [{ point: 'conduct', date: '2026-01-01', requested_charge: '自定义罪名', charge_key: 'charge-x', covered: true, rule_versions: [{ ruleId: 'r-1', ruleVersion: '1', contentHash: 'hash', sourceIds: ['law-1'] }] }],
      missing_items: [],
    })
    expect(wrapper.text()).toContain('时点覆盖结果')
    expect(wrapper.text()).toContain('已覆盖')
    expect(wrapper.text()).toContain('r-1@1')
    expect(wrapper.text()).toContain('law-1')
    wrapper.unmount()
  })

  it('keeps both evidence sides visible for a valid globally blocked path', async () => {
    const wrapper = await mountPage({
      ...base, status: 'blocked', blockers: [{ code: 'GLOBAL_BLOCKED', message: '待补齐事实' }],
      candidate_paths: [{
        id: 'cp-global-blocked', path_id: 'path-global-blocked', actor_id: 'actor-3', label: '待核候选路径', charge_key: 'help_info',
        baseline_position: null, supporting_evidence_ids: ['same-proof'], contrary_evidence_ids: ['same-proof'], legal_source_ids: [],
        rule_id: 'r-1', rule_version: '1', point: 'conduct', verification_status: 'candidate', status: 'blocked', exclusion_reason: null,
        blockers: [{ code: 'PATH_BLOCKED', message: '待补齐事实' }],
      }],
    })
    const text = wrapper.text()
    expect(text).toContain('待核候选路径')
    expect(text).toContain('支持证据')
    expect(text).toContain('相反证据')
    expect(text).toContain('same-proof')
    wrapper.unmount()
  })
})
