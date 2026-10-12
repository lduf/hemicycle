import json,glob,collections,re,datetime as dt,statistics as st,unicodedata
G=json.load(open("groups17.json"));A={"PO847173":"UDR","PO872880":"UDR","PO840056":"NI"}
GROUPS=['GDR','LFI-NFP','ECOS','SOC','LIOT','DEM','EPR','HOR','DR','UDR','RN']
def sig(r): return A.get(r) or G.get(r,{}).get("sigle") or "NI"
def norm(x): return unicodedata.normalize('NFKD',x).encode('ascii','ignore').decode().lower().replace('’',"'").strip()
# noms -> acteurs
names=collections.defaultdict(set)
for f in glob.glob("an_orgs/out/json/acteur/*.json"):
    a=json.load(open(f))["acteur"]; i=a["etatCivil"]["ident"]; uid=a["uid"]["#text"] if isinstance(a["uid"],dict) else a["uid"]
    names[norm(i["nom"])].add(uid); names[norm(i["prenom"]+" "+i["nom"])].add(uid)
# groupe de chaque acteur par date (depuis les votes)
obs=json.load(open("obs.json")); byA=collections.defaultdict(list)
for d,a,p,g in obs: byA[a].append((d,g))
for a in byA: byA[a].sort()
def grp_at(a,d):
    L=byA.get(a)
    if not L: return None
    best=min(L,key=lambda o:abs((dt.date.fromisoformat(o[0])-dt.date.fromisoformat(d)).days)); return best[1]
AUTH=re.compile(r"amendement[^,]*? de (?:M\.|Mme) (.+?)(?= et | à | après | avant | au | aux |,| \(|$)")
DEM=re.compile(r'groupe "([^"]+)"')
gname={v["nom"]:v["sigle"] for v in G.values()}
gname.update({"Union des droites pour la République":"UDR"})
def g_of_name(n):
    for k,v in gname.items():
        if norm(k)==norm(n): return "UDR" if v in("UDDPLR",) else v
    return None
S=collections.defaultdict(lambda: collections.defaultdict(float))
WD=collections.defaultdict(lambda: collections.defaultdict(lambda:[0,0]))
MON=collections.defaultdict(lambda: collections.defaultdict(lambda:[0,0]))
dep=collections.defaultdict(lambda:[0,None,None,None])  # votes, first, last, group
agree=collections.defaultdict(lambda:[0,0]); unknown_auth=0; n_scr=0
scr=[]
for f in glob.glob("an_data/out/json/*.json"):
    s=json.load(open(f))["scrutin"]
    if s["typeVote"]["codeTypeVote"]=="MOC": continue
    n_scr+=1; d=s["dateScrutin"]; t=s["titre"].replace("’","'"); typ=s["typeVote"]["codeTypeVote"]
    kind="ensemble" if re.match(r"l'ensemble|la première partie|la deuxième partie|l'article unique",t) else "amendement" if re.match(r"l'amendement|le sous-amendement",t) else "article" if t.startswith("l'article") else "autre"
    adopt=s["sort"]["code"]=="adopté"
    # auteur amendement
    auth=None
    if kind=="amendement":
        m=AUTH.search(t)
        if m:
            u=names.get(norm(m.group(1)))
            if u and len(u)==1: auth=grp_at(next(iter(u)),d)
        if auth is None: unknown_auth+=1
    dem=set(g for g in (g_of_name(x) for x in DEM.findall(s["demandeur"]["texte"] or "")) if g)
    stance={}
    for g in s["ventilationVotes"]["organe"]["groupes"]["groupe"]:
        sg=sig(g["organeRef"])
        if sg=="NI": continue
        v=g["vote"]["decompteVoix"]; p,c,a=int(v["pour"]),int(v["contre"]),int(v["abstentions"]); m=int(g["nombreMembresGroupe"]); vot=p+c+a
        dn=g["vote"]["decompteNominatif"]; deleg=0
        for k in("pours","contres","abstentions"):
            x=dn.get(k)
            if not x: continue
            x=x["votant"]; x=x if isinstance(x,list) else [x]
            for y in x:
                if y.get("parDelegation")=="true": deleg+=1
                r=dep[y["acteurRef"]]; r[0]+=1; r[3]=sg
        X=S[sg]; X["mem"]+=m; X["vot"]+=vot; X["p"]+=p; X["c"]+=c; X["a"]+=a; X["deleg"]+=deleg; X["n"]+=1
        X["mem_"+kind]+=m; X["vot_"+kind]+=vot
        X["mem_"+typ]+=m; X["vot_"+typ]+=vot
        if p+c: X["rice"]+=abs(p-c)/(p+c); X["rice_n"]+=1
        if auth: 
            k2="own" if auth==sg else "oth"; X["mem_am_"+k2]+=m; X["vot_am_"+k2]+=vot
        if dem:
            k3="dem_own" if sg in dem else "dem_oth"; X["mem_"+k3]+=m; X["vot_"+k3]+=vot
        if vot:
            ms=(p-c)/vot
            if abs(ms)>=.5:
                X["pos"]+=1; X["win"]+= (ms>0)==adopt
            stance[sg]=ms
        wd=dt.date.fromisoformat(d).weekday(); WD[sg][wd][0]+=vot; WD[sg][wd][1]+=m
        MON[sg][d[:7]][0]+=vot; MON[sg][d[:7]][1]+=m
    if auth and auth in GROUPS:
        Y=S[auth]; Y["am_tot"]+=1; Y["am_ok"]+=adopt
    for g in dem:
        if g in GROUPS: S[g]["dem_n"]+=1
    ks=[k for k in stance if abs(stance[k])>=.5]
    for i in ks:
        for j in ks:
            if i<j: agree[(i,j)][0]+= (stance[i]>0)==(stance[j]>0); agree[(i,j)][1]+=1
