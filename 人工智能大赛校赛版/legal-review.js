// 校赛专用演示审查模型：路径为审查问题清单，绝不是定罪规则。
export const legalPaths=[
 {id:"helping-cybercrime",label:"帮助信息网络犯罪活动罪（帮信罪）",checks:[
  ["help_activity","是否存在经核实的帮助行为"],
  ["knowledge","是否存在关于主观明知的证据"],
  ["upstream","上游信息网络犯罪事实是否已查明"],
  ["seriousness","情节严重的事实与适用规范是否经审查"]]},
 {id:"concealment",label:"掩饰、隐瞒犯罪所得罪",checks:[
  ["proceeds_nature","涉案财物是否属于犯罪所得及收益"],
  ["transfer_action","是否存在掩饰、隐瞒相关行为"],
  ["knowledge_of_proceeds","对资金性质的认识有何证据"],
  ["timing","与上游犯罪及事前通谋的时间关系"]]},
 {id:"fraud-accomplice",label:"诈骗罪共同犯罪",checks:[
  ["joint_intent","共同诈骗故意有何证明"],
  ["prior_agreement","是否有事前通谋或共同参与线索"],
  ["substantive_role","具体分工与实质参与行为"],
  ["fraud_evidence","诈骗行为与相关证据是否查明"]]}
];
export function createRiskSignals(c){
 const a=c.artifacts.at(-1);
 if(!a||a.stale)return [];
 return a.results.filter(r=>r.fired&&r.ruleId.startsWith("FIN-")).map(r=>({
 id:c.id+"-signal-"+r.ruleId,caseId:c.id,artifactId:a.id,
 factsVersionId:a.factsVersionId,ruleId:r.ruleId,ruleVersion:r.version,
 label:r.label,status:"requires_review",evidenceRefs:[],
 candidateFactRefs:[],legalConclusion:null,trace:r.trace
 }));
}
export function derivePaths(c){
 if(c.id!=="F4")return [];
 const version=c.versions.at(-1),facts=version?.facts??{};
 return legalPaths.map(p=>({
 id:p.id,label:p.label,position:"review_only",
 items:p.checks.map(([key,label])=>{
  const fact=c.candidates.find(x=>x.key===key&&x.status==="confirmed");
  const value=facts[key];
  const evidence=fact?.evidenceRefs?.filter(ref=>c.evidence.some(x=>x.id===ref))??[];
  return {key,label,status:fact&&value===true&&evidence.length?"evidence_linked":"needs_verification",
    evidenceRefs:evidence,verifiedFact:fact&&value===true?version?.id:null};
 }),
 humanReviewRequired:true,legalConclusion:null
 }));
}
export function verifyCandidate(c,id,decision){
 const fact=c.candidates.find(x=>x.id===id);
 if(!fact)throw Object.assign(new Error("候选事实不存在"),{status:404});
 if(fact.status!=="pending")throw Object.assign(new Error("候选事实已处理"),{status:409});
 if(!["confirmed","rejected"].includes(decision))throw Object.assign(new Error("无效核验决定"),{status:400});
 if(decision==="confirmed"&&(!fact.evidenceRefs?.length||fact.evidenceRefs.some(ref=>!c.evidence.some(e=>e.id===ref))))throw Object.assign(new Error("确认前必须关联本案有效证据"),{status:409});
 fact.status=decision;
 if(decision==="confirmed")c.draft[fact.key]=fact.value;
 return fact;
}
