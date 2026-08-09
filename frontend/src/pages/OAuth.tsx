import{useEffect,useState}from'react';
import{useNavigate}from'react-router-dom';
import{API_BASE,request}from'../api';
import{useAuth}from'../auth';
import{Logo,Spinner}from'../components';
import{homeFor}from'../navigation';

/** Provider config is static server-side, so a resolved lookup is shared rather
 *  than refetched by every consumer. Failures are not cached — a transient error
 *  would otherwise hide Google for the rest of the page session. */
let providerLookup:Promise<boolean>|undefined;
function googleEnabled(){
  providerLookup??=request<any>('/auth/oauth/providers',{auth:false}).then(data=>Boolean(data.google?.enabled)).catch(()=>{providerLookup=undefined;return false});
  return providerLookup;
}
export function useGoogleEnabled(){
  const[enabled,setEnabled]=useState<boolean>();
  useEffect(()=>{let active=true;void googleEnabled().then(value=>{if(active)setEnabled(value)});return()=>{active=false}},[]);
  return enabled;
}

export function GoogleButton({intent,role='applicant'}:{intent:'login'|'register';role?:string}){
  const enabled=useGoogleEnabled();
  if(!enabled)return null;
  const query=new URLSearchParams({intent,role,return_to:window.location.origin});
  return <><div className="auth-divider"><span>or continue with</span></div><a className="google-auth-button" href={`${API_BASE}/auth/oauth/google/start?${query}`}><span className="google-g">G</span><strong>Continue with Google</strong></a></>;
}

export function OAuthCallback(){
  const{exchangeOAuth}=useAuth();const nav=useNavigate();const[error,setError]=useState('');
  useEffect(()=>{const params=new URLSearchParams(location.search);const code=params.get('code');const providerError=params.get('error');if(providerError){setError(providerError);return}if(!code){setError('Google did not return a login code.');return}exchangeOAuth(code).then(user=>nav(homeFor(user),{replace:true})).catch(reason=>setError(reason instanceof Error?reason.message:'Google sign-in failed'))},[]);
  if(!error)return <div className="oauth-result"><Spinner/><h2>Completing Google sign-in…</h2><p>Please keep this window open.</p></div>;
  return <div className="register-page"><a href="/"><Logo/></a><section className="auth-card oauth-error"><span className="google-g">G</span><h2>Google sign-in wasn’t completed</h2><div className="alert error">{error}</div><a className="button full" href="/login">Return to login</a></section></div>;
}