# première/dernière date par acteur pour dénominateur individuel
dates=sorted({o[0] for o in obs})
didx={d:i for i,d in enumerate(dates)}
# nb de scrutins par date
cnt_date=collections.Counter()
for f in glob.glob("an_data/out/json/*.json"):
    s=json.load(open(f))["scrutin"]
    if s["typeVote"]["codeTypeVote"]!="MOC": cnt_date[s["dateScrutin"]]+=1
cum=[0];
for d in dates: cum.append(cum[-1]+cnt_date[d])
indiv=collections.defaultdict(list)
for a,L in byA.items():
    first,last=L[0][0],L[-1][0]; den=cum[didx[last]+1]-cum[didx[first]]
    if den<300: continue
    g=collections.Counter(x[1] for x in L).most_common(1)[0][0]
    if g in GROUPS: indiv[g].append(min(1,dep[a][0]/den))
out={"n_scrutins":n_scr,"unknown_auth":unknown_auth,"groups":{}}
for g in GROUPS:
    X=S[g]; r=lambda a,b: round(X[a]/X[b],4) if X[b] else None
    v=indiv[g]
    out["groups"][g]=dict(
        members_avg=round(X["mem"]/X["n"],1), part=r("vot","mem"),
        part_ensemble=r("vot_ensemble","mem_ensemble"), part_amend=r("vot_amendement","mem_amendement"), part_article=r("vot_article","mem_article"), part_sps=r("vot_SPS","mem_SPS"),
        part_am_own=r("vot_am_own","mem_am_own"), part_am_oth=r("vot_am_oth","mem_am_oth"),
        part_dem_own=r("vot_dem_own","mem_dem_own"), part_dem_oth=r("vot_dem_oth","mem_dem_oth"),
        abst=round(X["a"]/X["vot"],4), deleg=round(X["deleg"]/X["vot"],4), rice=round(X["rice"]/X["rice_n"],4), win=round(X["win"]/X["pos"],4),
        am_tot=int(X["am_tot"]), am_ok=int(X["am_ok"]), dem_n=int(X["dem_n"]),
        indiv=dict(n=len(v), median=round(st.median(v),4), q1=round(st.quantiles(v,n=4)[0],4), q3=round(st.quantiles(v,n=4)[2],4), mn=round(min(v),4), mx=round(max(v),4), lt10=sum(x<.10 for x in v), gt50=sum(x>.5 for x in v)),
        weekday={k:round(a[0]/a[1],4) for k,a in sorted(WD[g].items()) if a[1]},
        monthly={k:round(a[0]/a[1],4) for k,a in sorted(MON[g].items()) if a[1]},
    )
out["agree"]={f"{i}|{j}":round(a/b,4) for (i,j),(a,b) in agree.items() if b>50}
json.dump(out,open("stats.json","w"),ensure_ascii=False)
print(n_scr,"unknown auth",unknown_auth)
for g in GROUPS:
    o=out["groups"][g]; print(g,o["members_avg"],o["part"],o["part_ensemble"],o["part_amend"],"own",o["part_am_own"],o["part_am_oth"],"dem",o["part_dem_own"],o["part_dem_oth"],"abst",o["abst"],"deleg",o["deleg"],"rice",o["rice"],"win",o["win"],"am",o["am_tot"],o["am_ok"],o["dem_n"],o["indiv"])
