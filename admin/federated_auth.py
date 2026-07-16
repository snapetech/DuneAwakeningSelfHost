#!/usr/bin/env python3
"""OIDC/Discord OAuth login primitives with signed DASH sessions."""

import base64
import hashlib
import hmac
import json
import pathlib
import re
import secrets
import threading
import time
import urllib.parse
import urllib.error
import urllib.request


MAX_HTTP_BYTES=1024*1024
JWT_DIGEST_INFO_SHA256=bytes.fromhex("3031300d060960864801650304020105000420")
SUBJECT_RE=re.compile(r"^[^\x00-\x1f]{1,512}$")

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise urllib.error.HTTPError(req.full_url,code,"federated-auth redirects are refused",headers,fp)

HTTP_OPENER=urllib.request.build_opener(NoRedirect)

def b64u(data): return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
def unb64u(value): return base64.urlsafe_b64decode(str(value)+"="*((4-len(str(value))%4)%4))

def origin(url):
    parsed=urllib.parse.urlparse(str(url));port=f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{(parsed.hostname or '').lower()}{port}"

def validate_endpoint(url,allowed_origins):
    parsed=urllib.parse.urlparse(str(url))
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("federated-auth endpoints must be credential-free HTTPS URLs")
    if origin(url) not in allowed_origins: raise ValueError("federated-auth endpoint origin is not allowlisted")
    return str(url)

def load_settings(environment):
    env=environment
    kind=str(env.get("DUNE_ADMIN_AUTH_PROVIDER") or "").strip().lower()
    if kind not in ("oidc","discord",""): raise ValueError("DUNE_ADMIN_AUTH_PROVIDER must be oidc or discord")
    issuer=str(env.get("DUNE_ADMIN_AUTH_ISSUER") or ("https://discord.com" if kind=="discord" else "")).rstrip("/")
    redirect_uri=str(env.get("DUNE_ADMIN_AUTH_REDIRECT_URI") or "").strip()
    if redirect_uri:
        parsed=urllib.parse.urlparse(redirect_uri)
        loopback=parsed.scheme=="http" and parsed.hostname in ("127.0.0.1","localhost","::1")
        if not ((parsed.scheme=="https" and parsed.hostname) or loopback) or parsed.fragment:
            raise ValueError("federated-auth redirect URI must be HTTPS or HTTP loopback")
    allowed={origin(issuer)} if issuer else set()
    allowed.update(origin(value.strip()) for value in str(env.get("DUNE_ADMIN_AUTH_ALLOWED_ORIGINS") or "").split(",") if value.strip())
    settings={
        "kind":kind,"issuer":issuer,"clientId":str(env.get("DUNE_ADMIN_AUTH_CLIENT_ID") or "").strip(),
        "redirectUri":redirect_uri,"scopes":str(env.get("DUNE_ADMIN_AUTH_SCOPES") or ("identify" if kind=="discord" else "openid profile email")).strip(),
        "allowedOrigins":allowed,"sessionSeconds":max(300,min(int(env.get("DUNE_ADMIN_AUTH_SESSION_SECONDS") or 28800),604800)),
        "cookieSecure":str(env.get("DUNE_ADMIN_AUTH_COOKIE_SECURE") or "true").lower() in ("1","true","yes","on"),
    }
    if kind=="discord":
        settings.update({"authorizationEndpoint":"https://discord.com/oauth2/authorize","tokenEndpoint":"https://discord.com/api/oauth2/token","userinfoEndpoint":"https://discord.com/api/v10/users/@me"})
        settings["allowedOrigins"].update({"https://discord.com"})
    return settings

def configured(settings,client_secret,session_secret,mapping_path):
    return bool(settings.get("kind") and settings.get("issuer") and settings.get("clientId") and settings.get("redirectUri") and client_secret and session_secret and pathlib.Path(mapping_path).is_file())

def load_subjects(path):
    document=json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(document,dict) or document.get("version")!=1 or not isinstance(document.get("subjects"),list): raise ValueError("admin auth subject map must be version 1")
    seen=set();rows=[]
    for raw in document["subjects"]:
        issuer=str(raw.get("issuer") or "").rstrip("/");subject=str(raw.get("subject") or "");local=str(raw.get("localUserId") or "").lower()
        if not issuer.startswith("https://") or not SUBJECT_RE.fullmatch(subject) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,63}",local): raise ValueError("invalid federated subject mapping")
        key=(issuer,subject)
        if key in seen: raise ValueError("duplicate federated issuer/subject mapping")
        seen.add(key);rows.append({"issuer":issuer,"subject":subject,"localUserId":local,"enabled":bool(raw.get("enabled",True)),"label":str(raw.get("label") or "")[:128]})
    return rows

