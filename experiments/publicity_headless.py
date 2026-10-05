import subprocess,json,re,tempfile
from pathlib import Path
from html.parser import HTMLParser
class Text(HTMLParser):
 def __init__(self):super().__init__();self.items=[];self.skip=0
 def handle_starttag(self,t,a):
  if t in ["script","style","textarea"]:self.skip+=1
 def handle_endtag(self,t):
  if t in ["script","style","textarea"]:self.skip=max(0,self.skip-1)
 def handle_data(self,s):
  if not self.skip and s.strip():self.items.append(s.strip())
with tempfile.TemporaryDirectory(prefix="isologismoi-headless-") as profile:
 cmd=["google-chrome","--headless","--disable-gpu","--no-sandbox","--user-data-dir="+profile,
      "--dump-dom","--virtual-time-budget=12000","https://publicity.businessportal.gr/company/194123801000"]
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=40);t=Text();t.feed(p.stdout)
  o={"exit_code":p.returncode,"company_name_visible":any("STRIDE" in x for x in t.items),
     "gemi_visible":any("194123801000" in x for x in t.items),
     "captcha_visible":any("captcha" in x.lower() for x in t.items),
     "text_excerpt":t.items[:20],"dom_bytes":len(p.stdout),"mode":"normal Chrome headless, no stealth, ephemeral profile"}
 except subprocess.TimeoutExpired:o={"error":"headless timed out after 40 seconds"}
Path("experiments/publicity-evidence/headless.json").write_text(json.dumps(o,ensure_ascii=False,indent=2));print(json.dumps(o,ensure_ascii=False))

