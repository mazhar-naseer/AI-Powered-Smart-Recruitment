import{Fragment,useEffect,useState,type FormEvent}from'react';import{Link,useParams}from'react-router-dom';import{BriefcaseBusiness,CheckCircle2,ChevronDown,ChevronUp,MapPin,Search,UploadCloud}from'lucide-react';import{request}from'../api';import{Badge,Empty,Spinner}from'../components';import type{Application,Job}from'../types';
function JobCard({job}:{job:Job}){return <article className="job-card"><div className="job-icon"><BriefcaseBusiness/></div><div className="job-main"><h3>{job.title}</h3><p>{job.employer.company_name||job.employer.full_name}</p><span><MapPin size={13}/>{job.location||'Remote / flexible'}</span><div className="chips">{job.required_skills.slice(0,5).map(skill=><Badge key={skill} tone="blue">{skill}</Badge>)}</div></div><div className="job-action"><Badge>{job.status}</Badge><small>Posted {new Date(job.created_at).toLocaleDateString()}</small><Link className="button small" to={`/applicant/jobs/${job.id}`}>View Details</Link></div></article>}
export function ApplicantJobs(){const[jobs,setJobs]=useState<Job[]>();const[q,setQ]=useState('');async function load(search=''){const data=await request<any>(`/jobs?q=${encodeURIComponent(search)}`);setJobs(data.items)}useEffect(()=>{load()},[]);return <><div className="page-title"><div><h1>Job Board</h1><p>Find the right opportunity for your career.</p></div></div><form className="searchbar" onSubmit={e=>{e.preventDefault();load(q)}}><Search/><input aria-label="Search jobs" value={q} onChange={e=>setQ(e.target.value)} placeholder="Search jobs by title, skills or company…"/><button className="button">Search</button></form><section className="panel jobs">{!jobs?<Spinner/>:jobs.length?jobs.map(job=><JobCard key={job.id} job={job}/>):<Empty title="No matching jobs" body="Try a broader search or check back later."/>}</section></>}
export function JobDetails(){
  const{id}=useParams();
  const[job,setJob]=useState<Job>();
  const[existing,setExisting]=useState<Application|null>();
  const[file,setFile]=useState<File>();
  const[error,setError]=useState('');
  const[busy,setBusy]=useState(false);
  const[justSubmitted,setJustSubmitted]=useState(false);
  useEffect(()=>{
    Promise.all([request<Job>(`/jobs/${id}`),request<Application[]>('/applicant/applications')])
      .then(([jobData,applications])=>{setJob(jobData);setExisting(applications.find(application=>application.job_id===id)||null)})
      .catch(err=>setError(err instanceof Error?err.message:'Could not load job details'))
  },[id]);
  async function apply(e:FormEvent){
    e.preventDefault();
    if(existing)return;
    if(!file)return setError('Please select a PDF or DOCX resume.');
    const form=new FormData();form.append('resume',file);setBusy(true);setError('');
    try{
      const submitted=await request<{id:string;status:string}>(`/jobs/${id}/applications`,{method:'POST',body:form});
      setJustSubmitted(true);
      setExisting({id:submitted.id,status:submitted.status,job_id:id,matched_skills:[],component_scores:{},ai_strengths:[],ai_gaps:[],created_at:new Date().toISOString()} as Application)
    }catch(err){
      const message=err instanceof Error?err.message:'Application failed';setError(message);
      if(message.toLowerCase().includes('already applied')){
        const applications=await request<Application[]>('/applicant/applications');
        setExisting(applications.find(application=>application.job_id===id)||null)
      }
    }finally{setBusy(false)}
  }
  if(!job||existing===undefined)return <Spinner/>;
  return <><div className="job-detail-head"><div className="job-icon"><BriefcaseBusiness/></div><div><h1>{job.title}</h1><p>{job.employer.company_name||job.employer.full_name}</p><span><MapPin size={14}/>{job.location||'Remote / flexible'} · {job.employment_type||'Full-time'}</span></div></div><div className="job-detail-grid"><section className="panel prose"><h2>Job Description</h2><p>{job.description}</p><h3>Required Skills</h3><div className="chips">{job.required_skills.map(s=><Badge key={s} tone="blue">{s}</Badge>)}</div><div className="job-facts"><div><span>Experience</span><strong>{job.experience_level||'Not specified'}</strong></div><div><span>Job Type</span><strong>{job.employment_type||'Full-time'}</strong></div><div><span>Salary</span><strong>{job.salary_min?`${job.salary_min} - ${job.salary_max||'Open'}`:'Not disclosed'}</strong></div></div></section>{existing?<section className={`panel applied-card ${justSubmitted?'new-submission':''}`}><div className="applied-check"><CheckCircle2/></div><Badge tone={existing.status==='completed'?'green':'orange'}>{existing.status}</Badge><h2>{justSubmitted?'Application submitted successfully':'Application already submitted'}</h2><p>{justSubmitted?`We received your resume for ${job.title}. SmartHire is now processing your match analysis.`:`You applied on ${new Date(existing.created_at).toLocaleDateString()}. Your resume is already attached to this specific job application.`}</p>{existing.final_score!=null&&<div className="applied-score"><span>Current match score</span><strong>{existing.final_score}%</strong></div>}<Link className="button full" to={`/applicant/applications?application=${existing.id}`}>Track this application</Link></section>:<form className="panel upload" onSubmit={apply}><h2>Apply for this job</h2><p>Upload Resume (PDF or DOCX)</p>{error&&<div className="alert error">{error}</div>}<label className="dropzone"><UploadCloud/><strong>Choose your PDF or DOCX resume</strong><small>Maximum file size: 5 MB</small><input type="file" accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx" onChange={e=>setFile(e.target.files?.[0])}/>{file&&<b>{file.name}</b>}</label><button className="button full" disabled={busy}>{busy?'Submitting…':'Submit Application'}</button></form>}</div></>
}

const KPI=[
  {key:'semantic',label:'Semantic relevance',detail:'Local word and character vector similarity against the complete role.'},
  {key:'skills',label:'Skill evidence',detail:'Alias-aware evidence for mandatory, preferred, and optional skills.'},
  {key:'experience',label:'Experience evidence',detail:'Explicit years of experience compared with the requested seniority.'},
  {key:'role_alignment',label:'Role alignment',detail:'Alignment between resume role language and the target title.'},
  {key:'domain',label:'Domain knowledge',detail:'Evidence for employer-defined industry and domain terminology.'},
  {key:'education_certifications',label:'Education & certifications',detail:'Coverage of configured education and certification requirements.'},
] as const;

function InsightReport({application,onRetryAI,retryingAI}:{application:Application;onRetryAI:(id:string)=>void;retryingAI?:string}){
  const scores=application.component_scores||{};
  const weights=scores.scorecard_weights||application.job?.scorecard||{semantic:15,skills:35,experience:25,role_alignment:15,domain:5,education_certifications:5};
  const deterministic=scores.deterministic_total??application.deterministic_score??KPI.reduce((total,kpi)=>total+(scores[kpi.key]||0)*(weights[kpi.key]||0)/100,0);
  const missing=(application.job?.required_skills||[]).filter(skill=>!application.matched_skills.some(matched=>matched.toLowerCase()===skill.toLowerCase()));
  const geminiScore=application.ai_score??scores.gemini_semantic;
  const deterministicWeight=scores.deterministic_weight??65;
  const aiWeight=scores.ai_weight??35;
  const aiConfidence=scores.ai_confidence;
  const scoreDifference=scores.score_difference;
  const manualReview=Boolean(scores.manual_review_required);
  return <div className="insight-report">
    <div className="insight-head"><div><span className="eyebrow">Explainable match report</span><h3>Why this application scored {application.final_score?.toFixed(2)}%</h3><p>{application.ai_summary}</p></div><div className="score-orbit" style={{background:`radial-gradient(circle,#fff 55%,transparent 56%),conic-gradient(var(--green) 0 ${application.final_score||0}%,#e3e9f2 ${application.final_score||0}% 100%)`}}><strong>{application.final_score?.toFixed(0)}%</strong><span>Overall match</span></div></div>
    <div className="kpi-grid">{KPI.map(kpi=>{const raw=Number(scores[kpi.key]||0);const weight=Number(weights[kpi.key]||0);const contribution=raw*weight/100;return <article className="kpi-card" key={kpi.key}><div className="kpi-title"><span>{kpi.label}</span><strong>{raw.toFixed(1)}%</strong></div><div className="kpi-bar"><i style={{width:`${Math.min(100,Math.max(0,raw))}%`}}/></div><div className="kpi-math"><span>Weight {weight}%</span><b>+{contribution.toFixed(2)} points</b></div><p>{kpi.detail}</p></article>})}</div>
    <div className="calculation"><strong>Score calculation</strong><code>{KPI.map(kpi=>`${Number(scores[kpi.key]||0).toFixed(2)} × ${Number(weights[kpi.key]||0)}%`).join(' + ')} = {deterministic.toFixed(2)}%</code>{geminiScore!=null?<div><p>Gemini assessment: {geminiScore.toFixed(2)}%. Final score = {deterministicWeight.toFixed(1)}% deterministic + {aiWeight.toFixed(1)}% Gemini. AI influence is confidence-adjusted.</p>{aiConfidence!=null&&<p>Gemini confidence: {aiConfidence.toFixed(1)}% · Engine difference: {scoreDifference?.toFixed(1)} points.</p>}{manualReview&&<p><strong>Guardrail triggered:</strong> The engines disagree significantly, so an employer must manually review this result.</p>}</div>:<div><p>Deterministic score is complete. Gemini status: <strong>{application.ai_status||'not configured'}</strong>.</p>{application.ai_status==='failed'&&<><p className="muted">{application.ai_error||'The Gemini request did not complete.'}</p><button className="button tiny" disabled={retryingAI===application.id} onClick={()=>onRetryAI(application.id)}>{retryingAI===application.id?'Retrying Gemini…':'Retry Gemini analysis'}</button></>}</div>}</div>
    {application.evidence_matrix?.length?<div className="evidence-matrix"><h4>Evidence matrix</h4>{application.evidence_matrix.map((item,index)=><article key={`${item.category}-${item.criterion}-${index}`}><div><Badge tone={item.matched?'green':'orange'}>{item.matched?'Found':'Missing'}</Badge><strong>{item.criterion}</strong><small>{item.category.replaceAll('_',' ')} · {item.priority}</small></div><p>{item.evidence?.join(' · ')||'No supporting resume evidence found.'}</p></article>)}</div>:null}
    <div className="evidence-grid"><section><h4>Matched evidence</h4><div className="chips">{application.matched_skills.length?application.matched_skills.map(skill=><Badge key={skill} tone="green">{skill}</Badge>):<span className="muted">No required skills detected</span>}</div></section><section><h4>Missing or weak evidence</h4><div className="chips">{missing.length?missing.map(skill=><Badge key={skill} tone="orange">{skill}</Badge>):<span className="muted">All required skills were detected</span>}</div></section><section><h4>Engine and recommendation</h4><p><strong>{application.ai_provider||'Processing'}</strong></p><p className="muted">Recommendation: {application.ai_recommendation?.replaceAll('_',' ')||'Pending'}</p></section></div>
    <div className="insight-note"><strong>Audit trail:</strong> Analysis {application.analysis_version||'legacy'} · Parser {application.parser_version||'legacy'} · Prompt {String(scores.prompt_version||'legacy')}. Matching every skill alone does not produce 100%; the employer controls the six-part scorecard.</div>
  </div>
}

export function ApplicantApplications(){
  const targetApplication=new URLSearchParams(location.search).get('application')||undefined;
  const[apps,setApps]=useState<Application[]>();
  const[retrying,setRetrying]=useState<string>();
  const[retryingAI,setRetryingAI]=useState<string>();
  const[expanded,setExpanded]=useState<string|undefined>(targetApplication);
  const load=()=>request<Application[]>('/applicant/applications').then(items=>setApps(targetApplication?[...items].sort((a,b)=>a.id===targetApplication?-1:b.id===targetApplication?1:0):items));
  useEffect(()=>{void load()},[]);
  useEffect(()=>{
    if(!apps?.some(application=>application.status==='processing'||application.ai_status==='processing'))return;
    const timer=window.setInterval(()=>{void load()},2500);
    return()=>window.clearInterval(timer)
  },[apps]);
  useEffect(()=>{
    if(!apps||!targetApplication)return;
    document.querySelector('.applications-panel .insight-row')?.scrollIntoView({behavior:'smooth',block:'center'});
  },[apps,targetApplication]);
  async function retry(id:string){
    setRetrying(id);
    try{await request(`/applicant/applications/${id}/retry`,{method:'POST'});await load()}
    finally{setRetrying(undefined)}
  }
  async function retryAI(id:string){
    setRetryingAI(id);
    try{await request(`/applicant/applications/${id}/retry-ai`,{method:'POST'});await load()}
    finally{setRetryingAI(undefined)}
  }
  return <><div className="page-title"><div><h1>My Applications</h1><p>Track your submitted applications and match results.</p></div><Link className="button" to="/applicant/jobs">Browse Jobs</Link></div><section className="panel applications-panel">{!apps?<Spinner/>:apps.length?<div className="table-wrap"><table><thead><tr><th>Job</th><th>Company</th><th>Applied</th><th>Status</th><th>Match</th><th>AI Insight</th></tr></thead><tbody>{apps.map(a=><Fragment key={a.id}><tr><td><strong>{a.job?.title}</strong></td><td>{a.job?.employer.company_name}</td><td>{new Date(a.created_at).toLocaleDateString()}</td><td><Badge tone={a.status==='completed'?'green':a.status==='failed'?'red':'orange'}>{a.status}</Badge></td><td><strong>{a.final_score!=null?`${a.final_score}%`:'—'}</strong></td><td>{a.status==='failed'?<div className="analysis-error"><strong>Resume analysis failed</strong><small>{a.processing_error||'The resume could not be processed.'}</small><button className="button tiny" disabled={retrying===a.id} onClick={()=>retry(a.id)}>{retrying===a.id?'Retrying…':'Retry analysis'}</button></div>:a.status==='completed'?<button className="insight-trigger" aria-expanded={expanded===a.id} onClick={()=>setExpanded(expanded===a.id?undefined:a.id)}><span><strong>View match diagnosis</strong><small>{a.ai_status==='processing'?'Gemini analysis is processing…':a.ai_summary}</small></span>{expanded===a.id?<ChevronUp/>:<ChevronDown/>}</button>:<small>Analysis is processing…</small>}</td></tr>{expanded===a.id&&a.status==='completed'&&<tr className="insight-row"><td colSpan={6}><InsightReport application={a} onRetryAI={retryAI} retryingAI={retryingAI}/></td></tr>}</Fragment>)}</tbody></table></div>:<Empty title="No applications yet" body="Browse open jobs and submit your first application."/>}</section></>
}
