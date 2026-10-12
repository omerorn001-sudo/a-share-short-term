exec(open("opt2.py").read())
S={}
S["原系统(7条件+总分)"]=(lambda g:g["7条满足"]*100+g["总分"],None)
st7=[("f_turn",-1),("7条满足",-1),("f_vtrend",-1),("f_pos20",-1),("f_vol20",1),("f_body",1),("f_main1r",-1)]
S["9月稳定7因子(8月为样本外)"]=(lambda g:sum(zr(g,f,s) for f,s in st7),None)
n6=[("f_r20",-1),("f_pos20",-1),("f_vtrend",-1),("f_turn",-1),("f_vol20",1),("f_main1r",-1)]
S["回踩6因子"]=(lambda g:sum(zr(g,f,s) for f,s in n6),None)
n4=[("f_r20",-1),("f_vtrend",-1),("f_turn",-1),("f_vol20",1)]
S["精简4因子"]=(lambda g:sum(zr(g,f,s) for f,s in n4),None)
S["仅20日涨幅最低"]=(lambda g:-g["f_r20"],None)
gapf=lambda g:g["f_gap1"].between(-0.03,0.02)
S["回踩6因子+开盘-3%~+2%"]=(S["回踩6因子"][0],gapf)
S["精简4因子+开盘-3%~+2%"]=(S["精简4因子"][0],gapf)
S["回踩6因子+MA20上方"]=(S["回踩6因子"][0],lambda g:g["f_b20"]>0)
rows=[]
for nm,(sc,fl) in S.items():
    for m,A in D.items():
        o=run(A,sc,fl); rows.append({"方案":nm,"月":m,**{k:round(v,2) for k,v in o.items()}})
R=pd.DataFrame(rows); pd.set_option("display.width",300); pd.set_option("display.max_columns",40)
print(R.to_string()); pickle.dump(R,open("opt3.pkl","wb"))
