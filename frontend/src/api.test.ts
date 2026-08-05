import{describe,expect,it,beforeEach}from'vitest';import{tokenStore}from'./api';
describe('tokenStore',()=>{beforeEach(()=>{localStorage.clear();tokenStore.clear()});it('stores and clears authentication tokens',()=>{tokenStore.set('access','refresh');expect(tokenStore.get()).toBe('access');expect(localStorage.getItem('refresh_token')).toBe('refresh');tokenStore.clear();expect(tokenStore.get()).toBeNull()})});

