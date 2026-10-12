exec(open("opt2.py").read())
fs=[c for c in D["9月"].columns if c.startswith("f_")]+["7条满足","总分","资金分","技术分","调研次数","板块排名"]
rows=[]
for f in fs:
    r={"因子":f}
    for m,A in D.items():
        for k in (2,3):
            ic=A.groupby("T").apply(lambda g:g[f].rank().corr(g[f"ret{k}"].rank())).mean()
            r[f"{m}T{k}"]=round(ic,3)
    rows.append(r)
print(pd.DataFrame(rows).set_index("因子").to_string())
for m,A in D.items(): print(m,"池均T3",round(A.ret3.mean()*100,2),"天数",A["T"].nunique())
