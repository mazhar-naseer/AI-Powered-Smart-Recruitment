// @ts-nocheck
import{useState,type FormEvent}from'react';import{Link,Navigate,useNavigate}from'react-router-dom';import{ArrowRight,BrainCircuit,CheckCircle2,Clock3,LockKeyhole,ShieldCheck,Users}from'lucide-react';import{Logo}from'../components';import{useAuth}from'../auth';
export function Landing(){return <div className="landing"><nav className="landing-nav"><Logo/><div><a href="#features">Features</a><a href="#roles">For Employers</a><a href="#roles">For Applicants</a><Link className="button small" to="/register">Get Started</Link></div></nav><section className="hero"><div><h1>Smart Hiring.<br/>Better Matches.<br/><em>Stronger Teams.</em></h1><p>AI-powered resume screening that connects the right talent with the right opportunities.</p><div className="hero-actions"><Link className="button" to="/register?role=employer">I’m an Employer</Link><Link className="button outline" to="/register?role=applicant">I’m an Applicant</Link></div></div><div className="hero-art"><div className="resume-card"><div className="avatar">👤</div><div className="lines"/><strong>95%<small>Match</small></strong></div><div className="people">👨‍💻 <span>🤝</span> 👩‍💼</div></div></section><section id="features" className="features"><h2>Why SmartHire?</h2><div className="feature-grid">{[[BrainCircuit,'Smart Resume Screening','Our engine analyzes resumes and ranks candidates by best match.'],[Clock3,'Save Valuable Time','Reduce manual effort and focus on the best candidates.'],[Users,'Better Quality Hire','Find talent whose skills match your actual needs.'],[LockKeyhole,'Secure & Reliable','Private files and role-based access protect every step.']].map(([Icon,title,body])=><article key={String(title)}><Icon/><h3>{title}</h3><p>{body}</p><CheckCircle2 size={16}/></article>)}</div></section><section className="numbers"><div><strong>500+</strong><span>Companies</span></div><div><strong>10K+</strong><span>Job Seekers</span></div><div><strong>25K+</strong><span>Resumes Processed</span></div><div><strong>98%</strong><span>Satisfaction Rate</span></div></section></div>}
export function Login(){const{login}=useAuth();const nav=useNavigate();const registered=new URLSearchParams(location.search).get('registered')==='1';const[email,setEmail]=useState('');const[password,setPassword]=useState('');const[error,setError]=useState('');const[busy,setBusy]=useState(false);async function submit(e:FormEvent){e.preventDefault();setBusy(true);setError('');try{const user=await login(email,password);nav(user.role==='employer'?'/employer':user.role==='admin'?'/admin':'/applicant/jobs')}catch(err){setError(err instanceof Error?err.message:'Login failed')}finally{setBusy(false)}}return <div className="auth-page"><div className="auth-side"><Logo/><div><h1>Welcome back!</h1><p>Login to continue your hiring or job search journey.</p><div className="auth-illustration">🔐<span>📄</span><span>💼</span></div></div></div><form className="auth-card" onSubmit={submit}><h2>Login</h2><p>Enter your account credentials.</p>{registered&&!error&&<div className="alert success">Account created. Log in to continue.</div>}{error&&<div className="alert error">{error}</div>}<label>Email Address<input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" required/></label><label>Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} minLength={8} required/></label><button className="button full" disabled={busy}>{busy?'Signing in…':'Login'}<ArrowRight size={17}/></button><p className="center">Don’t have an account? <Link to="/register">Register here</Link></p></form></div>}
export function Register(){const{register}=useAuth();const nav=useNavigate();const params=new URLSearchParams(location.search);const[role,setRole]=useState(params.get('role')||'applicant');const[error,setError]=useState('');const[busy,setBusy]=useState(false);async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError('');const form=new FormData(e.currentTarget);try{const data=await register(Object.fromEntries(form.entries())as Record<string,string>);if(!data.verification_required){nav('/login?registered=1',{replace:true});return}nav(`/verify-email?email=${encodeURIComponent(data.email)}${data.dev_verification_code?`&code=${data.dev_verification_code}`:''}`)}catch(err){setError(err instanceof Error?err.message:'Registration failed')}finally{setBusy(false)}}return <div className="register-page"><Link to="/"><Logo/></Link><form className="auth-card wide" onSubmit={submit}><h2>Create your SmartHire account</h2><p>Choose how you want to use the platform.</p>{error&&<div className="alert error">{error}</div>}<div className="role-tabs"><button type="button" className={role==='applicant'?'active':''} onClick={()=>setRole('applicant')}>Applicant</button><button type="button" className={role==='employer'?'active':''} onClick={()=>setRole('employer')}>Employer</button></div><input type="hidden" name="role" value={role}/><div className="form-grid"><label>Full name<input name="full_name" minLength={2} required/></label><label>Email<input name="email" type="email" required/></label>{role==='employer'&&<label>Company name<input name="company_name" required/></label>}<label>Password<input name="password" type="password" minLength={8} required/></label></div><button className="button full" disabled={busy}>{busy?'Creating…':'Create Account'}</button><p className="center">Already registered? <Link to="/login">Login</Link></p></form></div>}

