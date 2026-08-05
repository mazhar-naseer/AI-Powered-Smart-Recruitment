import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import {request,tokenStore} from './api'; import type{User}from'./types';
type Registration=User&{dev_verification_code?:string;verification_required:boolean};
type AuthData={access_token:string;refresh_token:string;user:User};
type Auth={user:User|null;loading:boolean;login:(e:string,p:string)=>Promise<User>;register:(v:Record<string,string>)=>Promise<Registration>;verifyEmail:(v:{email?:string;code?:string;token?:string})=>Promise<User>;updateUser:(user:User)=>void;logout:()=>Promise<void>};
const Context=createContext<Auth|null>(null);
export function AuthProvider({children}:{children:ReactNode}){const[user,setUser]=useState<User|null>(null);const[loading,setLoading]=useState(true);useEffect(()=>{request<User>('/auth/me').then(setUser).catch(()=>tokenStore.clear()).finally(()=>setLoading(false))},[]);
const acceptAuth=(data:AuthData)=>{tokenStore.set(data.access_token,data.refresh_token);setUser(data.user);return data.user};
const login=async(email:string,password:string)=>acceptAuth(await request<AuthData>('/auth/login',{method:'POST',auth:false,body:JSON.stringify({email,password})}));
const register=async(values:Record<string,string>)=>request<Registration>('/auth/register',{method:'POST',auth:false,body:JSON.stringify(values)});
const verifyEmail=async(values:{email?:string;code?:string;token?:string})=>acceptAuth(await request<AuthData>('/auth/verify-email',{method:'POST',auth:false,body:JSON.stringify(values)}));
const logout=async()=>{const refresh_token=localStorage.getItem('refresh_token');if(refresh_token)await request('/auth/logout',{method:'POST',auth:false,body:JSON.stringify({refresh_token})}).catch(()=>{});tokenStore.clear();setUser(null)};
return <Context.Provider value={{user,loading,login,register,verifyEmail,updateUser:setUser,logout}}>{children}</Context.Provider>}
export const useAuth=()=>{const value=useContext(Context);if(!value)throw new Error('AuthProvider missing');return value};
