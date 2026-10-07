package com.lexcyber.server.domain;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * v1.3 §4.6.2-4.6.3 / §4.8.1 — FactsVersion 确认、head 推进与工作副本读写。
 * 版本号只经 facts_head.next_version 在行锁内分配（INV-DB-SOURCE-001，不用 MAX+1）。
 * status 不落库，由 confirmed_at + head 指针派生（ADR-0002）。
 * 快照覆盖全部六类实体（fact/actor/event/evidence/amount/jurisdiction_connection），
 * facts_version_item 登记每条快照成员的实体 id 与条目内容哈希（不含时间戳字段）。
 */
@Service
public class FactsBaselineService {
    /** 可编辑实体种类 → 快照 payload.entities 内的 key。 */
    static final Map<String, String> ENTITY_KIND_TO_KEY = Map.of(
            "actor", "actors",
            "event", "events",
            "evidence", "evidence",
            "amount", "amounts",
            "jurisdiction_connection", "jurisdictionConnections");
    /** /v2 facts-entities 端点路径段 → 内部 kind。 */
    static final Map<String, String> PATH_TO_KIND = Map.of(
            "facts", "fact",
            "actors", "actor",
            "events", "event",
            "evidence", "evidence",
            "amounts", "amount",
            "jurisdiction-connections", "jurisdiction_connection");
    static final List<String> AMOUNT_KINDS = List.of(
            "payment_settlement_amount", "illegal_gain", "crime_amount",
            "business_revenue", "recovery", "fine");

    private final JdbcTemplate jdbc;
    private final StalePropagationService stale;
    private final IdentityService ids;
    // USE_BIG_DECIMAL：numeric(20,4) 金额快照往返不丢精度
    private final ObjectMapper mapper = new ObjectMapper().findAndRegisterModules()
            .enable(com.fasterxml.jackson.databind.DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);

    public FactsBaselineService(JdbcTemplate jdbc, StalePropagationService stale) {
        this.jdbc = jdbc;
        this.stale = stale;
        this.ids = new IdentityService(jdbc);
    }

    /** 当前 confirmed 版本 id；无则 empty。唯一权威位置 facts_head（INV-FACTS-001）。 */
    public Optional<UUID> confirmedVersionId(String caseId) {
        List<UUID> rows = jdbc.query(
                "SELECT confirmed_facts_version_id FROM app.facts_head WHERE case_id = ?::uuid",
                (rs, ignored) -> rs.getObject(1, UUID.class), caseId);
        return rows.stream().filter(Objects::nonNull).findFirst();
    }

    /** 规则执行/门闩入口：必须有 confirmed FactsVersion，否则 409。 */
    public UUID requireConfirmedVersionId(String caseId) {
        UUID versionId = confirmedVersionId(caseId).orElseThrow(() ->
                new ApiException(HttpStatus.CONFLICT, "FACTS_NOT_CONFIRMED", "事实基线未确认"));
        validateVersionReferences(caseId, versionId);
        return versionId;
    }

    /** Validate a frozen version without consulting or mutating the working copy. */
    public void validateVersionReferences(String caseId, UUID versionId) {
        List<String> payloadRows = jdbc.query(
                "SELECT payload::text FROM app.facts_version WHERE facts_version_id = ? AND case_id = ?::uuid",
                (rs, ignored) -> rs.getString(1), versionId, caseId);
        if (payloadRows.isEmpty()) {
            throw invalidReference("facts version is missing or belongs to another case");
        }
        Map<String, Object> payload = castMap(readJson(payloadRows.get(0)));
        canonicalizeAndValidateReferenceClosure(caseId, payload);
        validateCloneActorReferences(caseId, payload);
    }

    /**
     * 把当前六类可编辑实体固化为一条新的 draft FactsVersion（全量语义快照）。
     * 调用方必须已持有 case 行锁。head 行锁内分配版本号。
     */
    @Transactional
    public UUID createDraftVersion(String caseId, UUID createdBy) {
        ensureHeadRow(caseId);
        jdbc.queryForObject(
                "SELECT case_id FROM app.facts_head WHERE case_id = ?::uuid FOR UPDATE",
                String.class, caseId);
        Integer version = jdbc.queryForObject(
                "SELECT next_version FROM app.facts_head WHERE case_id = ?::uuid",
                Integer.class, caseId);
        UUID versionId = UUID.randomUUID();

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("items", readJsonArray(snapshotQuery("fact"), caseId));
        Map<String, Object> entities = new LinkedHashMap<>();
        for (Map.Entry<String, String> e : ENTITY_KIND_TO_KEY.entrySet()) {
            entities.put(e.getValue(), readJsonArray(snapshotQuery(e.getKey()), caseId));
        }
        payload.put("entities", entities);
        canonicalizeAndValidateReferenceClosure(caseId, payload);
        validateCloneActorReferences(caseId, payload);
        String payloadJson = writeJson(payload);
        String contentHash = sha256(payloadJson);

        jdbc.update("""
                INSERT INTO app.facts_version(
                    facts_version_id, case_id, version, content_hash, payload, created_by)
                VALUES (?, ?::uuid, ?, ?, ?::jsonb, ?)
                """, versionId, caseId, version, contentHash, payloadJson, createdBy);

        insertVersionItems(versionId, "fact", (List<Object>) payload.get("items"));
        for (Map.Entry<String, String> e : ENTITY_KIND_TO_KEY.entrySet()) {
            insertVersionItems(versionId, e.getKey(), (List<Object>) entities.get(e.getValue()));
        }
        jdbc.update("UPDATE app.facts_head SET next_version = next_version + 1, updated_at = now() WHERE case_id = ?::uuid",
                caseId);
        return versionId;
    }

    /**
     * §4.8.1 确认流程：head FOR UPDATE → CAS 校验 expected head → 校验版本可确认 →
     * 置 confirmed → 推进 head → 下游 stale。
     * expectedConfirmedId 为调用方读到的当前 head；不一致返 409（后到者不得静默覆盖）。
     */
    @Transactional
    public void confirm(String caseId, UUID factsVersionId, UUID expectedConfirmedId, UUID confirmedBy) {
        ensureHeadRow(caseId);
        Map<String, Object> head = jdbc.queryForMap(
                "SELECT confirmed_facts_version_id FROM app.facts_head WHERE case_id = ?::uuid FOR UPDATE",
                caseId);
        UUID oldConfirmed = (UUID) head.get("confirmed_facts_version_id");
        if (!Objects.equals(oldConfirmed, expectedConfirmedId)) {
            throw new ApiException(HttpStatus.CONFLICT, "FACTS_HEAD_CONFLICT",
                    "事实基线在读取后已变化，请重新读取 facts-head 再确认");
        }
        Long valid = jdbc.queryForObject("""
                SELECT COUNT(*) FROM app.facts_version
                WHERE facts_version_id = ? AND case_id = ?::uuid AND confirmed_at IS NULL
                """, Long.class, factsVersionId, caseId);
        if (valid == null || valid == 0L) {
            throw new ApiException(HttpStatus.CONFLICT, "FACTS_VERSION_NOT_CONFIRMABLE",
                    "事实版本不存在、不属于该案件或已确认");
        }
        String payloadJson = jdbc.queryForObject(
                "SELECT payload::text FROM app.facts_version WHERE facts_version_id = ? AND case_id = ?::uuid",
                String.class, factsVersionId, caseId);
        Map<String, Object> payload = castMap(readJson(payloadJson));
        canonicalizeAndValidateReferenceClosure(caseId, payload);
        validateCloneActorReferences(caseId, payload);
        jdbc.update("""
                UPDATE app.facts_version SET confirmed_by = ?, confirmed_at = now()
                WHERE facts_version_id = ? AND confirmed_at IS NULL
                """, confirmedBy, factsVersionId);
        jdbc.update("""
                UPDATE app.facts_head SET confirmed_facts_version_id = ?, updated_at = now()
                WHERE case_id = ?::uuid
                """, factsVersionId, caseId);
        if (oldConfirmed != null && !oldConfirmed.equals(factsVersionId)) {
            stale.propagateFactsSuperseded(caseId, oldConfirmed, "facts_changed");
        }
    }

