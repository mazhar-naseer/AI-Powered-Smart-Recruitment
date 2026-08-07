import type{User}from'./types';

export function homeFor(user:User|null|undefined){
  if(!user)return '/';
  if(user.role==='admin')return '/admin';
  if(user.role==='employer')return '/employer';
  return '/applicant/jobs';
}
