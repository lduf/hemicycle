import json,datetime as dt,collections
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
obs=[(dt.date.fromisoformat(d),a,p,g) for d,a,p,g in json.load(open("obs.json"))]
byA=collections.defaultdict(list)
for o in obs: byA[o[1]].append(o)
ORDER=['GDR','LFI-NFP','ECOS','SOC','LIOT','DEM','EPR','HOR','DR','UDR','RN','NI']
GI={g:i for i,g in enumerate(ORDER)}
d=json.load(open("quiz_data.json"))
for q in d["q"]:
    s=json.load(open(f"an_data/out/json/VTANR5L17V{q['n']}.json"))["scrutin"]; D=dt.date.fromisoformat(s["dateScrutin"])
    vs={a:(p,g,st) for a,p,g,st in voters(s)}
    for W in (45,150):
     seat={}  # place -> (dist, acteur, group, state)
     for a,L in byA.items():
        if a in vs: p,g,st=vs[a]; best=(0,p,g,st)
        else:
            o=min(L,key=lambda o:abs((o[0]-D).days)); dd=abs((o[0]-D).days)
            if dd>W: continue
            best=(dd,o[2],o[3],'x')
        cur=seat.get(best[1])
        if cur is None or best[0]<cur[0]: seat[best[1]]=best
     if len(seat)>=570: break
    places=sorted(seat,reverse=True)  # gauche -> droite
    cnt=collections.Counter(seat[p][2] for p in places)
    exp={k:v[3] for k,v in q["g"].items()}
    diff={k:cnt.get(k,0)-exp.get(k,0) for k in exp if cnt.get(k,0)!=exp.get(k,0)}
    q["seats"]="".join(chr(65+GI.get(seat[p][2],11))+seat[p][3] for p in places)
    print(q["n"],len(places),diff)
json.dump(d,open("quiz_data.json","w"),ensure_ascii=False)
