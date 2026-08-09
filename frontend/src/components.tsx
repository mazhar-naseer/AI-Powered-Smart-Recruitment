import{useEffect,useRef,useState,type ReactNode,type RefObject}from'react';
import{Link,NavLink,useLocation,useNavigate}from'react-router-dom';
import{Activity,Bell,BrainCircuit,BriefcaseBusiness,CircleAlert,CircleCheckBig,CircleDashed,CircleMinus,CreditCard,Database,LayoutDashboard,LogOut,Menu,Settings,ShieldCheck,ThumbsUp,Trophy,Users,FileText,UserCircle,Search,Workflow,X,type LucideIcon}from'lucide-react';
import{useAuth}from'./auth';
import{homeFor}from'./navigation';
import{request}from'./api';

function WorkspaceSwitcher(){const[items,setItems]=useState<any[]>();useEffect(()=>{request<any[]>('/workspaces').then(setItems)},[]);if(!items?.length)return null;const active=items.find(item=>item.active)?.organization.id||items[0].organization.id;async function change(id:string){await request('/workspace/switch',{method:'POST',body:JSON.stringify({organization_id:id})});window.location.assign('/employer')}return <label className="workspace-switcher"><span>WORKSPACE</span><select value={active} onChange={e=>change(e.target.value)}>{items.map(item=><option value={item.organization.id} key={item.organization.id}>{item.organization.name} · {item.role}</option>)}</select></label>}

export function useWorkspacePermissions(enabled=true){const[permissions,setPermissions]=useState<string[]>();useEffect(()=>{if(enabled)request<any>('/workspace').then(data=>setPermissions(data.membership.permissions)).catch(()=>setPermissions([]));else setPermissions([])},[enabled]);return permissions}

export function Logo(){const{user}=useAuth();const nav=useNavigate();const openHome=()=>nav(homeFor(user));return <div className="logo logo-link" role="link" tabIndex={0} aria-label="SmartHire home" onClick={openHome} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openHome()}}}><span className="logo-mark">S</span><span>SmartHire</span></div>}
export function Spinner(){return <div className="spinner" role="status" aria-label="Loading"/>}
export function Empty({title,body,icon:Icon=Search}:{title:string;body:string;icon?:LucideIcon}){return <div className="empty"><Icon size={34}/><h3>{title}</h3><p>{body}</p></div>}

/** Fit bands sit on the backend's own recommendation cut-points — see
 *  backend/app/resume_processing.py: strong_match at >=75, review at >=50,
 *  weak_match below. The extra 85 and 60 edges only add granularity inside
 *  those bands, so this label can never contradict a stored ai_recommendation. */
export type FitTier={label:string;tone:string;hint:string;icon:LucideIcon};
export function fitTier(score:number|null|undefined):FitTier{
  if(score==null)return{label:'Not scored',tone:'grey',hint:'Awaiting resume analysis.',icon:CircleDashed};
  if(score>=85)return{label:'Excellent fit',tone:'green',hint:'Meets nearly all job requirements.',icon:Trophy};
  if(score>=75)return{label:'Strong fit',tone:'green',hint:'Covers the core requirements well.',icon:CircleCheckBig};
  if(score>=60)return{label:'Good fit',tone:'blue',hint:'Solid overlap with some gaps.',icon:ThumbsUp};
  if(score>=50)return{label:'Fair fit',tone:'orange',hint:'Partial match — worth a closer read.',icon:CircleAlert};
  return{label:'Weak fit',tone:'red',hint:'Limited overlap with the requirements.',icon:CircleMinus};
}

/** Percentage as an animated donut. The ring is decorative — the adjacent
 *  number and fit label carry the value for assistive tech. */
export function ScoreRing({value,tone,caption}:{value:number|null|undefined;tone:string;caption?:string}){
  const radius=18,circumference=2*Math.PI*radius;
  const filled=value==null?0:Math.max(0,Math.min(100,value));
  return <div className={`score-ring tone-${tone}`}>
    <svg viewBox="0 0 44 44" aria-hidden="true" focusable="false">
      <circle className="ring-track" cx="22" cy="22" r={radius}/>
      <circle className="ring-value" cx="22" cy="22" r={radius} strokeDasharray={circumference} strokeDashoffset={circumference-circumference*filled/100}/>
    </svg>
    <div><strong>{value==null?'—':<>{Math.round(value)}<i>%</i></>}</strong>{caption&&<small>{caption}</small>}</div>
  </div>
}

