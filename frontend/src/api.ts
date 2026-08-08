const BASE=import.meta.env.VITE_API_URL||'/api/v1';
export const API_BASE=BASE;
type Options=RequestInit&{auth?:boolean};
let accessToken=localStorage.getItem('access_token');
export const tokenStore={get:()=>accessToken,set:(access:string,refresh:string)=>{accessToken=access;localStorage.setItem('access_token',access);localStorage.setItem('refresh_token',refresh)},clear:()=>{accessToken=null;localStorage.removeItem('access_token');localStorage.removeItem('refresh_token')}};
function errorMessage(body:any):string{
  if(typeof body?.detail==='string')return body.detail;
  const details=body?.error?.details;
  if(Array.isArray(details)&&details.length){
    return details.map((item:any)=>{
      const field=String(item?.loc?.[item.loc.length-1]||'field').replaceAll('_',' ');
      return `${field.charAt(0).toUpperCase()+field.slice(1)}: ${item?.msg||'Invalid value'}`
    }).join(' · ')
  }
  return body?.message||'Request failed'
}
export async function request<T>(path:string,options:Options={}):Promise<T>{
  const headers=new Headers(options.headers); if(!(options.body instanceof FormData))headers.set('Content-Type','application/json'); if(options.auth!==false&&accessToken)headers.set('Authorization',`Bearer ${accessToken}`);
  let response=await fetch(`${BASE}${path}`,{...options,headers});
  if(response.status===401&&localStorage.getItem('refresh_token')&&!path.includes('/auth/refresh')){
    const refresh=await fetch(`${BASE}/auth/refresh`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh_token:localStorage.getItem('refresh_token')})});
    if(refresh.ok){const body=await refresh.json();tokenStore.set(body.data.access_token,body.data.refresh_token);headers.set('Authorization',`Bearer ${body.data.access_token}`);response=await fetch(`${BASE}${path}`,{...options,headers});}else tokenStore.clear();
  }
  const contentType=response.headers.get('content-type')||''; const body=contentType.includes('json')?await response.json():await response.blob();
  if(!response.ok)throw new Error(errorMessage(body));
  // A binary route — resume, avatar, export — answers with the file itself and
  // has no envelope to unwrap. Reaching for `.data` on a Blob yields undefined,
  // so the caller would get nothing back and no error explaining why.
  return (body instanceof Blob?body:body.data) as T;
}