def mapped_local_user(path,issuer,subject):
    matched=next((row for row in load_subjects(path) if row["issuer"]==str(issuer).rstrip("/") and hmac.compare_digest(row["subject"],str(subject)) and row["enabled"]),None)
    return matched["localUserId"] if matched else None

def sign_payload(payload,secret):
    body=b64u(json.dumps(payload,separators=(",",":"),sort_keys=True).encode());signature=b64u(hmac.new(secret.encode(),body.encode(),hashlib.sha256).digest());return body+"."+signature

def verify_payload(value,secret,kind,now=None):
    try: body,signature=str(value).split(".",1);expected=b64u(hmac.new(secret.encode(),body.encode(),hashlib.sha256).digest())
    except Exception as exc: raise PermissionError("invalid federated-auth cookie") from exc
    if not hmac.compare_digest(signature,expected): raise PermissionError("invalid federated-auth cookie signature")
    try: payload=json.loads(unb64u(body))
    except Exception as exc: raise PermissionError("invalid federated-auth cookie payload") from exc
    now=int(time.time() if now is None else now)
    if payload.get("kind")!=kind or int(payload.get("iat",0))>now+60 or int(payload.get("exp",0))<=now: raise PermissionError("expired or invalid federated-auth cookie")
    return payload

class ReplayCache:
    def __init__(self): self.lock=threading.Lock();self.used={}
    def consume(self,state,expires,now=None):
        now=int(time.time() if now is None else now)
        with self.lock:
            self.used={key:value for key,value in self.used.items() if value>now}
            if state in self.used: raise PermissionError("federated-auth state was already consumed")
            self.used[state]=int(expires)

def resolve_provider(settings,http_json):
    result=dict(settings)
    if result["kind"]=="oidc":
        discovery=validate_endpoint(result["issuer"]+"/.well-known/openid-configuration",result["allowedOrigins"])
        metadata=http_json(discovery)
        if str(metadata.get("issuer") or "").rstrip("/")!=result["issuer"]: raise PermissionError("OIDC discovery issuer mismatch")
        for source,target in (("authorization_endpoint","authorizationEndpoint"),("token_endpoint","tokenEndpoint"),("userinfo_endpoint","userinfoEndpoint"),("jwks_uri","jwksUri")):
            if source not in metadata and source=="userinfo_endpoint": continue
            result[target]=validate_endpoint(metadata.get(source),result["allowedOrigins"])
    for key in ("authorizationEndpoint","tokenEndpoint"):
        result[key]=validate_endpoint(result[key],result["allowedOrigins"])
    if result.get("userinfoEndpoint"): result["userinfoEndpoint"]=validate_endpoint(result["userinfoEndpoint"],result["allowedOrigins"])
    return result

def begin(settings,session_secret,http_json,now=None):
    now=int(time.time() if now is None else now);provider=resolve_provider(settings,http_json);state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48);challenge=b64u(hashlib.sha256(verifier.encode()).digest())
    flow={"kind":"flow","iat":now,"exp":now+600,"state":state,"nonce":nonce,"verifier":verifier,"provider":provider["kind"],"issuer":provider["issuer"]}
    query={"response_type":"code","client_id":provider["clientId"],"redirect_uri":provider["redirectUri"],"scope":provider["scopes"],"state":state,"code_challenge":challenge,"code_challenge_method":"S256"}
    if provider["kind"]=="oidc": query["nonce"]=nonce
    return {"url":provider["authorizationEndpoint"]+"?"+urllib.parse.urlencode(query),"flowCookie":sign_payload(flow,session_secret),"provider":provider}

