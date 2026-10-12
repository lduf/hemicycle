import json,glob,datetime as dt,collections
G=json.load(open("groups17.json"));A={"PO847173":"UDR","PO872880":"UDR","PO840056":"NI"}
def sig(r): return A.get(r) or G.get(r,{}).get("sigle") or "NI"
def voters(s):
    for g in s["ventilationVotes"]["organe"]["groupes"]["groupe"]:
        dn=g["vote"]["decompteNominatif"]
        for k,st in (("pours","p"),("contres","c"),("abstentions","a"),("nonVotants","x")):
            v=dn.get(k)
            if not v: continue
            v=v["votant"]; v=v if isinstance(v,list) else [v]
            for x in v:
                if x.get("numPlace"): yield x["acteurRef"],int(x["numPlace"]),sig(g["organeRef"]),st
obs=[]  # (date, acteur, place, group)
for f in glob.glob("an_data/out/json/*.json"):
    s=json.load(open(f))["scrutin"]; d=dt.date.fromisoformat(s["dateScrutin"])
    for a,p,g,_ in voters(s): obs.append((d,a,p,g))
print(len(obs))
json.dump([(o[0].isoformat(),o[1],o[2],o[3]) for o in obs],open("obs.json","w"))
