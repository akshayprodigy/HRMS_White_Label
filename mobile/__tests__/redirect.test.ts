import { decideRedirect } from '../src/auth/redirect';

describe('decideRedirect', () => {
  it('root while logged out goes to login without remembering anything', () => {
    expect(decideRedirect({ loggedIn: false, path: '/', pending: null })).toEqual({ href: '/login', pending: null });
  });
  it('a deep link while logged out goes to login and is remembered', () => {
    expect(decideRedirect({ loggedIn: false, path: '/leave', pending: null })).toEqual({ href: '/login', pending: '/leave' });
  });
  it('keeps the remembered link when the login screen itself is re-resolved', () => {
    expect(decideRedirect({ loggedIn: false, path: '/login', pending: '/leave' })).toEqual({ href: '/login', pending: '/leave' });
  });
  it('after login returns to the intended route, else home', () => {
    expect(decideRedirect({ loggedIn: true, path: '/', pending: '/leave' })).toEqual({ href: '/leave', pending: null });
    expect(decideRedirect({ loggedIn: true, path: '/', pending: null })).toEqual({ href: '/home', pending: null });
    expect(decideRedirect({ loggedIn: true, path: '/login', pending: null })).toEqual({ href: '/home', pending: null });
  });
});
