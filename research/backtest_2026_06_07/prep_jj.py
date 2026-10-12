exec(open("/data/tmp/bt/engine.py").read())
for s,a,b in (("jun","2026-06-01","2026-06-30"),("jul","2026-07-01","2026-07-31")):
    Ts=[d for d in dates if pd.Timestamp(a)<=d<=pd.Timestamp(b)]
    U={T:candidates(T) for T in Ts}
    rows=[{"T":T,**t} for T in Ts for c in U[T] for t in [tech(c,T)] if t]
    pickle.dump((Ts,U),open(f"cands_{s}.pkl","wb")); pickle.dump(pd.DataFrame(rows),open(f"tech_{s}.pkl","wb"))
    print(s,len(Ts),Ts[0].date(),Ts[-1].date(),len(rows),flush=True)
