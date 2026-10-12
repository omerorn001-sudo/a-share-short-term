exec(open("/data/tmp/bt/engine.py").read())
print("panel start",dates[0].date())
for s,a,b in (("jan","2026-01-01","2026-01-31"),("feb","2026-02-01","2026-02-28"),("mar","2026-03-01","2026-03-31"),("apr","2026-04-01","2026-04-30"),("may","2026-05-01","2026-05-31")):
    Ts=[d for d in dates if pd.Timestamp(a)<=d<=pd.Timestamp(b)]
    U={T:candidates(T) for T in Ts}
    rows=[{"T":T,**t} for T in Ts for c in U[T] for t in [tech(c,T)] if t]
    pickle.dump((Ts,U),open(f"cands_{s}.pkl","wb")); pickle.dump(pd.DataFrame(rows),open(f"tech_{s}.pkl","wb"))
    print(s,len(Ts),Ts[0].date(),Ts[-1].date(),len(rows),flush=True)
