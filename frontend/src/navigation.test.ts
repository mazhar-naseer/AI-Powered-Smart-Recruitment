import{describe,expect,it}from'vitest';
import{homeFor}from'./navigation';
import type{User}from'./types';

const user=(role:User['role'])=>({role} as User);

describe('homeFor',()=>{
  it('keeps public visitors on the landing page',()=>expect(homeFor(null)).toBe('/'));
  it('routes applicants to the job board',()=>expect(homeFor(user('applicant'))).toBe('/applicant/jobs'));
  it('routes employers to their dashboard',()=>expect(homeFor(user('employer'))).toBe('/employer'));
  it('routes administrators to the Control Center',()=>expect(homeFor(user('admin'))).toBe('/admin'));
});