def verify_rs256(token,jwks,issuer,client_id,nonce,now=None):
    parts=str(token).split(".")
    if len(parts)!=3: raise PermissionError("invalid OIDC ID token")
    header=json.loads(unb64u(parts[0]));claims=json.loads(unb64u(parts[1]));signature=unb64u(parts[2])
    if header.get("alg")!="RS256": raise PermissionError("only OIDC RS256 ID tokens are accepted")
    keys=[key for key in (jwks.get("keys") or []) if key.get("kty")=="RSA" and key.get("kid")==header.get("kid") and key.get("use","sig")=="sig"]
    if len(keys)!=1: raise PermissionError("OIDC signing key was not uniquely identified")
    key=keys[0];n=int.from_bytes(unb64u(key["n"]),"big");e=int.from_bytes(unb64u(key["e"]),"big");size=(n.bit_length()+7)//8
    encoded=pow(int.from_bytes(signature,"big"),e,n).to_bytes(size,"big");digest=hashlib.sha256((parts[0]+"."+parts[1]).encode()).digest();expected=b"\x00\x01"+b"\xff"*(size-len(JWT_DIGEST_INFO_SHA256)-len(digest)-3)+b"\x00"+JWT_DIGEST_INFO_SHA256+digest
    if not hmac.compare_digest(encoded,expected): raise PermissionError("OIDC ID token signature verification failed")
    now=int(time.time() if now is None else now);aud=claims.get("aud");audiences=[aud] if isinstance(aud,str) else aud if isinstance(aud,list) else []
    if str(claims.get("iss") or "").rstrip("/")!=str(issuer).rstrip("/") or client_id not in audiences: raise PermissionError("OIDC issuer or audience mismatch")
    if len(audiences)>1 and claims.get("azp")!=client_id: raise PermissionError("OIDC authorized-party mismatch")
    if int(claims.get("exp",0))<=now-60 or int(claims.get("iat",0))>now+60 or not hmac.compare_digest(str(claims.get("nonce") or ""),str(nonce)): raise PermissionError("OIDC token time or nonce validation failed")
    if not SUBJECT_RE.fullmatch(str(claims.get("sub") or "")): raise PermissionError("OIDC subject is invalid")
    return claims

def complete(settings,flow_cookie,state,code,session_secret,client_secret,http_json,post_form,replay_cache,now=None):
    now=int(time.time() if now is None else now);flow=verify_payload(flow_cookie,session_secret,"flow",now)
    if not state or not hmac.compare_digest(str(state),str(flow["state"])): raise PermissionError("federated-auth state mismatch")
    replay_cache.consume(flow["state"],flow["exp"],now)
    if not code or len(str(code))>4096: raise PermissionError("federated-auth code is missing or oversized")
    provider=resolve_provider(settings,http_json)
    if flow.get("provider")!=provider["kind"] or str(flow.get("issuer") or "").rstrip("/")!=provider["issuer"]: raise PermissionError("federated-auth provider changed during login")
    form={"grant_type":"authorization_code","code":str(code),"redirect_uri":provider["redirectUri"],"client_id":provider["clientId"],"client_secret":client_secret,"code_verifier":flow["verifier"]};tokens=post_form(provider["tokenEndpoint"],form)
    access_token=str(tokens.get("access_token") or "")
    if provider["kind"]=="oidc":
        id_token=str(tokens.get("id_token") or "");jwks=http_json(validate_endpoint(provider["jwksUri"],provider["allowedOrigins"]));claims=verify_rs256(id_token,jwks,provider["issuer"],provider["clientId"],flow["nonce"],now);subject=str(claims["sub"]);display=str(claims.get("name") or claims.get("preferred_username") or subject)[:128]
    else:
        if not access_token or str(tokens.get("token_type") or "").lower()!="bearer": raise PermissionError("Discord token response omitted a bearer access_token")
        user=http_json(provider["userinfoEndpoint"],{"Authorization":"Bearer "+access_token});subject=str(user.get("id") or "");display=str(user.get("global_name") or user.get("username") or subject)[:128]
        if not re.fullmatch(r"[0-9]{5,32}",subject): raise PermissionError("Discord subject is invalid")
    session={"kind":"session","iat":now,"exp":now+provider["sessionSeconds"],"issuer":provider["issuer"],"subject":subject,"sid":secrets.token_urlsafe(18)}
    return {"issuer":provider["issuer"],"subject":subject,"displayName":display,"sessionCookie":sign_payload(session,session_secret),"expires":session["exp"]}

def http_json(url,headers=None):
    request=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"DASH-federated-auth/1",**(headers or {})})
    with HTTP_OPENER.open(request,timeout=8) as response:
        raw=response.read(MAX_HTTP_BYTES+1)
    if len(raw)>MAX_HTTP_BYTES: raise ValueError("federated-auth HTTP response exceeded limit")
    value=json.loads(raw)
    if not isinstance(value,dict): raise ValueError("federated-auth HTTP response must be a JSON object")
    return value

def post_form(url,form):
    data=urllib.parse.urlencode(form).encode();request=urllib.request.Request(url,data=data,headers={"Accept":"application/json","Content-Type":"application/x-www-form-urlencoded","User-Agent":"DASH-federated-auth/1"},method="POST")
    with HTTP_OPENER.open(request,timeout=8) as response: raw=response.read(MAX_HTTP_BYTES+1)
    if len(raw)>MAX_HTTP_BYTES: raise ValueError("federated-auth token response exceeded limit")
    value=json.loads(raw)
    if not isinstance(value,dict): raise ValueError("federated-auth token response must be a JSON object")
    return value
