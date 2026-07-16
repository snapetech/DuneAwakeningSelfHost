#!/usr/bin/env python3
import importlib.util,json,pathlib,tempfile,time,unittest
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding,rsa

ROOT=pathlib.Path(__file__).resolve().parents[1];SPEC=importlib.util.spec_from_file_location("federated_auth",ROOT/"admin"/"federated_auth.py");AUTH=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(AUTH)

class FederatedAuthTests(unittest.TestCase):
    def settings(self,kind="discord"):
        env={"DUNE_ADMIN_AUTH_PROVIDER":kind,"DUNE_ADMIN_AUTH_CLIENT_ID":"client-1","DUNE_ADMIN_AUTH_REDIRECT_URI":"https://admin.example.test/auth/callback","DUNE_ADMIN_AUTH_COOKIE_SECURE":"true"}
        if kind=="oidc": env.update({"DUNE_ADMIN_AUTH_ISSUER":"https://id.example.test","DUNE_ADMIN_AUTH_ALLOWED_ORIGINS":"https://id.example.test"})
        return AUTH.load_settings(env)

    def test_subject_map_is_explicit_and_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"subjects.json";path.write_text(json.dumps({"version":1,"subjects":[{"issuer":"https://discord.com","subject":"1234567890","localUserId":"night-ops","enabled":True}]}))
            self.assertEqual(AUTH.mapped_local_user(path,"https://discord.com","1234567890"),"night-ops")
            self.assertIsNone(AUTH.mapped_local_user(path,"https://discord.com","999"))
            path.write_text(json.dumps({"version":1,"subjects":[{"issuer":"https://discord.com","subject":"1234567890","localUserId":"night-ops"},{"issuer":"https://discord.com","subject":"1234567890","localUserId":"owner-aa"}]}))
            with self.assertRaises(ValueError): AUTH.load_subjects(path)

    def test_signed_cookie_expiry_and_tamper(self):
        token=AUTH.sign_payload({"kind":"session","iat":100,"exp":200,"issuer":"x","subject":"y"},"secret")
        self.assertEqual(AUTH.verify_payload(token,"secret","session",150)["subject"],"y")
        with self.assertRaises(PermissionError): AUTH.verify_payload(token+"x","secret","session",150)
        with self.assertRaises(PermissionError): AUTH.verify_payload(token,"secret","session",201)

    def test_discord_code_pkce_state_and_replay(self):
        settings=self.settings();started=AUTH.begin(settings,"session-secret",lambda *_:None,now=1000);flow=AUTH.verify_payload(started["flowCookie"],"session-secret","flow",1001);query=dict(__import__('urllib').parse.parse_qsl(__import__('urllib').parse.urlparse(started["url"]).query))
        self.assertEqual(query["code_challenge_method"],"S256");self.assertEqual(query["scope"],"identify");self.assertNotEqual(query["code_challenge"],flow["verifier"])
        posts=[]
        def post(url,form): posts.append((url,form));return {"access_token":"provider-token","token_type":"Bearer"}
        def get(url,headers=None): self.assertEqual(headers,{"Authorization":"Bearer provider-token"});return {"id":"123456789012345678","username":"operator","global_name":"Operator"}
        cache=AUTH.ReplayCache();result=AUTH.complete(settings,started["flowCookie"],flow["state"],"code-1","session-secret","client-secret",get,post,cache,now=1002)
        self.assertEqual(result["subject"],"123456789012345678");self.assertEqual(posts[0][1]["code_verifier"],flow["verifier"]);self.assertNotIn("provider-token",result["sessionCookie"])
        session=AUTH.verify_payload(result["sessionCookie"],"session-secret","session",1003);self.assertEqual(session["issuer"],"https://discord.com")
        with self.assertRaises(PermissionError): AUTH.complete(settings,started["flowCookie"],flow["state"],"code-1","session-secret","client-secret",get,post,cache,now=1003)

    def test_oidc_discovery_and_rs256_validation(self):
        settings=self.settings("oidc")
        metadata={"issuer":"https://id.example.test","authorization_endpoint":"https://id.example.test/authorize","token_endpoint":"https://id.example.test/token","userinfo_endpoint":"https://id.example.test/userinfo","jwks_uri":"https://id.example.test/jwks"}
        resolved=AUTH.resolve_provider(settings,lambda url:metadata);self.assertEqual(resolved["jwksUri"],"https://id.example.test/jwks")
        private=rsa.generate_private_key(public_exponent=65537,key_size=2048);numbers=private.public_key().public_numbers();now=int(time.time());header={"alg":"RS256","kid":"key-1","typ":"JWT"};claims={"iss":"https://id.example.test","sub":"subject-1","aud":"client-1","iat":now,"exp":now+300,"nonce":"nonce-1"}
        head=AUTH.b64u(json.dumps(header,separators=(",",":")).encode());body=AUTH.b64u(json.dumps(claims,separators=(",",":")).encode());signature=private.sign((head+"."+body).encode(),padding.PKCS1v15(),hashes.SHA256());token=head+"."+body+"."+AUTH.b64u(signature);jwks={"keys":[{"kty":"RSA","use":"sig","kid":"key-1","n":AUTH.b64u(numbers.n.to_bytes((numbers.n.bit_length()+7)//8,"big")),"e":AUTH.b64u(numbers.e.to_bytes((numbers.e.bit_length()+7)//8,"big"))}]}
        self.assertEqual(AUTH.verify_rs256(token,jwks,"https://id.example.test","client-1","nonce-1",now)["sub"],"subject-1")
        with self.assertRaises(PermissionError): AUTH.verify_rs256(token,jwks,"https://id.example.test","client-1","wrong",now)

    def test_endpoint_and_redirect_validation(self):
        with self.assertRaises(ValueError): AUTH.validate_endpoint("http://id.example.test/token",{"http://id.example.test"})
        with self.assertRaises(ValueError): AUTH.load_settings({"DUNE_ADMIN_AUTH_PROVIDER":"discord","DUNE_ADMIN_AUTH_REDIRECT_URI":"http://admin.example.test/cb"})

if __name__=="__main__":unittest.main()
