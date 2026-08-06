import{useState,type FormEvent}from'react';
import{ArrowRight}from'lucide-react';
import{Link,useNavigate}from'react-router-dom';
import{useAuth}from'../auth';
import{Logo}from'../components';
import{GoogleButton}from'./OAuth';

export function Login(){
  const{login}=useAuth();const nav=useNavigate();
  const[email,setEmail]=useState('');const[password,setPassword]=useState('');
  const[error,setError]=useState('');const[busy,setBusy]=useState(false);
  async function submit(event:FormEvent){event.preventDefault();setBusy(true);setError('');try{const user=await login(email,password);nav(user.role==='employer'?'/employer':user.role==='admin'?'/admin':'/applicant/jobs')}catch(reason){setError(reason instanceof Error?reason.message:'Login failed')}finally{setBusy(false)}}
  return <div className="auth-page"><div className="auth-side"><Logo/><div><h1>Welcome back!</h1><p>Login to continue your hiring or job search journey.</p><div className="auth-illustration">🔐<span>📄</span><span>💼</span></div></div></div><form className="auth-card" onSubmit={submit}><h2>Login</h2><p>Use Google or your SmartHire credentials.</p>{error&&<div className="alert error">{error}</div>}<GoogleButton intent="login"/><label>Email Address<input type="email" value={email} onChange={event=>setEmail(event.target.value)} placeholder="you@example.com" required/></label><label>Password<input type="password" value={password} onChange={event=>setPassword(event.target.value)} minLength={8} required/></label><button className="button full" disabled={busy}>{busy?'Signing in…':'Login'}<ArrowRight size={17}/></button><p className="center">Don’t have an account? <Link to="/register">Register here</Link></p></form></div>;
}

export function Register(){
  const{register}=useAuth();const nav=useNavigate();const params=new URLSearchParams(location.search);
  const[role,setRole]=useState(params.get('role')||'applicant');const[error,setError]=useState('');const[busy,setBusy]=useState(false);
  async function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setError('');const form=new FormData(event.currentTarget);try{const data=await register(Object.fromEntries(form.entries())as Record<string,string>);nav(`/verify-email?email=${encodeURIComponent(data.email)}${data.dev_verification_code?`&code=${data.dev_verification_code}`:''}`)}catch(reason){setError(reason instanceof Error?reason.message:'Registration failed')}finally{setBusy(false)}}
  return <div className="register-page"><Link to="/"><Logo/></Link><form className="auth-card wide" onSubmit={submit}><h2>Create your SmartHire account</h2><p>Choose your account type before continuing with Google.</p>{error&&<div className="alert error">{error}</div>}<div className="role-tabs"><button type="button" className={role==='applicant'?'active':''} onClick={()=>setRole('applicant')}>Applicant</button><button type="button" className={role==='employer'?'active':''} onClick={()=>setRole('employer')}>Employer</button></div><GoogleButton intent="register" role={role}/><input type="hidden" name="role" value={role}/><div className="form-grid"><label>Full name<input name="full_name" minLength={2} required/></label><label>Email<input name="email" type="email" required/></label>{role==='employer'&&<label>Company name<input name="company_name" required/></label>}<label>Password<input name="password" type="password" minLength={8} required/></label></div><button className="button full" disabled={busy}>{busy?'Creating…':'Create Account'}</button><p className="center">Already registered? <Link to="/login">Login</Link></p></form></div>;
}
