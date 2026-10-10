// 仅供校赛展示的合成数据；所有规则为演示策略而非法定或监管阈值。
export const ruleDefs = [
 {id:"FIN-KYB-001",label:"实际控制人尚未核验",source:"演示内部审查规则",field:"beneficial_owner_verified",op:"eq",value:false,action:"建议增强人工核验"},
 {id:"FIN-KYB-002",label:"业务用途尚未核验",source:"演示内部审查规则",field:"business_purpose_verified",op:"eq",value:false,action:"建议补充说明材料"},
 {id:"FIN-KYB-003",label:"资金来源尚未核验",source:"演示内部审查规则",field:"source_of_funds_verified",op:"eq",value:false,action:"建议增强人工核验"},
 {id:"FIN-KYB-004",label:"支持材料不完整",source:"演示内部审查规则",field:"supporting_documents_complete",op:"eq",value:false,action:"建议补充资料"},
 {id:"FIN-TXN-001",label:"短期交易频繁",source:"合成演示阈值（非监管标准）",field:"transaction_frequency_24h",op:"gte",value:20,action:"建议核对交易模式"},
 {id:"FIN-TXN-002",label:"新账户高交易聚合",source:"合成演示阈值（非监管标准）",field:"account_age_days",op:"combo",value:30,other:"transaction_total_30d",otherValue:100000,action:"建议增强人工复核"},
 {id:"FIN-TXN-003",label:"跨境与地区标记并存",source:"演示内部审查规则",field:"cross_border_transaction",op:"both",value:true,other:"high_risk_region",otherValue:true,action:"建议人工复核"},
 {id:"FIN-TXN-004",label:"多个风险特征组合",source:"演示内部审查规则",field:"transaction_frequency_24h",op:"combo",value:20,other:"transaction_total_30d",otherValue:100000,action:"建议提高复核优先级"}
];
export function initialState(){
 const make=(id,title,facts)=>({id,title,documents:[{name:"合成演示业务材料",locator:"DEMO:"+id+":1",note:"仅为演示摘要，不对应真实客户或原始卷宗"}],draft:{...facts},versions:[],artifacts:[],reviews:[],events:[]});
 return {schema:1,cases:[
  make("F1","企业客户业务准入审查",{beneficial_owner_verified:true,business_purpose_verified:true,source_of_funds_verified:false,supporting_documents_complete:false}),
  make("F2","异常交易风险辅助研判",{account_age_days:12,transaction_frequency_24h:32,transaction_total_30d:180000,cross_border_transaction:true,high_risk_region:true,source_of_funds_verified:false})
 ]};
}
export function evaluate(facts){
 return ruleDefs.map(rule=>{
  const left=facts[rule.field], right=rule.other?facts[rule.other]:undefined;
  const scenario=Object.hasOwn(facts,"beneficial_owner_verified")?"KYB":"TXN";
  if(rule.id.startsWith("FIN-KYB")&&scenario!=="KYB" || rule.id.startsWith("FIN-TXN")&&scenario!=="TXN")return {ruleId:rule.id,version:"demo-1.0",label:rule.label,source:rule.source,status:"not_applicable",fired:false,action:null,trace:{reason:"此规则不适用于当前演示场景"},blocker:null};
  const valid=typeof left=== (rule.op==="gte"||rule.op==="combo"?"number":"boolean") && (!rule.other || typeof right === (rule.other==="transaction_total_30d"?"number":"boolean"));
  const fired=valid && (rule.op==="eq"?left===rule.value:rule.op==="gte"?left>=rule.value:rule.op==="both"?left===rule.value&&right===rule.otherValue:rule.op==="combo"?left<(rule.id==="FIN-TXN-002"?rule.value:-Infinity)&&right>=rule.otherValue: false);
  const actualFired=rule.id==="FIN-TXN-004"?valid&&left>=rule.value&&right>=rule.otherValue:fired;
  return {ruleId:rule.id,version:"demo-1.0",label:rule.label,source:rule.source,status:valid?"calculated":"blocked",fired:actualFired,action:actualFired?rule.action:null,trace:{field:rule.field,actual:left??null,operator:rule.op,expected:rule.value,otherField:rule.other??null,otherActual:right??null,otherExpected:rule.otherValue??null},blocker:valid?null:"缺少字段或字段类型无效"};
 });
}
export function apply(state,action){
 const now=new Date().toISOString();
 if(action.type==="reset")return initialState();
 const c=state.cases.find(x=>x.id===action.caseId);
 if(!c)throw Object.assign(new Error("事项不存在"),{status:404});
 if(action.type==="edit"){
  if(!Object.hasOwn(c.draft,action.field))throw Object.assign(new Error("不支持该字段"),{status:400});
  const old=c.draft[action.field],v=action.value;
  if(typeof old!==typeof v || (typeof v==="number"&&(!Number.isFinite(v)||v<0)))throw Object.assign(new Error("字段类型或数值无效"),{status:400});
  c.draft[action.field]=v;
 } else if(action.type==="confirm"){
  const version=c.versions.length+1;
  c.versions.push({id:c.id+"-facts-v"+version,number:version,facts:{...c.draft},confirmedAt:now});
  c.artifacts.forEach(a=>{a.stale=true});
  c.events.push({at:now,type:"facts.confirmed",version});
 } else if(action.type==="run"){
  const v=c.versions.at(-1);if(!v)throw Object.assign(new Error("请先确认事实"),{status:409});
  const results=evaluate(v.facts);
  const a={id:c.id+"-artifact-v"+(c.artifacts.length+1),factsVersionId:v.id,createdAt:now,results,stale:false,humanReviewRequired:true};
  c.artifacts.push(a);c.events.push({at:now,type:"artifact.published",artifactId:a.id});
 } else if(action.type==="review"){
  const a=c.artifacts.at(-1);
  if(!a||a.stale)throw Object.assign(new Error("无可复核的当前分析结果"),{status:409});
  if(!["approved","rejected"].includes(action.decision))throw Object.assign(new Error("复核动作不合法"),{status:400});
  if(a.results.some(x=>x.status==="blocked")&&action.decision==="approved")throw Object.assign(new Error("存在阻断规则，不能批准"),{status:409});
  if(typeof action.comment!=="string"||action.comment.length>1000)throw Object.assign(new Error("复核意见不合法"),{status:400});
  c.reviews.push({artifactId:a.id,decision:action.decision,comment:action.comment,at:now,actor:"校赛演示操作员"});
  c.events.push({at:now,type:"review."+action.decision,artifactId:a.id});
 }else throw Object.assign(new Error("不支持的操作"),{status:400});
 return state;
}
export function explain(c,question){
 const a=c.artifacts.at(-1);const v=c.versions.at(-1);
 if(!a||!v)return {answer:"请先确认事实并运行分析。",citations:[]};
 const citations=[v.id,a.id];
 if(a.stale)return {answer:"当前结果已失效：确认了新的事实版本，需要重新执行分析和人工复核。",citations};
 const fired=a.results.filter(x=>x.fired),blocked=a.results.filter(x=>x.status==="blocked");
 if(question==="rules")return {answer:fired.length?"演示规则命中："+fired.map(x=>x.ruleId+"（"+x.label+"）").join("、")+"。这只是人工复核提示，不构成违法认定。":"本轮没有命中已可计算的演示规则。",citations:citations.concat(fired.map(x=>x.ruleId))};
 if(question==="review")return {answer:"当前分析绑定 "+v.id+"；"+(blocked.length?"存在"+blocked.length+"项字段缺口。":"分析结果仍需人工复核，不能自动代表机构决定。"),citations};
 if(question==="change")return {answer:"当关键事实变化并重新确认，依赖旧事实版本的 Artifact 将标记 stale，必须重新运行与复核。",citations};
 throw Object.assign(new Error("只支持三个预设解释问题"),{status:400});
}
