import {useEffect, useState, type FormEvent} from 'react';
import {Building2, Check, CreditCard, Download, Search, ShieldCheck, Sparkles, TrendingUp, UsersRound} from 'lucide-react';
import {request} from '../api';
import {Badge, Spinner} from '../components';
import '../admin-saas.css';

type Metric = {used:number; limit:number|null};
type SaaSData = {
  organization:{id:string; name:string; slug:string; settings:Record<string,any>};
  subscription:{plan_key:string; status:string; billing_provider:string; trial_ends_at?:string; current_period_end?:string};
  plans:Record<string,{name:string; monthly_price:number; description:string; limits:Record<string,number|null>}>;
  usage:Record<string,Metric>;
  onboarding:Record<string,boolean>;
};

const labels:Record<string,string> = {
  active_jobs:'Active jobs', team_members:'Team members',
  ai_analyses_monthly:'AI analyses this month', storage_mb:'Private storage (MB)',
};

export function WorkspaceCommercial(){
  const [data,setData]=useState<SaaSData>();
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');
  const load=()=>request<SaaSData>('/workspace/saas').then(setData);
  useEffect(()=>{void load()},[]);

  async function save(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setError('');setMessage('');
    const form=new FormData(event.currentTarget);
    const payload={
      name:String(form.get('name')), timezone:String(form.get('timezone')),
      company_domain:String(form.get('company_domain')||'')||null,
      careers_url:String(form.get('careers_url')||'')||null,
      primary_color:String(form.get('primary_color')),
      data_retention_days:Number(form.get('data_retention_days')),
      candidate_email_notifications:form.get('candidate_email_notifications')==='on',
      onboarding_completed:true,
    };
    try{await request('/workspace/settings',{method:'PATCH',body:JSON.stringify(payload)});setMessage('Company settings saved successfully.');await load()}
    catch(reason){setError(reason instanceof Error?reason.message:'Settings could not be saved')}
  }
  async function plan(plan_key:string){
    if(!confirm(`Change this workspace to the ${data?.plans[plan_key].name} plan?`))return;
    try{await request('/workspace/billing/change-plan',{method:'POST',body:JSON.stringify({plan_key})});setMessage('Subscription updated.');await load()}
    catch(reason){setError(reason instanceof Error?reason.message:'Plan could not be changed')}
  }
  async function exportData(){
    const exported=await request<any>('/workspace/data-export');
    const url=URL.createObjectURL(new Blob([JSON.stringify(exported,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=`smarthire-${data?.organization.slug}-export.json`;link.click();URL.revokeObjectURL(url);
  }
  if(!data)return <Spinner/>;
  const settings=data.organization.settings;
  return <>
    <div className="page-title"><div><span className="eyebrow">Commercial workspace</span><h1>Workspace & Billing</h1><p>Manage company identity, plan capacity, privacy, and operational readiness.</p></div><Badge tone="blue">{data.subscription.status} · {data.plans[data.subscription.plan_key]?.name}</Badge></div>
    {message&&<div className="alert success">{message}</div>}{error&&<div className="alert error">{error}</div>}
    <section className="commercial-summary"><article><Building2/><div><span>Onboarding</span><strong>{Object.values(data.onboarding).filter(Boolean).length}/{Object.keys(data.onboarding).length} complete</strong></div></article><article><Sparkles/><div><span>Current plan</span><strong>{data.plans[data.subscription.plan_key]?.name}</strong></div></article><article><ShieldCheck/><div><span>Billing mode</span><strong>{data.subscription.billing_provider}</strong></div></article></section>
    <div className="usage-grid">{Object.entries(data.usage).map(([key,value])=>{const percentage=value.limit?Math.min(100,Math.round(value.used/value.limit*100)):0;return <article className="panel" key={key}><div><span>{labels[key]||key}</span><strong>{value.used} / {value.limit??'Unlimited'}</strong></div><div className="usage-track"><i style={{width:value.limit?`${percentage}%`:'12%'}}/></div><small>{value.limit?`${Math.max(0,value.limit-value.used)} remaining in this plan`:'No plan limit'}</small></article>})}</div>
    <section className="plan-grid">{Object.entries(data.plans).map(([key,item])=><article className={`panel plan-card ${key===data.subscription.plan_key?'selected':''}`} key={key}><span>{item.name}</span><h2>${item.monthly_price}<small>/month</small></h2><p>{item.description}</p><ul>{Object.entries(item.limits).map(([metric,limit])=><li key={metric}><Check/>{limit??'Unlimited'} {labels[metric]?.toLowerCase()||metric}</li>)}</ul><button className="button" disabled={key===data.subscription.plan_key} onClick={()=>plan(key)}>{key===data.subscription.plan_key?'Current plan':'Select plan'}</button></article>)}</section>
    <div className="commercial-settings">
      <form className="panel workspace-settings-card" onSubmit={save}>
        <div className="workspace-settings-head"><div className="workspace-settings-icon"><Building2/></div><div><span>WORKSPACE PROFILE</span><h2>Company information</h2><p>Keep your employer identity and operational preferences accurate.</p></div></div>
        <div className="field-grid">
          <label><span>Company name</span><input name="name" defaultValue={data.organization.name} minLength={2} required/><small>Displayed across jobs, emails, and candidate experiences.</small></label>
          <label><span>Timezone</span><input name="timezone" defaultValue={settings.timezone||'Asia/Karachi'} placeholder="Asia/Karachi" required/><small>Used for interviews, reports, and timestamps.</small></label>
          <label><span>Company domain</span><input name="company_domain" defaultValue={settings.company_domain||''} placeholder="company.com"/><small>Your public business domain.</small></label>
          <label><span>Careers page URL</span><input name="careers_url" type="url" defaultValue={settings.careers_url||''} placeholder="https://company.com/careers"/><small>Where candidates can learn about your company.</small></label>
          <label className="color-field"><span>Brand color</span><div><input aria-label="Brand color" name="primary_color" type="color" defaultValue={settings.primary_color||'#173fbf'}/><strong>{settings.primary_color||'#173fbf'}</strong></div><small>Used for branded candidate experiences.</small></label>
          <label><span>Data retention period</span><div className="retention-input"><input name="data_retention_days" type="number" min="30" max="3650" defaultValue={settings.data_retention_days||365}/><b>days</b></div><small>How long candidate information is retained.</small></label>
        </div>
        <div className="workspace-preferences"><div><strong>Candidate lifecycle emails</strong><span>Notify candidates when important application events occur.</span></div><label className="switch"><input name="candidate_email_notifications" type="checkbox" defaultChecked={settings.candidate_email_notifications!==false}/><i/></label></div>
        <div className="workspace-save"><div><strong>Changes are tenant-specific</strong><span>Only workspace owners can update these settings.</span></div><button className="button">Save company settings</button></div>
      </form>
      <section className="panel privacy-card"><div className="privacy-icon"><ShieldCheck/></div><span className="privacy-kicker">DATA GOVERNANCE</span><h2>Privacy & portability</h2><p>Download a secure, tenant-scoped record of your workspace. Every export is recorded in the platform audit log.</p><div className="privacy-meta"><span>Current retention</span><strong>{settings.data_retention_days||365} days</strong></div><button className="button ghost" onClick={exportData}><Download/>Export workspace data</button><small>JSON format · Jobs, applications, and workspace settings</small></section>
    </div>
  </>;
}

export function AdminCommercial(){
  const[data,setData]=useState<any>();const[query,setQuery]=useState('');const[status,setStatus]=useState('all');useEffect(()=>{request('/admin/saas/overview').then(setData)},[]);if(!data)return <Spinner/>;
  const accounts=(data.accounts||[]).filter((account:any)=>(status==='all'||account.status===status)&&account.name.toLowerCase().includes(query.toLowerCase()));
  const distribution=(data.accounts||[]).reduce((result:Record<string,number>,account:any)=>({...result,[account.plan]:(result[account.plan]||0)+1}),{});
  const activation=data.organizations?Math.round(data.active_subscriptions/data.organizations*100):0;
  return <div className="saas-admin">
    <section className="saas-admin-hero"><div><span>COMMERCIAL OPERATIONS</span><h1>Subscription command center</h1><p>Monitor tenant health, revenue readiness, and plan adoption across the SmartHire platform.</p></div><div className="saas-hero-signal"><i/><div><strong>Portfolio healthy</strong><span>{activation}% subscription activation</span></div></div></section>
    <div className="saas-admin-kpis"><article className="mint"><div className="saas-kpi-icon"><Building2/></div><div><span>Total organizations</span><strong>{data.organizations}</strong><small>Tenant workspaces provisioned</small></div></article><article className="blue"><div className="saas-kpi-icon"><UsersRound/></div><div><span>Active subscriptions</span><strong>{data.active_subscriptions}</strong><small>{activation}% of all organizations</small></div></article><article className="violet"><div className="saas-kpi-icon"><TrendingUp/></div><div><span>Estimated MRR</span><strong>${Number(data.estimated_mrr||0).toLocaleString()}</strong><small>Current monthly run rate</small></div></article><article className="amber"><div className="saas-kpi-icon"><CreditCard/></div><div><span>Paid plan adoption</span><strong>{Object.entries(distribution).filter(([plan])=>plan!=='starter').reduce((sum,[,count])=>sum+(count as number),0)}</strong><small>Tenants above Starter</small></div></article></div>
    <div className="saas-admin-layout"><section className="saas-tenant-panel"><header><div><span className="section-kicker">TENANT PORTFOLIO</span><h2>Organization accounts</h2><p>Review commercial state and subscription tier for every workspace.</p></div><div className="saas-table-tools"><label><Search/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search organizations…"/></label><select value={status} onChange={event=>setStatus(event.target.value)}><option value="all">All statuses</option><option value="active">Active</option><option value="trialing">Trialing</option><option value="past_due">Past due</option><option value="canceled">Canceled</option></select></div></header><div className="saas-table"><div className="saas-row saas-row-head"><span>ORGANIZATION</span><span>SUBSCRIPTION PLAN</span><span>ACCOUNT STATUS</span><span>HEALTH</span></div>{accounts.map((account:any,index:number)=><div className="saas-row" key={account.id}><div className="tenant-identity"><i>{account.name.slice(0,2).toUpperCase()}</i><div><strong>{account.name}</strong><span>Tenant #{String(index+1).padStart(2,'0')}</span></div></div><div><span className={`plan-pill plan-${account.plan}`}>{account.plan}</span></div><div><span className={`status-pill status-${account.status}`}><i/>{account.status.replace('_',' ')}</span></div><div className="health-cell"><span>{account.status==='active'?'Operational':'Attention'}</span><div><i style={{width:account.status==='active'?'92%':'48%'}}/></div></div></div>)}{!accounts.length&&<div className="saas-empty"><Search/><strong>No tenant accounts found</strong><span>Try changing your search or status filter.</span></div>}</div><footer><span>Showing {accounts.length} of {data.accounts.length} organizations</span><small>Commercial data refreshes with the latest billing state.</small></footer></section>
    <aside className="saas-insights"><div><span className="section-kicker">PLAN MIX</span><h2>Subscription distribution</h2><p>Current adoption by product tier.</p></div><div className="plan-distribution">{Object.entries(distribution).map(([plan,count],index)=><article key={plan}><div><i className={`distribution-dot dot-${index%4}`}/><strong>{plan}</strong><span>{count as number} tenants</span></div><b>{Math.round((count as number)/data.organizations*100)}%</b><div className="distribution-track"><i style={{width:`${(count as number)/data.organizations*100}%`}}/></div></article>)}</div><div className="revenue-readiness"><Sparkles/><div><strong>Revenue readiness</strong><p>{data.estimated_mrr>0?'Recurring revenue is active and being tracked.':'All current tenants are on non-revenue plans. Upgrade conversions will appear here.'}</p></div></div></aside></div>
  </div>;
}