    // ---------- 读路径（历史 / 明细 / diff / 工作副本） ----------

    /** 案件全部 FactsVersion 的元数据（不含 payload），按 version 升序。 */
    @Transactional(readOnly = true)
    public List<Map<String, Object>> listVersions(String caseId) {
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT v.facts_version_id, v.version, v.content_hash, v.created_at,
                       v.confirmed_at, h.confirmed_facts_version_id
                FROM app.facts_version v
                LEFT JOIN app.facts_head h ON h.case_id = v.case_id
                WHERE v.case_id = ?::uuid ORDER BY v.version
                """, caseId);
        UUID currentHead = rows.isEmpty() ? null : (UUID) rows.get(0).get("confirmed_facts_version_id");
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : rows) {
            Map<String, Object> v = new LinkedHashMap<>();
            UUID id = (UUID) r.get("facts_version_id");
            v.put("factsVersionId", id);
            v.put("version", r.get("version"));
            v.put("status", statusOf(id, r.get("confirmed_at"), currentHead));
            v.put("contentHash", r.get("content_hash"));
            v.put("createdAt", r.get("created_at"));
            v.put("confirmedAt", r.get("confirmed_at"));
            out.add(v);
        }
        return out;
    }

    /** 单个 FactsVersion 明细：元数据 + 不可变 payload 全文。 */
    @Transactional(readOnly = true)
    public Map<String, Object> versionDetail(String caseId, UUID versionId) {
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT v.facts_version_id, v.version, v.content_hash, v.payload::text AS payload,
                       v.created_at, v.confirmed_at, h.confirmed_facts_version_id
                FROM app.facts_version v
                LEFT JOIN app.facts_head h ON h.case_id = v.case_id
                WHERE v.facts_version_id = ? AND v.case_id = ?::uuid
                """, versionId, caseId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "FACTS_VERSION_NOT_FOUND", "事实版本不存在");
        }
        Map<String, Object> r = rows.get(0);
        Map<String, Object> v = new LinkedHashMap<>();
        UUID id = (UUID) r.get("facts_version_id");
        v.put("factsVersionId", id);
        v.put("caseId", caseId);
        v.put("version", r.get("version"));
        v.put("status", statusOf(id, r.get("confirmed_at"),
                (UUID) r.get("confirmed_facts_version_id")));
        v.put("contentHash", r.get("content_hash"));
        v.put("createdAt", r.get("created_at"));
        v.put("confirmedAt", r.get("confirmed_at"));
        v.put("payload", readJson((String) r.get("payload")));
        return v;
    }

    /** 当前工作副本（可编辑实体表）按种类分组返回；形状与快照 payload.entities 一致。 */
    @Transactional(readOnly = true)
    public Map<String, Object> editableEntities(String caseId) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("caseId", caseId);
        view.put("items", readJsonArray(snapshotQuery("fact"), caseId));
        Map<String, Object> entities = new LinkedHashMap<>();
        for (Map.Entry<String, String> e : ENTITY_KIND_TO_KEY.entrySet()) {
            entities.put(e.getValue(), readJsonArray(snapshotQuery(e.getKey()), caseId));
        }
        view.put("entities", entities);
        return view;
    }

    /** 两版本逐条对比：按每节的 id 索引，输出 added/removed/changed（含 before/after）。 */
    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public Map<String, Object> diffVersions(String caseId, UUID fromId, UUID toId) {
        Map<String, Object> from = (Map<String, Object>) versionDetail(caseId, fromId).get("payload");
        Map<String, Object> to = (Map<String, Object>) versionDetail(caseId, toId).get("payload");
        Map<String, Object> sections = new LinkedHashMap<>();
        sections.put("items", diffSection(
                (List<Object>) from.getOrDefault("items", List.of()),
                (List<Object>) to.getOrDefault("items", List.of())));
        Map<String, Object> fromEntities = (Map<String, Object>) from.getOrDefault("entities", Map.of());
        Map<String, Object> toEntities = (Map<String, Object>) to.getOrDefault("entities", Map.of());
        for (String key : ENTITY_KIND_TO_KEY.values()) {
            sections.put(key, diffSection(
                    (List<Object>) fromEntities.getOrDefault(key, List.of()),
                    (List<Object>) toEntities.getOrDefault(key, List.of())));
        }
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("caseId", caseId);
        view.put("fromFactsVersionId", fromId);
        view.put("toFactsVersionId", toId);
        view.put("sections", sections);
        return view;
    }

    /**
     * 把某历史版本内容回写到可编辑工作副本（clone/还原路径）。
     * 只影响编辑态；不改变 head，也不修改任何 FactsVersion（INV-FACTS-002）。
     * 调用方必须已持有 case 行锁。
     */
    @Transactional
    @SuppressWarnings("unchecked")
    public void cloneIntoWorkingCopy(String caseId, UUID versionId) {
        Map<String, Object> payload =
                (Map<String, Object>) versionDetail(caseId, versionId).get("payload");
        canonicalizeAndValidateReferenceClosure(caseId, payload);
        validateCloneActorReferences(caseId, payload);
        deleteWorkingCopy(caseId);
        Map<String, Object> entities = (Map<String, Object>) payload.getOrDefault("entities", Map.of());
        for (Map<String, Object> item : itemsOf(entities, "actors")) {
            jdbc.update("""
                    INSERT INTO app.case_actor(actor_id, case_id, external_id, actor_type, name, role,
                                               attributes, verification_status)
                    VALUES (?::uuid, ?::uuid, ?, ?, ?, ?, ?::jsonb, ?)
                    """, entityIdOrNew(item), caseId, str(item.get("externalId")),
                    str(item.get("type")), str(item.get("name")), str(item.get("role")),
                    writeJson(item.getOrDefault("attributes", Map.of())), str(item.get("verificationStatus")));
        }
        for (Map<String, Object> item : itemsOf(entities, "events")) {
            jdbc.update("""
                    INSERT INTO app.case_event(event_id, case_id, external_id, event_date, stage,
                                               description, actor_id, attributes, verification_status)
                    VALUES (?::uuid, ?::uuid, ?, ?::date, ?, ?, ?::uuid, ?::jsonb, ?)
                    """, entityIdOrNew(item), caseId, str(item.get("externalId")),
                    str(item.get("date")), str(item.get("stage")), str(item.get("description")),
                    existingEntityOrNull(caseId, "actor", str(item.get("actorId"))),
                    writeJson(item.getOrDefault("attributes", Map.of())),
                    str(item.get("verificationStatus")));
        }
        for (Map<String, Object> item : itemsOf(entities, "evidence")) {
            jdbc.update("""
                    INSERT INTO app.case_evidence(evidence_id, case_id, external_id, evidence_type, label,
                                                  document_id, locator, attributes, verification_status)
                    VALUES (?::uuid, ?::uuid, ?, ?, ?, ?::uuid, ?::jsonb, ?::jsonb, ?)
                    """, entityIdOrNew(item), caseId, str(item.get("externalId")),
                    str(item.get("type")), str(item.get("label")),
                    existingDocumentOrNull(str(item.get("documentId"))),
                    item.get("locator") == null ? null : writeJson(item.get("locator")),
                    writeJson(item.getOrDefault("attributes", Map.of())), str(item.get("verificationStatus")));
        }
        for (Map<String, Object> item : itemsOf(entities, "amounts")) {
            // component_of 两遍回填：快照内金额可能引用尚未插入的同案金额
            jdbc.update("""
                    INSERT INTO app.case_amount(amount_id, case_id, external_id, kind, label, value,
                                                currency, evidence_ids,
                                                verification_status, attributes)
                    VALUES (?::uuid, ?::uuid, ?, ?, ?, ?, ?, ?::jsonb, ?, ?::jsonb)
                    """, entityIdOrNew(item), caseId, str(item.get("externalId")),
                    str(item.get("kind")), str(item.get("label")), item.get("value") == null ? null
                            : new java.math.BigDecimal(String.valueOf(item.get("value"))),
                    str(item.get("currency")) == null ? "CNY" : str(item.get("currency")),
                    writeJson(item.getOrDefault("evidenceIds", List.of())),
                    str(item.get("verificationStatus")), writeJson(item.getOrDefault("attributes", Map.of())));
        }
        for (Map<String, Object> item : itemsOf(entities, "amounts")) {
            String componentOf = str(item.get("componentOf"));
            if (componentOf != null) {
                jdbc.update("""
                        UPDATE app.case_amount SET component_of = ?::uuid
                        WHERE case_id = ?::uuid AND amount_id = ?::uuid
                          AND EXISTS (SELECT 1 FROM app.case_amount p
                                      WHERE p.case_id = ?::uuid AND p.amount_id = ?::uuid)
                        """, componentOf, caseId, entityIdOrNew(item), caseId, componentOf);
            }
        }
        for (Map<String, Object> item : itemsOf(entities, "jurisdictionConnections")) {
            jdbc.update("""
                    INSERT INTO app.case_jurisdiction_connection(
                        connection_id, case_id, external_id, connection_type, value,
                        evidence_ids, verification_status)
                    VALUES (?::uuid, ?::uuid, ?, ?, ?, ?::jsonb, ?)
                    """, entityIdOrNew(item), caseId, str(item.get("externalId")),
                    str(item.get("type")), str(item.get("value")),
                    writeJson(item.getOrDefault("evidenceIds", List.of())), str(item.get("verificationStatus")));
        }
        for (Map<String, Object> item : itemsOf(payload, "items")) {
            jdbc.update("""
                    INSERT INTO app.case_fact(fact_id, case_id, external_id, fact_key, fact_value, stage,
                                              actor_id, locator, source_document_id, evidence_ids,
                                              verification_status, source_version, attributes)
                    VALUES (?::uuid, ?::uuid, ?, ?, ?, ?, ?::uuid, ?, ?::uuid, ?::jsonb, ?, ?, ?::jsonb)
                    """, entityIdOrNew(item), caseId, str(item.get("externalId")),
                    str(item.get("key")), str(item.get("value")) == null ? "" : str(item.get("value")),
                    str(item.get("stage")),
                    existingEntityOrNull(caseId, "actor", str(item.get("actorId"))), str(item.get("locator")),
                    existingDocumentOrNull(str(item.get("sourceDocumentId"))),
                    writeJson(item.getOrDefault("evidenceIds", List.of())),
                    str(item.get("verificationStatus")), str(item.get("sourceVersion")),
                    writeJson(item.getOrDefault("attributes", Map.of())));
        }
        jdbc.update("""
                INSERT INTO app.facts_head(case_id, updated_at) VALUES (?::uuid, now())
                ON CONFLICT (case_id) DO UPDATE SET updated_at = now()
                """, caseId);
    }

    // ---------- 工作副本编辑（/v2：确认后仍可编辑，只影响下一次快照） ----------

    /**
     * 按种类整组替换可编辑实体（与 /v1 facts PUT 同语义：删除+重建该案件该类的全部行）。
     * amount.kind 受封闭集约束；componentOf 必须是同案本次替换中的有效无环引用。
     * 其他遗留引用字段按 external_id / uuid 解析，不伪造不存在的实体。
     */
    @Transactional
    public void replaceEntities(String caseId, String pathKind, List<Map<String, Object>> items) {
        String kind = PATH_TO_KIND.get(pathKind);
        if (kind == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                    "kind must be one of " + PATH_TO_KIND.keySet());
        }
        List<Map<String, Object>> safe = items == null ? List.of() : items;
        switch (kind) {
            case "fact" -> replaceFacts(caseId, safe);
            case "actor" -> replaceActors(caseId, safe);
            case "event" -> replaceEvents(caseId, safe);
            case "evidence" -> replaceEvidence(caseId, safe);
            case "amount" -> replaceAmounts(caseId, safe);
            case "jurisdiction_connection" -> replaceJurisdiction(caseId, safe);
            default -> throw new IllegalStateException("unreachable");
        }
        jdbc.update("""
                INSERT INTO app.facts_head(case_id, updated_at) VALUES (?::uuid, now())
                ON CONFLICT (case_id) DO UPDATE SET updated_at = now()
                """, caseId);
    }

    private void replaceFacts(String caseId, List<Map<String, Object>> items) {
        jdbc.update("DELETE FROM app.case_fact WHERE case_id = ?::uuid", caseId);
        for (Map<String, Object> item : items) {
            String key = str(item.get("key"));
            if (key == null || key.isBlank() || str(item.get("value")) == null) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                        "each fact item needs key and value");
            }
            jdbc.update("""
                    INSERT INTO app.case_fact(case_id, external_id, fact_key, fact_value, stage,
                        actor_id, locator, source_document_id, evidence_ids,
                        verification_status, source_version, attributes)
                    VALUES (?::uuid, ?, ?, ?, ?, ?::uuid, ?, ?::uuid, ?::jsonb, ?, ?, ?::jsonb)
                    """, caseId, str(item.get("id")), key.trim(), str(item.get("value")),
                    str(item.get("stage")), resolveEntityRef(caseId, "actor", item.get("actorId")),
                    str(item.get("locator")), resolveDocumentId(item.get("sourceDocumentId")),
                    writeJson(resolveEvidenceRefs(caseId, item.get("evidenceIds"))),
                    str(item.get("verificationStatus")), str(item.get("sourceVersion")),
                    writeJson(item.getOrDefault("attributes", Map.of())));
        }
    }

    private void replaceActors(String caseId, List<Map<String, Object>> items) {
        Map<Map<String, Object>, String> incomingIds = resolveIncomingIds(caseId, "actor", items);
        Set<String> retained = new HashSet<>(incomingIds.values());
        List<String> referencedRemoved = jdbc.query("""
                SELECT a.actor_id::text
                FROM app.case_actor a
                WHERE a.case_id = ?::uuid
                  AND NOT (a.actor_id::text = ANY(?::text[]))
                  AND (EXISTS (SELECT 1 FROM app.case_event e WHERE e.case_id = a.case_id AND e.actor_id = a.actor_id)
                       OR EXISTS (SELECT 1 FROM app.case_fact f WHERE f.case_id = a.case_id AND f.actor_id = a.actor_id))
                """, (rs, ignored) -> rs.getString(1), caseId,
                retained.toArray(String[]::new));
        if (!referencedRemoved.isEmpty()) {
            throw entityReferenced("actor", referencedRemoved);
        }
        // Validate every incoming actor before changing any row. Existing rows are
        // updated in place so event/fact foreign keys remain stable.
        validateUniqueIncomingAliases(caseId, "actor", items, incomingIds);
        jdbc.update("DELETE FROM app.case_actor WHERE case_id = ?::uuid AND NOT (actor_id::text = ANY(?::text[]))",
                caseId, retained.toArray(String[]::new));
        for (Map<String, Object> item : items) {
            String actorId = incomingIds.get(item);
            jdbc.update("""
                    INSERT INTO app.case_actor(actor_id, case_id, external_id, actor_type, name, role,
                                               attributes, verification_status)
                    VALUES (?::uuid, ?::uuid, ?, ?, ?, ?, ?::jsonb, ?)
                    ON CONFLICT (actor_id) DO UPDATE SET external_id = EXCLUDED.external_id,
                        actor_type = EXCLUDED.actor_type, name = EXCLUDED.name, role = EXCLUDED.role,
                        attributes = EXCLUDED.attributes, verification_status = EXCLUDED.verification_status,
                        updated_at = now()
                    """, actorId, caseId, incomingExternalId(item, actorId), str(item.get("type")),
                    str(item.get("name")), str(item.get("role")),
                    writeJson(item.getOrDefault("attributes", Map.of())), str(item.get("verificationStatus")));
        }
    }

    private void replaceEvents(String caseId, List<Map<String, Object>> items) {
        jdbc.update("DELETE FROM app.case_event WHERE case_id = ?::uuid", caseId);
        for (Map<String, Object> item : items) {
            jdbc.update("""
                    INSERT INTO app.case_event(case_id, external_id, event_date, stage, description,
                                               actor_id, attributes, verification_status)
                    VALUES (?::uuid, ?, ?::date, ?, ?, ?::uuid, ?::jsonb, ?)
                    """, caseId, str(item.get("id")), str(item.get("date")), str(item.get("stage")),
                    str(item.get("description")), resolveEntityRef(caseId, "actor", item.get("actorId")),
                    writeJson(item.getOrDefault("attributes", Map.of())), str(item.get("verificationStatus")));
        }
    }

    private void replaceEvidence(String caseId, List<Map<String, Object>> items) {
        Map<Map<String, Object>, String> incomingIds = resolveIncomingIds(caseId, "evidence", items);
        Set<String> retained = new HashSet<>(incomingIds.values());
        List<String> referencedRemoved = referencedEvidenceIds(caseId, retained);
        if (!referencedRemoved.isEmpty()) {
            throw entityReferenced("evidence", referencedRemoved);
        }
        validateUniqueIncomingAliases(caseId, "evidence", items, incomingIds);
        jdbc.update("DELETE FROM app.case_evidence WHERE case_id = ?::uuid AND NOT (evidence_id::text = ANY(?::text[]))",
                caseId, retained.toArray(String[]::new));
        for (Map<String, Object> item : items) {
            String evidenceId = incomingIds.get(item);
            jdbc.update("""
                    INSERT INTO app.case_evidence(evidence_id, case_id, external_id, evidence_type, label,
                                                  document_id, locator, attributes, verification_status)
                    VALUES (?::uuid, ?::uuid, ?, ?, ?, ?::uuid, ?::jsonb, ?::jsonb, ?)
                    ON CONFLICT (evidence_id) DO UPDATE SET external_id = EXCLUDED.external_id,
                        evidence_type = EXCLUDED.evidence_type, label = EXCLUDED.label,
                        document_id = EXCLUDED.document_id, locator = EXCLUDED.locator,
                        attributes = EXCLUDED.attributes, verification_status = EXCLUDED.verification_status,
                        updated_at = now()
                    """, evidenceId, caseId, incomingExternalId(item, evidenceId), str(item.get("type")), str(item.get("label")),
                    resolveDocumentId(item.get("documentId")),
                    item.get("locator") == null ? null : writeJson(item.get("locator")),
                    writeJson(item.getOrDefault("attributes", Map.of())), str(item.get("verificationStatus")));
        }
    }

    private void replaceAmounts(String caseId, List<Map<String, Object>> items) {
        Map<String, Integer> amountAliases = validateAmountComponentGraph(items);
        jdbc.update("DELETE FROM app.case_amount WHERE case_id = ?::uuid", caseId);
        for (Map<String, Object> item : items) {
            String kind = str(item.get("kind"));
            if (kind == null || !AMOUNT_KINDS.contains(kind)) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                        "amount kind must be one of " + AMOUNT_KINDS);
            }
            jdbc.update("""
                    INSERT INTO app.case_amount(case_id, external_id, kind, label, value, currency,
                                                evidence_ids, verification_status, attributes)
                    VALUES (?::uuid, ?, ?, ?, ?, ?, ?::jsonb, ?, ?::jsonb)
                    """, caseId, str(item.get("id")), kind, str(item.get("label")),
                    item.get("value") == null ? null
                            : new java.math.BigDecimal(String.valueOf(item.get("value"))),
                    str(item.get("currency")) == null ? "CNY" : str(item.get("currency")),
                    writeJson(resolveEvidenceRefs(caseId, item.get("evidenceIds"))),
                    str(item.get("verificationStatus")), writeJson(item.getOrDefault("attributes", Map.of())));
        }
        // 第二遍回填 component_of（同案 external_id → uuid），避免插入顺序依赖
        for (Map<String, Object> item : items) {
            String componentOf = resolveReplacementAmountRef(caseId, item.get("componentOf"), amountAliases, items);
            if (componentOf != null) {
                jdbc.update("""
                        UPDATE app.case_amount SET component_of = ?::uuid
                        WHERE case_id = ?::uuid AND external_id = ?
                        """, componentOf, caseId, str(item.get("id")));
            }
        }
    }

    private String resolveReplacementAmountRef(String caseId, Object raw,
            Map<String, Integer> amountAliases, List<Map<String, Object>> items) {
        String value = str(raw);
        if (value == null || value.isBlank()) {
            return null;
        }
        Integer aliasIndex = amountAliases.get(amountReferenceKey(value));
        if (aliasIndex != null) {
            value = str(items.get(aliasIndex).get("id"));
        }
        List<String> exact = jdbc.query("""
                SELECT amount_id::text FROM app.case_amount
                WHERE case_id = ?::uuid AND trim(external_id) = ?
                """, (rs, ignored) -> rs.getString(1), caseId, value.trim());
        if (!exact.isEmpty()) {
            return exact.get(0);
        }
        if (IdentityService.isUuid(value.trim())) {
            List<String> uuidInsensitive = jdbc.query("""
                    SELECT amount_id::text FROM app.case_amount
                    WHERE case_id = ?::uuid AND lower(trim(external_id)) = lower(?)
                    """, (rs, ignored) -> rs.getString(1), caseId, value.trim());
            if (!uuidInsensitive.isEmpty()) {
                return uuidInsensitive.get(0);
            }
        }
        throw invalidAmountComponent("componentOf could not resolve to its replacement row");
    }

    /** Validate the complete incoming amount graph before deleting the existing working copy. */
    private Map<String, Integer> validateAmountComponentGraph(List<Map<String, Object>> items) {
        Map<String, Integer> idsByKey = new HashMap<>();
        Map<Integer, Integer> parentByIndex = new HashMap<>();
        for (int i = 0; i < items.size(); i++) {
            Map<String, Object> item = items.get(i);
            String kind = str(item.get("kind"));
            if (kind == null || !AMOUNT_KINDS.contains(kind)) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                        "amount kind must be one of " + AMOUNT_KINDS);
            }
            if (item.containsKey("id") && (str(item.get("id")) == null || str(item.get("id")).isBlank())) {
                throw invalidAmountComponent("amount id cannot be blank when provided");
            }
            String id = str(item.get("id"));
            if (id != null && !id.isBlank()) {
                String key = amountReferenceKey(id);
                if (idsByKey.putIfAbsent(key, i) != null) {
                    throw invalidAmountComponent("amount ids must be unique");
                }
            }
            String entityId = str(item.get("entityId"));
            if (entityId != null && !entityId.isBlank()) {
                if (!IdentityService.isUuid(entityId)) {
                    throw invalidAmountComponent("amount entityId must be a uuid");
                }
                String key = amountReferenceKey(entityId);
                Integer previous = idsByKey.putIfAbsent(key, i);
                if (previous != null && previous != i) {
                    throw invalidAmountComponent("amount ids must be unique");
                }
                // entityId is an incoming graph alias, not a mutable-row lookup or a
                // caller-supplied primary key. Historical snapshots remain retryable;
                // references resolve only to newly inserted rows in this case.
            }
        }
        for (int i = 0; i < items.size(); i++) {
            String parent = str(items.get(i).get("componentOf"));
            if (parent == null || parent.isBlank()) {
                continue;
            }
            String childId = str(items.get(i).get("id"));
            if (childId == null || childId.isBlank()) {
                throw invalidAmountComponent("componentOf child must have an id");
            }
            String key = amountReferenceKey(parent);
            Integer parentIndex = idsByKey.get(key);
            if (parentIndex == null) {
                throw invalidAmountComponent("componentOf must refer to an amount in this replacement");
            }
            if (parentIndex == i) {
                throw invalidAmountComponent("amount componentOf cannot refer to itself");
            }
            String parentId = str(items.get(parentIndex).get("id"));
            if (parentId == null || parentId.isBlank()) {
                throw invalidAmountComponent("componentOf parent must have an id");
            }
            parentByIndex.put(i, parentIndex);
        }
        for (int i = 0; i < items.size(); i++) {
            Set<Integer> path = new HashSet<>();
            Integer cursor = i;
            while (cursor != null) {
                if (!path.add(cursor)) {
                    throw invalidAmountComponent("amount componentOf relationships cannot contain cycles");
                }
                cursor = parentByIndex.get(cursor);
            }
        }
        return idsByKey;
    }

    private static String amountReferenceKey(String raw) {
        String value = raw.trim();
        return IdentityService.isUuid(value) ? value.toLowerCase(java.util.Locale.ROOT) : value;
    }

    private static ApiException invalidAmountComponent(String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", message);
    }

    private void replaceJurisdiction(String caseId, List<Map<String, Object>> items) {
        jdbc.update("DELETE FROM app.case_jurisdiction_connection WHERE case_id = ?::uuid", caseId);
        for (Map<String, Object> item : items) {
            jdbc.update("""
                    INSERT INTO app.case_jurisdiction_connection(
                        case_id, external_id, connection_type, value, evidence_ids, verification_status)
                    VALUES (?::uuid, ?, ?, ?, ?::jsonb, ?)
                    """, caseId, str(item.get("id")), str(item.get("type")), str(item.get("value")),
                    writeJson(resolveEvidenceRefs(caseId, item.get("evidenceIds"))),
                    str(item.get("verificationStatus")));
        }
    }

    // ---------- 内部辅助 ----------

    /** 单类实体的快照数组 SQL：每行输出 jsonb 对象，含 id/entityId/externalId 与业务字段。 */
    private String snapshotQuery(String kind) {
        return switch (kind) {
            case "fact" -> """
                    SELECT COALESCE(jsonb_agg(item ORDER BY ord), '[]'::jsonb)::text FROM (
                      SELECT row_number() OVER (ORDER BY created_at, fact_id) AS ord,
                             jsonb_build_object(
                               'id', COALESCE(external_id, fact_id::text),
                               'entityId', fact_id::text, 'externalId', external_id,
                               'key', fact_key, 'value', fact_value,
                               'stage', stage, 'actorId', actor_id::text,
                               'locator', locator,
                               'sourceDocumentId', source_document_id::text,
                               'evidenceIds', evidence_ids,
                               'verificationStatus', verification_status,
                               'sourceVersion', source_version,
                               'attributes', attributes) AS item
                      FROM app.case_fact WHERE case_id = ?::uuid) t
                    """;
            case "actor" -> """
                    SELECT COALESCE(jsonb_agg(item ORDER BY ord), '[]'::jsonb)::text FROM (
                      SELECT row_number() OVER (ORDER BY created_at, actor_id) AS ord,
                             jsonb_build_object(
                               'id', COALESCE(external_id, actor_id::text),
                               'entityId', actor_id::text, 'externalId', external_id,
                               'type', actor_type, 'name', name, 'role', role,
                               'attributes', attributes,
                               'verificationStatus', verification_status) AS item
                      FROM app.case_actor WHERE case_id = ?::uuid) t
                    """;
            case "event" -> """
                    SELECT COALESCE(jsonb_agg(item ORDER BY ord), '[]'::jsonb)::text FROM (
                      SELECT row_number() OVER (ORDER BY created_at, event_id) AS ord,
                             jsonb_build_object(
                               'id', COALESCE(external_id, event_id::text),
                               'entityId', event_id::text, 'externalId', external_id,
                               'date', event_date, 'stage', stage,
                               'description', description, 'actorId', actor_id::text,
                               'attributes', attributes,
                               'verificationStatus', verification_status) AS item
                      FROM app.case_event WHERE case_id = ?::uuid) t
                    """;
            case "evidence" -> """
                    SELECT COALESCE(jsonb_agg(item ORDER BY ord), '[]'::jsonb)::text FROM (
                      SELECT row_number() OVER (ORDER BY created_at, evidence_id) AS ord,
                             jsonb_build_object(
                               'id', COALESCE(external_id, evidence_id::text),
                               'entityId', evidence_id::text, 'externalId', external_id,
                               'type', evidence_type, 'label', label,
                               'documentId', document_id::text, 'locator', locator,
                               'attributes', attributes,
                               'verificationStatus', verification_status) AS item
                      FROM app.case_evidence WHERE case_id = ?::uuid) t
                    """;
            case "amount" -> """
                    SELECT COALESCE(jsonb_agg(item ORDER BY ord), '[]'::jsonb)::text FROM (
                      SELECT row_number() OVER (ORDER BY created_at, amount_id) AS ord,
                             jsonb_build_object(
                               'id', COALESCE(external_id, amount_id::text),
                               'entityId', amount_id::text, 'externalId', external_id,
                               'kind', kind, 'label', label, 'value', value,
                               'currency', currency, 'componentOf', component_of::text,
                               'evidenceIds', evidence_ids,
                               'verificationStatus', verification_status,
                               'attributes', attributes) AS item
                      FROM app.case_amount WHERE case_id = ?::uuid) t
                    """;
            case "jurisdiction_connection" -> """
                    SELECT COALESCE(jsonb_agg(item ORDER BY ord), '[]'::jsonb)::text FROM (
                      SELECT row_number() OVER (ORDER BY created_at, connection_id) AS ord,
                             jsonb_build_object(
                               'id', COALESCE(external_id, connection_id::text),
                               'entityId', connection_id::text, 'externalId', external_id,
                               'type', connection_type, 'value', value,
                               'evidenceIds', evidence_ids,
                               'verificationStatus', verification_status) AS item
                      FROM app.case_jurisdiction_connection WHERE case_id = ?::uuid) t
                    """;
            default -> throw new IllegalArgumentException("unknown entity kind: " + kind);
        };
    }

    /** 快照成员索引：entity_id 取条目内 entityId，hash 取条目 json 本身（语义字段，不含时间戳）。 */
    private void insertVersionItems(UUID versionId, String entityKind, List<Object> items) {
        for (Object raw : items) {
            String itemJson = writeJson(raw);
            jdbc.update("""
                    INSERT INTO app.facts_version_item(facts_version_id, entity_kind, entity_id,
                                                       entity_version_or_hash)
                    VALUES (?, ?, (?::jsonb ->> 'entityId')::uuid,
                            encode(digest(?::text, 'sha256'), 'hex'))
                    """, versionId, entityKind, itemJson, itemJson);
        }
    }

    private void deleteWorkingCopy(String caseId) {
        jdbc.update("DELETE FROM app.case_fact WHERE case_id = ?::uuid", caseId);
        jdbc.update("DELETE FROM app.case_event WHERE case_id = ?::uuid", caseId);
        jdbc.update("DELETE FROM app.case_amount WHERE case_id = ?::uuid", caseId);
        jdbc.update("DELETE FROM app.case_jurisdiction_connection WHERE case_id = ?::uuid", caseId);
        jdbc.update("DELETE FROM app.case_evidence WHERE case_id = ?::uuid", caseId);
        jdbc.update("DELETE FROM app.case_actor WHERE case_id = ?::uuid", caseId);
    }

    /** 把同类引用解析为 uuid：先同案 external_id，再裸 uuid，均失败返回 null。 */
    private String resolveEntityRef(String caseId, String kind, Object raw) {
        String value = str(raw);
        if (value == null || value.isBlank()) {
            return null;
        }
        String table = switch (kind) {
            case "actor" -> "case_actor";
            case "amount" -> "case_amount";
            case "evidence" -> "case_evidence";
            default -> throw new IllegalArgumentException("no ref table for " + kind);
        };
        String pk = switch (kind) {
            case "actor" -> "actor_id";
            case "amount" -> "amount_id";
            case "evidence" -> "evidence_id";
            default -> throw new IllegalArgumentException("no ref pk for " + kind);
        };
        List<String> rows = jdbc.query(
                "SELECT " + pk + "::text FROM app." + table +
                        " WHERE case_id = ?::uuid AND external_id = ?",
                (rs, ignored) -> rs.getString(1), caseId, value.trim());
        if (!rows.isEmpty()) {
            return rows.get(0);
        }
        return IdentityService.isUuid(value.trim()) ? value.trim() : null;
    }

    /** evidenceIds 数组：逐条解析为同案 evidence uuid；解析不了保留原值（不静默丢引用）。 */
    @SuppressWarnings("unchecked")
    private List<Object> resolveEvidenceRefs(String caseId, Object raw) {
        if (!(raw instanceof List<?> list)) {
            return List.of();
        }
        List<Object> resolved = new ArrayList<>();
        for (Object entry : list) {
            String value = str(entry);
            if (value == null) {
                continue;
            }
            String uuid = resolveEntityRef(caseId, "evidence", value);
            resolved.add(uuid == null ? value : uuid);
        }
        return resolved;
    }

    private String resolveDocumentId(Object raw) {
        String value = str(raw);
        if (value == null || value.isBlank()) {
            return null;
        }
        String trimmed = value.trim();
        if (IdentityService.isUuid(trimmed)) {
            return trimmed;
        }
        List<String> rows = jdbc.query(
                "SELECT uuid_id::text FROM app.legacy_id_map WHERE legacy_id = ? AND entity_kind = 'document'",
                (rs, ignored) -> rs.getString(1), trimmed);
        return rows.isEmpty() ? null : rows.get(0);
    }

    /** clone 路径专用：实体 uuid 仍存在才回填，否则置 NULL（快照可引用此后被删的行）。 */
    private String existingEntityOrNull(String caseId, String kind, String entityId) {
        if (entityId == null || entityId.isBlank() || !IdentityService.isUuid(entityId)) {
            return null;
        }
        String table = switch (kind) {
            case "actor" -> "case_actor";
            case "evidence" -> "case_evidence";
            case "amount" -> "case_amount";
            default -> throw new IllegalArgumentException("no ref table for " + kind);
        };
        String pk = switch (kind) {
            case "actor" -> "actor_id";
            case "evidence" -> "evidence_id";
            case "amount" -> "amount_id";
            default -> throw new IllegalArgumentException("no ref pk for " + kind);
        };
        List<String> rows = jdbc.query(
                "SELECT " + pk + "::text FROM app." + table +
                        " WHERE case_id = ?::uuid AND " + pk + " = ?::uuid",
                (rs, ignored) -> rs.getString(1), caseId, entityId);
        return rows.isEmpty() ? null : entityId;
    }

    /** clone 路径专用：快照中的 documentId 仍指向现存文档才回填，否则置 NULL（不伪造引用）。 */
    private String existingDocumentOrNull(String documentId) {
        if (documentId == null || documentId.isBlank()) {
            return null;
        }
        List<String> rows = jdbc.query(
                "SELECT id::text FROM app.documents WHERE id = ?::uuid",
                (rs, ignored) -> rs.getString(1), documentId);
        return rows.isEmpty() ? null : documentId;
    }

    private void ensureHeadRow(String caseId) {
        jdbc.update("INSERT INTO app.facts_head(case_id) VALUES (?::uuid) ON CONFLICT (case_id) DO NOTHING",
                caseId);
    }

    /**
     * Resolve the stable primary key for each incoming actor/evidence row.  A
     * snapshot carries both entityId and the human-facing id/externalId; all
     * aliases must identify the same row. An explicit entityId is a canonical
     * identity; id/externalId may also be a new UUID-shaped external alias.
     */
    private Map<Map<String, Object>, String> resolveIncomingIds(
            String caseId, String kind, List<Map<String, Object>> items) {
        Map<Map<String, Object>, String> result = new IdentityHashMap<>();
        Set<String> seen = new HashSet<>();
        for (Map<String, Object> item : items) {
            List<String> aliases = new ArrayList<>();
            String entityId = str(item.get("entityId"));
            String id = str(item.get("id"));
            String externalId = str(item.get("externalId"));
            String canonical = null;
            if (entityId != null && !entityId.isBlank()) {
                if (!IdentityService.isUuid(entityId)) {
                    throw invalidInput("entityId must be a UUID");
                }
                canonical = findCanonicalEntityId(caseId, kind, entityId.trim());
                if (canonical == null) {
                    throw invalidInput("unknown or cross-case " + kind + " entityId: " + entityId);
                }
            }
            if (externalId != null && !externalId.isBlank()) {
                aliases.add(externalId.trim());
            }
            if (id != null && !id.isBlank()) {
                aliases.add(id.trim());
            }
            for (String alias : aliases) {
                String resolved = findIncomingAlias(caseId, kind, alias);
                if (resolved != null && canonical != null && !canonical.equalsIgnoreCase(resolved)) {
                    throw invalidInput("ambiguous " + kind + " aliases");
                }
                if (resolved != null) {
                    canonical = resolved;
                }
            }
            if (externalId != null && !externalId.isBlank()
                    && id != null && !id.isBlank()
                    && !externalId.trim().equals(id.trim())
                    && findIncomingAlias(caseId, kind, externalId.trim()) == null
                    && findIncomingAlias(caseId, kind, id.trim()) == null) {
                throw invalidInput("id and externalId do not identify the same " + kind);
            }
            if (canonical == null) {
                canonical = UUID.randomUUID().toString();
            }
            if (!seen.add(canonical.toLowerCase(java.util.Locale.ROOT))) {
                throw invalidInput("duplicate " + kind + " identity");
            }
            result.put(item, canonical);
        }
        return result;
    }

    private void validateUniqueIncomingAliases(String caseId, String kind,
            List<Map<String, Object>> items, Map<Map<String, Object>, String> resolved) {
        Set<String> external = new HashSet<>();
        for (Map<String, Object> item : items) {
            String value = incomingExternalId(item, resolved.get(item));
            if (value != null && !external.add(value)) {
                throw invalidInput("duplicate " + kind + " externalId");
            }
            // A caller may provide an externalId that belongs to another row;
            // resolveIncomingIds already detects the differing canonical ids.
            if (resolved.get(item) == null) {
                throw invalidInput("missing " + kind + " identity");
            }
        }
    }

    private String incomingExternalId(Map<String, Object> item, String canonicalId) {
        String external = str(item.get("externalId"));
        if (external != null && !external.isBlank()) {
            return external.trim();
        }
        String id = str(item.get("id"));
        if (id == null || id.isBlank()) {
            return null;
        }
        String entityId = str(item.get("entityId"));
        if (entityId != null && IdentityService.isUuid(entityId)
                && entityId.trim().equalsIgnoreCase(canonicalId)
                && id.trim().equalsIgnoreCase(canonicalId)) {
            return null;
        }
        return id.trim();
    }

    private String findEntityId(String caseId, String kind, String alias) {
        String table = entityTable(kind);
        String pk = entityPrimaryKey(kind);
        List<String> rows;
        if (IdentityService.isUuid(alias)) {
            rows = jdbc.query("SELECT " + pk + "::text FROM app." + table
                            + " WHERE case_id = ?::uuid AND " + pk + " = ?::uuid",
                    (rs, ignored) -> rs.getString(1), caseId, alias.trim());
        } else {
            rows = jdbc.query("SELECT " + pk + "::text FROM app." + table
                            + " WHERE case_id = ?::uuid AND external_id = ?",
                    (rs, ignored) -> rs.getString(1), caseId, alias.trim());
        }
        if (rows.size() > 1) {
            throw invalidInput("ambiguous " + kind + " identity: " + alias);
        }
        return rows.isEmpty() ? null : rows.get(0);
    }

    private String findCanonicalEntityId(String caseId, String kind, String entityId) {
        String table = entityTable(kind);
        String pk = entityPrimaryKey(kind);
        List<String> rows = jdbc.query("SELECT " + pk + "::text FROM app." + table
                        + " WHERE case_id = ?::uuid AND " + pk + " = ?::uuid",
                (rs, ignored) -> rs.getString(1), caseId, entityId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    /** id/externalId may themselves be UUID-shaped external identifiers. */
    private String findIncomingAlias(String caseId, String kind, String alias) {
        String table = entityTable(kind);
        String pk = entityPrimaryKey(kind);
        Set<String> rows = new HashSet<>();
        rows.addAll(jdbc.query("SELECT " + pk + "::text FROM app." + table
                        + " WHERE case_id = ?::uuid AND external_id = ?",
                (rs, ignored) -> rs.getString(1), caseId, alias.trim()));
        if (IdentityService.isUuid(alias)) {
            rows.addAll(jdbc.query("SELECT " + pk + "::text FROM app." + table
                            + " WHERE case_id = ?::uuid AND " + pk + " = ?::uuid",
                    (rs, ignored) -> rs.getString(1), caseId, alias.trim()));
        }
        if (rows.size() > 1) {
            throw invalidReference("ambiguous " + kind + " identity: " + alias);
        }
        return rows.isEmpty() ? null : rows.iterator().next();
    }

    private String entityTable(String kind) {
        return switch (kind) {
            case "actor" -> "case_actor";
            case "evidence" -> "case_evidence";
            default -> throw new IllegalArgumentException("unsupported stable entity " + kind);
        };
    }

    private String entityPrimaryKey(String kind) {
        return switch (kind) {
            case "actor" -> "actor_id";
            case "evidence" -> "evidence_id";
            default -> throw new IllegalArgumentException("unsupported stable entity " + kind);
        };
    }

    private List<String> referencedEvidenceIds(String caseId, Set<String> retained) {
        List<String> rows = jdbc.query("""
                SELECT DISTINCT e.evidence_id::text
                FROM app.case_evidence e
                WHERE e.case_id = ?::uuid
                  AND NOT (e.evidence_id::text = ANY(?::text[]))
                  AND (
                    EXISTS (SELECT 1 FROM app.case_fact f WHERE f.case_id = e.case_id
                           AND (f.evidence_ids @> jsonb_build_array(e.evidence_id::text)
                                OR (e.external_id IS NOT NULL AND f.evidence_ids @> jsonb_build_array(e.external_id)))
                    OR EXISTS (SELECT 1 FROM app.case_amount a WHERE a.case_id = e.case_id
                           AND (a.evidence_ids @> jsonb_build_array(e.evidence_id::text)
                                OR (e.external_id IS NOT NULL AND a.evidence_ids @> jsonb_build_array(e.external_id)))
                    OR EXISTS (SELECT 1 FROM app.case_jurisdiction_connection j WHERE j.case_id = e.case_id
                           AND (j.evidence_ids @> jsonb_build_array(e.evidence_id::text)
                                OR (e.external_id IS NOT NULL AND j.evidence_ids @> jsonb_build_array(e.external_id)))
                  )
                """, (rs, ignored) -> rs.getString(1), caseId,
                retained.toArray(String[]::new));
        return rows;
    }

    private ApiException entityReferenced(String kind, List<String> ids) {
        return new ApiException(HttpStatus.CONFLICT, "ENTITY_REFERENCED",
                kind + " rows are still referenced by the working copy",
                Map.of("kind", kind, "entityIds", ids));
    }

    private ApiException invalidReference(String message) {
        return new ApiException(HttpStatus.CONFLICT, "FACTS_REFERENCE_INVALID", message);
    }

    private ApiException invalidInput(String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", message);
    }

    /** Validate and normalize JSON evidence references before a payload is persisted. */
    @SuppressWarnings("unchecked")
    private void canonicalizeAndValidateReferenceClosure(String caseId, Map<String, Object> payload) {
        Object rawEntities = payload.get("entities");
        if (!(rawEntities instanceof Map<?, ?>)) {
            ensureNoUnresolvableLegacyReferences(itemsOf(payload, "items"));
            return;
        }
        Map<String, Object> entities = castMap(rawEntities);
        Map<String, String> evidenceAliases = snapshotAliasMap(caseId,
                snapshotItems(entities, "evidence", "evidence"), "evidence");
        List<Map<String, Object>> facts = itemsOf(payload, "items");
        for (Map<String, Object> item : facts) {
            item.put("evidenceIds", canonicalEvidenceList(item.get("evidenceIds"), evidenceAliases));
        }
        for (String key : List.of("amounts", "jurisdictionConnections")) {
            for (Map<String, Object> item : itemsOf(entities, key)) {
                item.put("evidenceIds", canonicalEvidenceList(item.get("evidenceIds"), evidenceAliases));
            }
        }
    }

    private void ensureNoUnresolvableLegacyReferences(List<Map<String, Object>> facts) {
        for (Map<String, Object> item : facts) {
            Object raw = item.get("evidenceIds");
            if (raw != null && (!(raw instanceof List<?> list) || !list.isEmpty())) {
                throw invalidReference("legacy facts payload has no evidence identity table");
            }
        }
    }

    private List<Object> canonicalEvidenceList(Object raw, Map<String, String> evidenceAliases) {
        if (raw == null) {
            return List.of();
        }
        if (!(raw instanceof List<?> list)) {
            throw invalidReference("evidenceIds must be an array");
        }
        List<Object> canonical = new ArrayList<>();
        for (Object entry : list) {
            if (!(entry instanceof String)) {
                throw invalidReference("evidenceIds entries must be strings");
            }
            String value = str(entry);
            if (value == null || value.isBlank()) {
                throw invalidReference("evidenceIds contains a blank reference");
            }
            String resolved = evidenceAliases.get(aliasKey(value));
            if (resolved == null) {
                throw invalidReference("unknown evidence reference in frozen payload: " + value);
            }
            canonical.add(resolved);
        }
        return canonical;
    }

    private void validateCloneActorReferences(String caseId, Map<String, Object> payload) {
        Object rawEntities = payload.get("entities");
        if (!(rawEntities instanceof Map<?, ?>)) {
            for (Map<String, Object> item : itemsOf(payload, "items")) {
                if (str(item.get("actorId")) != null && !str(item.get("actorId")).isBlank()) {
                    throw invalidReference("legacy facts payload has no actor identity table");
                }
            }
            return;
        }
        Map<String, Object> entities = castMap(rawEntities);
        Map<String, String> actorAliases = snapshotAliasMap(caseId,
                snapshotItems(entities, "actors", "actor"), "actor");
        for (Map<String, Object> item : itemsOf(entities, "events")) {
            item.put("actorId", canonicalActorReference(item.get("actorId"), actorAliases));
        }
        for (Map<String, Object> item : itemsOf(payload, "items")) {
            item.put("actorId", canonicalActorReference(item.get("actorId"), actorAliases));
        }
    }

    private String canonicalActorReference(Object raw, Map<String, String> actorAliases) {
        if (raw != null && !(raw instanceof String)) {
            throw invalidReference("actorId must be a string");
        }
        String value = str(raw);
        if (value == null || value.isBlank()) {
            return null;
        }
        String canonical = actorAliases.get(aliasKey(value));
        if (canonical == null) {
            throw invalidReference("unknown actor reference in frozen payload: " + value);
        }
        return canonical;
    }

    /** Build aliases exclusively from the immutable payload, never the mutable working copy. */
    private Map<String, String> snapshotAliasMap(String caseId, List<Map<String, Object>> items, String kind) {
        Map<String, String> aliases = new HashMap<>();
        Set<String> entityIds = new HashSet<>();
        for (Map<String, Object> item : items) {
            String entityId = str(item.get("entityId"));
            if (entityId == null || !IdentityService.isUuid(entityId)) {
                throw invalidReference(kind + " snapshot row has no canonical entityId");
            }
            validateSnapshotEntityOwnership(caseId, kind, entityId);
            String canonical = entityId.toLowerCase(java.util.Locale.ROOT);
            if (!entityIds.add(canonical)) {
                throw invalidReference("duplicate " + kind + " snapshot entityId");
            }
            String rawId = str(item.get("id"));
            String rawExternalId = str(item.get("externalId"));
            for (String raw : new String[] {rawId, rawExternalId}) {
                if (raw == null || raw.isBlank()) {
                    continue;
                }
                String key = aliasKey(raw);
                String previous = aliases.putIfAbsent(key, canonical);
                if (previous != null && !previous.equals(canonical)) {
                    throw invalidReference("ambiguous " + kind + " snapshot alias: " + raw);
                }
            }
            String previous = aliases.putIfAbsent(aliasKey(entityId), canonical);
            if (previous != null && !previous.equals(canonical)) {
                throw invalidReference("duplicate " + kind + " snapshot entityId");
            }
        }
        return aliases;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> snapshotItems(Map<String, Object> entities, String key, String kind) {
        Object raw = entities.get(key);
        if (raw == null) {
            return List.of();
        }
        if (!(raw instanceof List<?> list)) {
            throw invalidReference("snapshot " + kind + " section must be an array");
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : list) {
            if (!(item instanceof Map<?, ?> map)) {
                throw invalidReference("snapshot " + kind + " rows must be objects");
            }
            result.add((Map<String, Object>) map);
        }
        return result;
    }

    private void validateSnapshotEntityOwnership(String caseId, String kind, String entityId) {
        String table = entityTable(kind);
        String pk = entityPrimaryKey(kind);
        List<String> owners = jdbc.query("SELECT case_id::text FROM app." + table
                        + " WHERE " + pk + " = ?::uuid",
                (rs, ignored) -> rs.getString(1), entityId);
        if (!owners.isEmpty() && !caseId.equalsIgnoreCase(owners.get(0))) {
            throw invalidReference("cross-case " + kind + " entityId in frozen payload: " + entityId);
        }
    }

    private static String aliasKey(String raw) {
        String value = raw.trim();
        return IdentityService.isUuid(value)
                ? value.toLowerCase(java.util.Locale.ROOT)
                : "external:" + value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> castMap(Object value) {
        if (!(value instanceof Map<?, ?> map)) {
            throw invalidReference("facts payload must be an object");
        }
        return (Map<String, Object>) map;
    }

    private static String statusOf(UUID versionId, Object confirmedAt, UUID currentHead) {
        if (confirmedAt == null) {
            return "draft";
        }
        return versionId.equals(currentHead) ? "confirmed" : "superseded";
    }

    private Map<String, Object> diffSection(List<Object> from, List<Object> to) {
        Map<String, Map<String, Object>> fromById = indexById(from);
        Map<String, Map<String, Object>> toById = indexById(to);
        List<Object> added = new ArrayList<>();
        List<Object> removed = new ArrayList<>();
        List<Object> changed = new ArrayList<>();
        for (Map.Entry<String, Map<String, Object>> e : toById.entrySet()) {
            Map<String, Object> before = fromById.get(e.getKey());
            if (before == null) {
                added.add(e.getValue());
            } else if (!before.equals(e.getValue())) {
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("id", e.getKey());
                entry.put("before", before);
                entry.put("after", e.getValue());
                changed.add(entry);
            }
        }
        for (Map.Entry<String, Map<String, Object>> e : fromById.entrySet()) {
            if (!toById.containsKey(e.getKey())) {
                removed.add(e.getValue());
            }
        }
        Map<String, Object> section = new LinkedHashMap<>();
        section.put("added", added);
        section.put("removed", removed);
        section.put("changed", changed);
        return section;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Map<String, Object>> indexById(List<Object> items) {
        Map<String, Map<String, Object>> index = new LinkedHashMap<>();
        for (Object raw : items) {
            if (raw instanceof Map<?, ?> map) {
                Object id = ((Map<String, Object>) map).get("id");
                index.put(id == null ? UUID.randomUUID().toString() : String.valueOf(id),
                        (Map<String, Object>) map);
            }
        }
        return index;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> itemsOf(Map<String, Object> parent, String key) {
        Object raw = parent.get(key);
        if (!(raw instanceof List<?> list)) {
            return List.of();
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Object entry : list) {
            if (entry instanceof Map<?, ?> map) {
                out.add((Map<String, Object>) map);
            }
        }
        return out;
    }

    private List<Object> readJsonArray(String sql, String caseId) {
        return readJsonList(jdbc.queryForObject(sql, String.class, caseId));
    }

    @SuppressWarnings("unchecked")
    private List<Object> readJsonList(String json) {
        Object parsed = readJson(json);
        return parsed instanceof List ? (List<Object>) parsed : List.of();
    }

    private Object readJson(String json) {
        try {
            return mapper.readValue(json == null ? "null" : json, Object.class);
        } catch (Exception ex) {
            throw new IllegalStateException("invalid jsonb payload", ex);
        }
    }

    private String writeJson(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (Exception ex) {
            throw new IllegalStateException("json serialization failed", ex);
        }
    }

    /** 条目内实体 uuid；老快照无 entityId 时生成新 uuid（还原路径只重建工作副本，可换 id）。 */
    private static String entityIdOrNew(Map<String, Object> item) {
        Object id = item.get("entityId");
        return id == null ? UUID.randomUUID().toString() : String.valueOf(id);
    }

    private static String str(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    static String sha256(String text) {
        try {
            return java.util.HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(
                            (text == null ? "" : text).getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 is unavailable", ex);
        }
    }
}