const FOCUSABLE='a[href],button:not([disabled]),select,input,[tabindex]:not([tabindex="-1"])';
// Drawer state for the ≤900px shells. The nav itself is unchanged — this only
// governs whether the existing <aside> is slid into view, so every link, route,
// and permission filter behaves exactly as it does on desktop.
function useNavDrawer(){
  const[open,setOpen]=useState(false);
  const{pathname}=useLocation();
  const drawer=useRef<HTMLElement>(null);
  const toggle=useRef<HTMLButtonElement>(null);
  const wasOpen=useRef(false);
  useEffect(()=>{setOpen(false)},[pathname]);
  useEffect(()=>{
    // Returning focus to the hamburger is only correct if this close follows an
    // open we actually handled, otherwise the first render would steal focus.
    if(!open){if(wasOpen.current){wasOpen.current=false;toggle.current?.focus()}return}
    wasOpen.current=true;
    const{body}=document;const previousOverflow=body.style.overflow;body.style.overflow='hidden';
    drawer.current?.focus();
    const close=()=>setOpen(false);
    // Crossing back above the breakpoint hides the drawer in CSS, so the state
    // has to follow or the body would stay scroll-locked on a desktop layout.
    const wide=window.matchMedia('(min-width:901px)');
    function onKeyDown(event:KeyboardEvent){
      if(event.key==='Escape'){event.preventDefault();close();return}
      if(event.key!=='Tab'||!drawer.current)return;
      const items=[...drawer.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(item=>item.offsetParent!==null);
      if(!items.length)return;
      const first=items[0],last=items[items.length-1],active=document.activeElement;
      if(event.shiftKey&&(active===first||active===drawer.current)){event.preventDefault();last.focus()}
      else if(!event.shiftKey&&active===last){event.preventDefault();first.focus()}
    }
    document.addEventListener('keydown',onKeyDown);wide.addEventListener('change',close);
    return()=>{document.removeEventListener('keydown',onKeyDown);wide.removeEventListener('change',close);body.style.overflow=previousOverflow}
  },[open]);
  return{open,setOpen,drawer,toggle,pathname}
}
/** NavLink treats a parent path as active for every child route, so
 *  /employer/jobs/new lights up both "My Jobs" and "Post a Job". Only the
 *  deepest link the URL actually sits under wins, which still keeps "My Jobs"
 *  lit on /employer/jobs/:id/edit where no deeper link exists. */
function activeLink(pathname:string,paths:string[]){
  return paths.reduce((best,path)=>(pathname===path||pathname.startsWith(`${path}/`))&&path.length>best.length?path:best,'');
}
function NavToggle({open,setOpen,toggle}:{open:boolean;setOpen:(value:boolean)=>void;toggle:RefObject<HTMLButtonElement>}){
  return <button ref={toggle} className="nav-toggle" aria-label={open?'Close navigation':'Open navigation'} aria-expanded={open} aria-controls="shell-nav" onClick={()=>setOpen(!open)}>{open?<X size={20}/>:<Menu size={20}/>}</button>
}

export function Shell({children}:{children:ReactNode}){
  const{user,logout}=useAuth();const nav=useNavigate();const permissions=useWorkspacePermissions(user?.role==='employer');const{open,setOpen,drawer,toggle,pathname}=useNavDrawer();if(!user)return null;
  const employerLinks=([['/employer','Dashboard',LayoutDashboard],['/employer/jobs','My Jobs',BriefcaseBusiness,'analytics.view'],['/employer/jobs/new','Post a Job',FileText,'jobs.manage'],['/employer/pipeline','Hiring Pipeline',Workflow,'analytics.view'],['/employer/team','Recruiter Team',Users,'analytics.view'],['/employer/intelligence','AI Scorecards',BrainCircuit,'jobs.manage'],['/employer/settings','Workspace & Billing',CreditCard,'organization.manage']] as [string,string,LucideIcon,string?][]).filter(([, , ,permission])=>!permission||permissions?.includes(permission)).map(([to,label,Icon])=>[to,label,Icon] as [string,string,LucideIcon]);
  const links:[string,string,LucideIcon][]=user.role==='employer'?employerLinks:user.role==='applicant'?[['/applicant/jobs','Job Board',BriefcaseBusiness],['/applicant/applications','My Applications',FileText]]:[['/admin','System Dashboard',LayoutDashboard],['/admin/users','User Management',Users],['/admin/jobs','Job Postings',BriefcaseBusiness]];
  const active=activeLink(pathname,[...links.map(([to])=>to),'/notifications','/profile']);
  // The className *function* form is required: NavLink appends its own "active"
  // to a string className, which is exactly the behaviour being overridden here.
  return <div className={`app-shell ${user.role==='employer'&&permissions&&!permissions.includes('candidates.manage')?'workspace-readonly':''}`}><div className={`nav-backdrop ${open?'open':''}`} aria-hidden="true" onClick={()=>setOpen(false)}/><aside ref={drawer} id="shell-nav" tabIndex={-1} className={open?'open':''}><Logo/>{user.role==='employer'&&<WorkspaceSwitcher/>}<nav>{links.map(([to,label,Icon])=><NavLink key={String(to)} to={String(to)} className={()=>active===to?'active':''}><Icon size={18}/>{String(label)}</NavLink>)}<NavLink to="/notifications" className={()=>active==='/notifications'?'active':''}><Bell size={18}/>Notifications</NavLink><NavLink to="/profile" className={()=>active==='/profile'?'active':''}><UserCircle size={18}/>Profile</NavLink></nav><button className="logout" onClick={async()=>{await logout();nav('/login')}}><LogOut size={18}/>Logout</button></aside><main><header className="topbar"><NavToggle open={open} setOpen={setOpen} toggle={toggle}/><div className="topbar-brand"><Logo/></div><div className="topbar-greeting"><strong>Welcome back, {user.full_name.split(' ')[0]}!</strong><small>Here’s what’s happening today.</small></div><div className="account"><ShieldCheck size={18}/><span>{user.role}</span></div></header><div className="content">{children}</div></main></div>
}

export function AdminShell({children}:{children:ReactNode}){
  const{user,logout}=useAuth();const nav=useNavigate();const{open,setOpen,drawer,toggle,pathname}=useNavDrawer();if(!user)return null;
  const links:[string,string,LucideIcon][]=[['/admin','Command Center',Activity],['/admin/users','Identity & Access',Users],['/admin/jobs','Content Control',BriefcaseBusiness],['/admin/intelligence','Intelligence Monitor',Database],['/admin/operations','Operations & Audit',Settings],['/admin/saas','SaaS Accounts',CreditCard],['/admin/saas/requests','Plan Requests',Bell],['/admin/governance','Configuration',Settings],['/notifications','Notifications',Bell]];
  const active=activeLink(pathname,links.map(([to])=>to));
  return <div className="admin-shell"><div className={`nav-backdrop ${open?'open':''}`} aria-hidden="true" onClick={()=>setOpen(false)}/><aside ref={drawer} id="shell-nav" tabIndex={-1} className={`admin-rail ${open?'open':''}`}><Link className="admin-brand" to="/admin" aria-label="Admin Control Center home"><span><ShieldCheck/></span><div><strong>SmartHire</strong><small>CONTROL CENTER</small></div></Link><div className="admin-environment"><i/>PRODUCTION ENVIRONMENT</div><nav>{links.map(([to,label,Icon])=><NavLink key={to} to={to} className={()=>active===to?'active':''}><Icon size={18}/><span>{label}</span></NavLink>)}</nav><div className="admin-operator"><div className="admin-avatar">{user.full_name.slice(0,2).toUpperCase()}</div><div><strong>{user.full_name}</strong><small>Platform administrator</small></div></div><button className="admin-logout" onClick={async()=>{await logout();nav('/admin/login')}}><LogOut size={17}/>Secure sign out</button></aside><main><header className="admin-topbar"><NavToggle open={open} setOpen={setOpen} toggle={toggle}/><div><span>ADMINISTRATION</span><strong>Platform Operations</strong></div><div className="admin-health"><i/>All systems operational</div></header><div className="admin-content">{children}</div></main></div>
}

export function Stat({label,value,accent='blue',icon:Icon=BriefcaseBusiness}:{label:string;value:string|number;accent?:string;icon?:LucideIcon}){return <div className={`stat ${accent}`}><div className="stat-icon"><Icon size={20}/></div><div><span>{label}</span><strong>{value}</strong></div></div>}
export function Badge({children,tone='green'}:{children:ReactNode;tone?:string}){return <span className={`badge ${tone}`}>{children}</span>}
