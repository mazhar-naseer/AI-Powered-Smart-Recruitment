import{Navigate,Route,Routes}from'react-router-dom';
import{useAuth}from'./auth';
import{AdminShell,Shell,Spinner}from'./components';
import{AdminLogin,Landing,Login,Register,VerifyEmail}from'./pages/Public';
import{EmployerDashboard,EmployerJobs,JobForm,RankedApplicants}from'./pages/Employer';
import{ApplicantApplications,ApplicantJobs,JobDetails}from'./pages/Applicant';
import{AdminDashboard,AdminJobs,AdminUsers}from'./pages/Admin';
import{Profile}from'./pages/Profile';
import type{Role}from'./types';

function Home(){const{user}=useAuth();return <Navigate to={user?.role==='employer'?'/employer':user?.role==='admin'?'/admin':'/applicant/jobs'} replace/>}
function Protected({roles,children}:{roles?:Role[];children:React.ReactNode}){const{user,loading}=useAuth();if(loading)return <Spinner/>;if(!user)return <Navigate to="/login" replace/>;if(roles&&!roles.includes(user.role))return <Home/>;return <Shell>{children}</Shell>}
function AdminProtected({children}:{children:React.ReactNode}){const{user,loading}=useAuth();if(loading)return <Spinner/>;if(!user)return <Navigate to="/admin/login" replace/>;if(user.role!=='admin')return <Home/>;return <AdminShell>{children}</AdminShell>}

export default function App(){return <Routes>
  <Route path="/" element={<Landing/>}/><Route path="/login" element={<Login/>}/><Route path="/admin/login" element={<AdminLogin/>}/><Route path="/register" element={<Register/>}/><Route path="/verify-email" element={<VerifyEmail/>}/><Route path="/home" element={<Home/>}/>
  <Route path="/employer" element={<Protected roles={['employer']}><EmployerDashboard/></Protected>}/><Route path="/employer/jobs" element={<Protected roles={['employer']}><EmployerJobs/></Protected>}/><Route path="/employer/jobs/new" element={<Protected roles={['employer']}><JobForm/></Protected>}/><Route path="/employer/jobs/:id/edit" element={<Protected roles={['employer']}><JobForm/></Protected>}/><Route path="/employer/jobs/:id/applications" element={<Protected roles={['employer']}><RankedApplicants/></Protected>}/>
  <Route path="/applicant/jobs" element={<Protected roles={['applicant']}><ApplicantJobs/></Protected>}/><Route path="/applicant/jobs/:id" element={<Protected roles={['applicant']}><JobDetails/></Protected>}/><Route path="/applicant/applications" element={<Protected roles={['applicant']}><ApplicantApplications/></Protected>}/>
  <Route path="/admin" element={<AdminProtected><AdminDashboard/></AdminProtected>}/><Route path="/admin/users" element={<AdminProtected><AdminUsers/></AdminProtected>}/><Route path="/admin/jobs" element={<AdminProtected><AdminJobs/></AdminProtected>}/>
  <Route path="/profile" element={<Protected><Profile/></Protected>}/><Route path="*" element={<Navigate to="/"/>}/>
</Routes>}