export function VerifyEmail(){
  const params=new URLSearchParams(location.search);
  const email=params.get('email')||'';
  const token=params.get('token')||'';
  const{verifyEmail}=useAuth();
  const nav=useNavigate();
  const[code,setCode]=useState(params.get('code')||'');
  const[error,setError]=useState('');
  const[busy,setBusy]=useState(false);
  async function verify(e:FormEvent){
    e.preventDefault();setBusy(true);setError('');
    try{
      const user=await verifyEmail(token?{token}:{email,code});
      nav(user.role==='employer'?'/employer':user.role==='admin'?'/admin':'/applicant/jobs',{replace:true})
    }catch(err){
      setError(err instanceof Error?err.message:'Verification code is invalid or expired');setBusy(false)
    }
  }
  return <div className="register-page"><Link to="/"><Logo/></Link><form className="auth-card" onSubmit={verify}><h2>Verify your email</h2><p>{token?'Confirm this verification link to securely access your account.':'Enter the six-digit code sent to your email. You will be logged in automatically.'}</p>{error&&<div className="alert error">{error}</div>}{!token&&<label>Verification code<input value={code} inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" onChange={e=>setCode(e.target.value.replace(/\D/g,''))} disabled={busy} required/></label>}<button className="button full" disabled={busy||(!token&&code.length!==6)}>{busy?'Verifying and signing in…':'Verify and continue'}</button></form></div>
}

export function AdminLogin(){
  const{user,login,logout}=useAuth();const nav=useNavigate();
  const[email,setEmail]=useState('');const[password,setPassword]=useState('');
  const[error,setError]=useState('');const[busy,setBusy]=useState(false);
  if(user?.role==='admin')return <Navigate to="/admin" replace/>;
  async function submit(e:FormEvent){
    e.preventDefault();setBusy(true);setError('');
    try{
      if(user)await logout();
      const authenticated=await login(email,password);
      if(authenticated.role!=='admin'){
        await logout();
        throw new Error('This portal is restricted to platform administrators.');
      }
      nav('/admin',{replace:true});
    }catch(err){setError(err instanceof Error?err.message:'Administrative sign-in failed')}
    finally{setBusy(false)}
  }
  return <div className="admin-login-page">
    <section className="admin-login-intro">
      <Link className="admin-brand large" to="/" aria-label="SmartHire home"><span><ShieldCheck/></span><div><strong>SmartHire</strong><small>CONTROL CENTER</small></div></Link>
      <div><span className="admin-kicker">SECURE OPERATIONS PORTAL</span><h1>Platform control.<br/>Clear oversight.</h1><p>A dedicated workspace for identity governance, job moderation, system health, and recruitment intelligence operations.</p><div className="admin-security-note"><LockKeyhole/><div><strong>Restricted system</strong><small>Access is audited and limited to authorized administrators.</small></div></div></div>
      <small>SmartHire Platform Operations · Local Environment</small>
    </section>
    <form className="admin-login-card" onSubmit={submit}>
      <div className="admin-login-icon"><ShieldCheck/></div><span className="admin-kicker">ADMINISTRATOR ACCESS</span><h2>Sign in to Control Center</h2><p>Use your separately provisioned administrator credentials.</p>
      {error&&<div className="alert error">{error}</div>}
      <label>Administrator email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="username" placeholder="admin@company.com" required/></label>
      <label>Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" minLength={8} required/></label>
      <button className="admin-login-button" disabled={busy}>{busy?'Verifying access…':'Enter Control Center'}<ArrowRight size={17}/></button>
      <Link className="admin-back" to="/forgot-password?portal=admin">Forgot administrator password?</Link>
      <Link className="admin-back" to="/login">← Return to SmartHire application</Link>
    </form>
  </div>
}
