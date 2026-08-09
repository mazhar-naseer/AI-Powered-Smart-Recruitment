import{useState,type FormEvent,type ReactNode}from'react';
import{ArrowRight,BrainCircuit,BriefcaseBusiness,FileText,LockKeyhole,ShieldCheck,Sparkles,UserRoundCheck,Users}from'lucide-react';
import{Link,useNavigate}from'react-router-dom';
import{useAuth}from'../auth';
import{Logo}from'../components';
import{GoogleButton,useGoogleEnabled}from'./OAuth';

/** Shared brand panel for /login and /register. Presentation only. */
function AuthAside({eyebrow,title,lead,children}:{eyebrow:string;title:ReactNode;lead:string;children:ReactNode}){
  return <aside className="auth-aside">
    <div className="auth-aside-glow" aria-hidden="true"/>
    <div className="auth-brand"><Logo/></div>
    <div className="auth-aside-body">
      <span className="auth-eyebrow"><Sparkles/>{eyebrow}</span>
      <h1>{title}</h1>
      <p>{lead}</p>
      {children}
    </div>
    <div className="auth-illustration" aria-hidden="true"><span><LockKeyhole/></span><span><FileText/></span><span><BriefcaseBusiness/></span></div>
  </aside>;
}

export function Login(){
  const{login}=useAuth();const nav=useNavigate();const registered=new URLSearchParams(location.search).get('registered')==='1';
  const[email,setEmail]=useState('');const[password,setPassword]=useState('');
  const[error,setError]=useState('');const[busy,setBusy]=useState(false);const google=useGoogleEnabled();
  async function submit(event:FormEvent){event.preventDefault();setBusy(true);setError('');try{const user=await login(email,password);nav(user.role==='employer'?'/employer':user.role==='admin'?'/admin':'/applicant/jobs')}catch(reason){setError(reason instanceof Error?reason.message:'Login failed')}finally{setBusy(false)}}
  return <div className="auth-shell">
    <AuthAside eyebrow="Welcome back" title={<>Your next great <em>hire</em> starts here.</>} lead="Log in to pick up your hiring pipeline or job search exactly where you left it.">
      <ul className="auth-highlights">
        <li><span><BrainCircuit/></span><div><strong>AI resume intelligence</strong><small>Ranked candidates with transparent scoring.</small></div></li>
        <li><span><Users/></span><div><strong>Collaborative ATS</strong><small>Shared pipelines, notes, and assignments.</small></div></li>
        <li><span><ShieldCheck/></span><div><strong>Secure by default</strong><small>Verified accounts and audited access.</small></div></li>
      </ul>
    </AuthAside>
    <main className="auth-main">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-card-head"><h2>Login</h2><p>{google?'Use Google or your SmartHire credentials.':'Enter your SmartHire credentials to continue.'}</p></div>
        {registered&&!error&&<div className="alert success">Account created. Log in to continue.</div>}
        {error&&<div className="alert error">{error}</div>}
        <GoogleButton intent="login"/>
        <label>Email Address<input type="email" value={email} onChange={event=>setEmail(event.target.value)} placeholder="you@example.com" required/></label>
        <label>Password<input type="password" value={password} onChange={event=>setPassword(event.target.value)} minLength={8} required/></label>
        <div className="auth-meta"><Link to="/forgot-password">Forgot password?</Link></div>
        <button className="button full auth-submit" disabled={busy}>{busy?'Signing in…':'Login'}<ArrowRight size={17}/></button>
        <p className="center">Don’t have an account? <Link to="/register">Register here</Link></p>
      </form>
    </main>
  </div>;
}

export function Register(){
  const{register}=useAuth();const nav=useNavigate();const params=new URLSearchParams(location.search);
  const[role,setRole]=useState(params.get('role')||'applicant');const[error,setError]=useState('');const[busy,setBusy]=useState(false);const google=useGoogleEnabled();
  async function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setError('');const form=new FormData(event.currentTarget);try{const data=await register(Object.fromEntries(form.entries())as Record<string,string>);if(!data.verification_required){nav('/login?registered=1',{replace:true});return}nav(`/verify-email?email=${encodeURIComponent(data.email)}${data.dev_verification_code?`&code=${data.dev_verification_code}`:''}`)}catch(reason){setError(reason instanceof Error?reason.message:'Registration failed')}finally{setBusy(false)}}
  return <div className="auth-shell">
    <AuthAside eyebrow="Get started" title={<>Hiring, made <em>measurably</em> smarter.</>} lead="Create your account to post roles, apply to jobs, and let SmartHire AI do the heavy lifting.">
      <ul className="auth-highlights">
        <li><span><UserRoundCheck/></span><div><strong>One account, both sides</strong><small>Apply as a candidate or hire as an employer.</small></div></li>
        <li><span><BrainCircuit/></span><div><strong>Instant resume scoring</strong><small>Every application analysed on arrival.</small></div></li>
        <li><span><ShieldCheck/></span><div><strong>Email-verified access</strong><small>Your workspace stays yours.</small></div></li>
      </ul>
    </AuthAside>
    <main className="auth-main">
      <form className="auth-card wide" onSubmit={submit}>
        <div className="auth-card-head"><h2>Create your SmartHire account</h2><p>{google?'Choose your account type before continuing with Google.':'Choose your account type to get started.'}</p></div>
        {error&&<div className="alert error">{error}</div>}
        <div className={`role-tabs ${role==='employer'?'employer':''}`}>
          <button type="button" className={role==='applicant'?'active':''} onClick={()=>setRole('applicant')}>Applicant</button>
          <button type="button" className={role==='employer'?'active':''} onClick={()=>setRole('employer')}>Employer</button>
        </div>
        <GoogleButton intent="register" role={role}/>
        <input type="hidden" name="role" value={role}/>
        <div className="form-grid">
          <label>Full name<input name="full_name" minLength={2} required/></label>
          <label>Email<input name="email" type="email" required/></label>
          {role==='employer'&&<label>Company name<input name="company_name" required/></label>}
          <label>Password<input name="password" type="password" minLength={8} required/></label>
        </div>
        <button className="button full auth-submit" disabled={busy}>{busy?'Creating…':'Create Account'}<ArrowRight size={17}/></button>
        <p className="center">Already registered? <Link to="/login">Login</Link></p>
      </form>
    </main>
  </div>;
}
