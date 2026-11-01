// The only public runtime operation reads one already verified static JSON document.
const securityHeaders={
  'X-Content-Type-Options':'nosniff',
  'Referrer-Policy':'no-referrer',
  'Cache-Control':'public, max-age=15',
  'Cross-Origin-Resource-Policy':'same-origin',
  'X-Frame-Options':'DENY',
  'Strict-Transport-Security':'max-age=31536000',
  'Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
};
export async function onRequest(context: {request:Request;env:{SAMO_SNAPSHOTS:{get:(key:string,options?:{cacheTtl:number})=>Promise<string|null>}}}) {
  if(!['GET','HEAD'].includes(context.request.method))return new Response('Method not allowed',{status:405,headers:{...securityHeaders,Allow:'GET, HEAD'}});
  const value=await context.env.SAMO_SNAPSHOTS.get('snapshot',{cacheTtl:30});
  if(!value)return new Response('No verified ecosystem observation published yet',{status:503,headers:securityHeaders});
  return new Response(context.request.method==='HEAD'?null:value,{headers:{...securityHeaders,'Content-Type':'application/json; charset=utf-8'}});
}
