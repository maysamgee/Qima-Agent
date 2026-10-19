const domain = import.meta.env.VITE_COGNITO_DOMAIN;
const client = import.meta.env.VITE_COGNITO_CLIENT_ID;
function base64url(buffer: ArrayBuffer) { return btoa(String.fromCharCode(...new Uint8Array(buffer))).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', ''); }
export async function signIn() {
  if (!domain || !client) throw new Error('Configure the Cognito domain and client ID in the frontend environment.');
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)).buffer);
  const state = crypto.randomUUID();
  sessionStorage.setItem('pkce_verifier', verifier); sessionStorage.setItem('oauth_state', state);
  const challenge = base64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));
  const params = new URLSearchParams({response_type: 'code',client_id: client,redirect_uri: `${location.origin}/callback`,scope: 'openid email profile',state,code_challenge: challenge,code_challenge_method: 'S256'});
  location.assign(`${domain}/oauth2/authorize?${params}`);
}
let callbackPromise: Promise<void> | undefined;
export function finishSignIn() {
  callbackPromise ??= (async () => {
    const params = new URLSearchParams(location.search);
    const expected = sessionStorage.getItem('oauth_state');
    const verifier = sessionStorage.getItem('pkce_verifier');
    if (!expected || params.get('state') !== expected || !verifier || !params.get('code')) throw new Error('Sign-in state is invalid. Please sign in again.');
    sessionStorage.removeItem('oauth_state'); sessionStorage.removeItem('pkce_verifier');
    const response = await fetch(`${domain}/oauth2/token`, {method: 'POST',headers: {'Content-Type': 'application/x-www-form-urlencoded'},body: new URLSearchParams({grant_type:'authorization_code',client_id:client,redirect_uri:`${location.origin}/callback`,code:params.get('code')!,code_verifier:verifier})});
    if (!response.ok) throw new Error('Sign-in could not be completed.');
    const tokens = await response.json(); sessionStorage.setItem('access_token', tokens.access_token);
  })();
  return callbackPromise;
}
