exec(open("/data/tmp/bt/engine.py").read())
Ts=[d for d in dates if pd.Timestamp("2026-08-03")<=d<=pd.Timestamp("2026-08-31")]
U={T:candidates(T) for T in Ts}
rows=[]
for T in Ts:
    for c in U[T]:
        t=tech(c,T)
        if t: rows.append({"T":T,**t})
tdf=pd.DataFrame(rows)
pickle.dump((Ts,U),open("cands_aug.pkl","wb")); pickle.dump(tdf,open("tech_aug.pkl","wb"))
old=set(sum(pickle.load(open("cands.pkl","rb"))[1].values(),[]))
allc=sorted(set(sum(U.values(),[]))); new=[c for c in allc if c not in old]
print(len(Ts),len(tdf),"union",len(allc),"new",len(new))
json.dump(new,open("new_aug.json","w"))
