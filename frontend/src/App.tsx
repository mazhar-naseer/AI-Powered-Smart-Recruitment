import{Navigate,Route,Routes}from'react-router-dom';
import{useAuth}from'./auth';
import{AdminShell,Shell,Spinner}from'./components';
import{AdminLogin,Landing,Login,Register,VerifyEmail}from'./pages/Public';
import{EmployerDashboard,EmployerJobs,JobForm,RankedApplicants}from'./pages/Employer';
import{ApplicantApplications,ApplicantJobs,JobDetails}from'./pages/Applicant';
import{AdminDashboard,AdminIntelligence,AdminJobApplications,AdminJobs,AdminOperations,AdminUsers}from'./pages/Admin';
import{Profile}from'./pages/Profile';
import{EmployerIntelligence}from'./pages/Intelligence';
import{AcceptTeamInvitation,CandidateWorkspace,HiringPipeline,NotificationCenter,PipelineSettings,RecruiterTeam}from'./pages/ATS';
import type{Role}from'./types';
import{homeFor}from'./navigation';

function Home(){const{user,loading}=useAuth();if(loading)return <Spinner/>;return <Navigate to={homeFor(user)} replace/>}
function PublicOnly({children}:{children:React.ReactNode}){const{user,loading}=useAuth();if(loading)return <Spinner/>;if(user)return <Navigate to={homeFor(user)} replace/>;return children}
function Protected({roles,children}:{roles?:Role[];children:React.ReactNode}){const{user,loading}=useAuth();if(loading)return <Spinner/>;if(!user)return <Navigate to="/login" replace/>;if(roles&&!roles.includes(user.role))return <Home/>;return <Shell>{children}</Shell>}
function AdminProtected({children}:{children:React.ReactNode}){const{user,loading}=useAuth();if(loading)return <Spinner/>;if(!user)return <Navigate to="/admin/login" replace/>;if(user.role!=='admin')return <Home/>;return <AdminShell>{children}</AdminShell>}
function AccountProtected({children}:{children:React.ReactNode}){const{user,loading}=useAuth();if(loading)return <Spinner/>;if(!user)return <Navigate to="/login" replace/>;return user.role==='admin'?<AdminShell>{children}</AdminShell>:<Shell>{children}</Shell>}

export default function App(){return <Routes>
  <Route path="/" element={<PublicOnly><Landing/></PublicOnly>}/><Route path="/login" element={<PublicOnly><Login/></PublicOnly>}/><Route path="/admin/login" element={<PublicOnly><AdminLogin/></PublicOnly>}/><Route path="/register" element={<PublicOnly><Register/></PublicOnly>}/><Route path="/verify-email" element={<PublicOnly><VerifyEmail/></PublicOnly>}/><Route path="/home" element={<Home/>}/>
  <Route path="/employer" element={<Protected roles={['employer']}><EmployerDashboard/></Protected>}/><Route path="/employer/jobs" element={<Protected roles={['employer']}><EmployerJobs/></Protected>}/><Route path="/employer/jobs/new" element={<Protected roles={['employer']}><JobForm/></Protected>}/><Route path="/employer/jobs/:id/edit" element={<Protected roles={['employer']}><JobForm/></Protected>}/><Route path="/employer/jobs/:id/applications" element={<Protected roles={['employer']}><RankedApplicants/></Protected>}/>
  <Route path="/employer/intelligence" element={<Protected roles={['employer']}><EmployerIntelligence/></Protected>}/>
  <Route path="/employer/team" element={<Protected roles={['employer']}><RecruiterTeam/></Protected>}/><Route path="/employer/pipeline" element={<Protected roles={['employer']}><HiringPipeline/></Protected>}/><Route path="/employer/pipeline/settings" element={<Protected roles={['employer']}><PipelineSettings/></Protected>}/><Route path="/employer/candidates/:id" element={<Protected roles={['employer']}><CandidateWorkspace/></Protected>}/>
  <Route path="/team/invitations/:token" element={<Protected roles={['employer']}><AcceptTeamInvitation/></Protected>}/>
  <Route path="/applicant/jobs" element={<Protected roles={['applicant']}><ApplicantJobs/></Protected>}/><Route path="/applicant/jobs/:id" element={<Protected roles={['applicant']}><JobDetails/></Protected>}/><Route path="/applicant/applications" element={<Protected roles={['applicant']}><ApplicantApplications/></Protected>}/>
  <Route path="/admin" element={<AdminProtected><AdminDashboard/></AdminProtected>}/><Route path="/admin/users" element={<AdminProtected><AdminUsers/></AdminProtected>}/><Route path="/admin/jobs" element={<AdminProtected><AdminJobs/></AdminProtected>}/><Route path="/admin/jobs/:id/applications" element={<AdminProtected><AdminJobApplications/></AdminProtected>}/><Route path="/admin/intelligence" element={<AdminProtected><AdminIntelligence/></AdminProtected>}/>
  <Route path="/admin/operations" element={<AdminProtected><AdminOperations/></AdminProtected>}/>
  <Route path="/notifications" element={<AccountProtected><NotificationCenter/></AccountProtected>}/><Route path="/profile" element={<Protected><Profile/></Protected>}/><Route path="*" element={<Home/>}/>
</Routes>}
